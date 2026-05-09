# -*- coding: utf-8 -*-
"""
筛选热门板块成分股 -> 取 Top N 个股做精细分析 -> 推送到 Telegram。

推荐先 dry-run 验证筛选结果：
    python run_screen_analyze_telegram.py --dry-run --no-send

正式运行：
    python run_screen_analyze_telegram.py

依赖 .env 中至少配置：
    OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
    TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from daily_analysis.config import get_config
from daily_analysis.cli.main import StockAnalysisPipeline, setup_logging
from daily_analysis.integrations.notification import NotificationChannel
from daily_analysis.analysis.stock_screener import ScreeningResult

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="热门板块筛选 + Top 个股精细分析 + Telegram 推送一体化脚本",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--sector-count",
        type=int,
        default=5,
        help="参与筛选的热门板块数量。数值越大，覆盖越广，但行情请求更多、运行更慢。",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=3,
        help="从规则层排序结果中取前 N 只股票进入精细分析。你的需求是前 3 个股，所以默认 3。",
    )
    parser.add_argument(
        "--include-llm",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否对 Top N 个股调用 LLM 生成精细分析。关闭后只输出筛选报告。",
    )
    parser.add_argument(
        "--send",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否推送到 Telegram。可用 --no-send 只保存报告不推送。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试跑模式：只做规则筛选，不跑 LLM，不推送。等价于 --no-include-llm --no-send。",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="主流程并发线程数。这个脚本对 Top N 精细分析默认串行执行，保留该参数用于初始化主流程。",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="输出更详细日志，并写入 logs/stock_analysis_debug_YYYYMMDD.log。",
    )
    parser.add_argument(
        "--report-prefix",
        default="screen_analyze_telegram",
        help="保存到 reports/ 下的报告文件名前缀。",
    )
    parser.add_argument(
        "--send-screening-only-if-no-analysis",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="当精细分析没有成功结果时，是否仍把规则筛选报告推送出去。",
    )
    parser.add_argument(
        "--max-report-chars",
        type=int,
        default=0,
        help="推送前截断报告字符数，0 表示不主动截断；Telegram 服务内部仍会按 4096 字符分段。",
    )

    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.sector_count <= 0:
        raise ValueError("--sector-count 必须大于 0")
    if args.top_n <= 0:
        raise ValueError("--top-n 必须大于 0")
    if args.max_report_chars < 0:
        raise ValueError("--max-report-chars 不能小于 0")


def build_pipeline_report(screening_result: ScreeningResult, analysis_report: Optional[str]) -> str:
    lines = [
        "# 热门板块筛选 + Top 个股精细分析 Pipeline",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "> 用途：投资研究与复盘辅助，不构成投资建议。",
        "",
        "## Pipeline 摘要",
        "",
        f"- 热门板块数：{len(screening_result.sectors)}",
        f"- 有效候选数：{len(screening_result.candidates)}",
        f"- 进入精细分析：{len(screening_result.selected)}",
        f"- 过滤样本数：{len(screening_result.filtered)}",
        "",
    ]

    if screening_result.selected:
        lines.extend([
            "## 进入精细分析的 Top 个股",
            "",
            "| 排名 | 代码 | 名称 | 板块 | 综合分 | 趋势分 | 信号 | 5日均成交额 | 风险 |",
            "| --- | --- | --- | --- | ---: | ---: | --- | ---: | --- |",
        ])
        for index, item in enumerate(screening_result.selected, start=1):
            lines.append(
                f"| {index} | {item.code} | {item.name} | {item.sector_name} | "
                f"{item.composite_score:.1f} | {item.trend_result.signal_score} | "
                f"{item.trend_result.buy_signal.value} | {item.average_amount_5d / 100000000:.2f}亿 | "
                f"{'；'.join(item.risk_flags) or '-'} |"
            )
        lines.append("")

    lines.extend(["## 规则层筛选报告", "", screening_result.format_report(), ""])

    if analysis_report:
        lines.extend(["## Top 个股精细分析报告", "", analysis_report])
    else:
        lines.extend(["## Top 个股精细分析报告", "", "未生成精细分析报告。"])

    return "\n".join(lines)


def assert_telegram_configured(pipeline: StockAnalysisPipeline) -> None:
    channels = pipeline.notifier.get_available_channels()
    if NotificationChannel.TELEGRAM not in channels:
        raise RuntimeError(
            "Telegram 未配置或配置不完整。请在 .env 中设置 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID。"
        )


def maybe_truncate_report(report: str, max_chars: int) -> str:
    if max_chars <= 0 or len(report) <= max_chars:
        return report
    suffix = "\n\n---\n\n报告已按 --max-report-chars 截断，完整内容请查看本地 reports/ 文件。"
    return report[: max(0, max_chars - len(suffix))] + suffix


def main() -> int:
    args = parse_args()
    validate_args(args)

    if args.dry_run:
        args.include_llm = False
        args.send = False

    config = get_config()
    setup_logging(debug=args.debug or config.debug, log_dir=config.log_dir)

    logger.info("===== 启动筛选-分析-Telegram 一体化 Pipeline =====")
    logger.info(
        "参数: sector_count=%s, top_n=%s, include_llm=%s, send=%s, dry_run=%s",
        args.sector_count,
        args.top_n,
        args.include_llm,
        args.send,
        args.dry_run,
    )

    for warning in config.validate():
        logger.warning(warning)

    pipeline = StockAnalysisPipeline(config=config, max_workers=args.workers)

    if args.send:
        assert_telegram_configured(pipeline)

    screening_result = pipeline.run_hot_sector_screening(
        top_n=args.top_n,
        sector_count=args.sector_count,
        run_llm=False,
        send_notification=False,
    )

    if not screening_result.selected:
        logger.warning("筛选结果为空，没有可进入精细分析的个股。")

    analysis_results = []
    if args.include_llm and screening_result.selected:
        for index, candidate in enumerate(screening_result.selected, start=1):
            logger.info("[%s/%s] 开始精细分析 %s %s", index, len(screening_result.selected), candidate.code, candidate.name)
            result = pipeline.process_single_stock(candidate.code, skip_analysis=False)
            if result:
                analysis_results.append(result)
            else:
                logger.warning("%s %s 精细分析未返回结果", candidate.code, candidate.name)

    analysis_report = None
    if analysis_results:
        analysis_report = pipeline.notifier.generate_dashboard_report(analysis_results)
    elif args.include_llm:
        logger.warning("Top 个股精细分析全部失败或无结果。")

    final_report = build_pipeline_report(screening_result, analysis_report)
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{args.report_prefix}_{date_str}.md"
    filepath = pipeline.notifier.save_report_to_file(final_report, filename)
    logger.info("Pipeline 报告已保存: %s", filepath)

    should_send = args.send and (bool(analysis_results) or args.send_screening_only_if_no_analysis)
    if should_send:
        send_report = maybe_truncate_report(final_report, args.max_report_chars)
        logger.info("开始推送 Telegram。")
        success = pipeline.notifier.send_to_telegram(send_report)
        if not success:
            logger.error("Telegram 推送失败。")
            return 2
        logger.info("Telegram 推送成功。")
    elif args.send:
        logger.warning("未推送：精细分析无结果，且 --no-send-screening-only-if-no-analysis 已启用。")
    else:
        logger.info("已跳过 Telegram 推送。")

    print(f"报告已保存: {Path(filepath)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.exception("Pipeline 运行失败: %s", exc)
        print(f"Pipeline 运行失败: {exc}", file=sys.stderr)
        raise SystemExit(1)
