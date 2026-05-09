#!/usr/bin/env bash
set -euo pipefail

# 热门板块筛选 -> Top 个股精细分析 -> Telegram 推送
#
# 使用方式：
#   bash run_screen_analyze_telegram.sh
#
# 试跑：
#   DRY_RUN=true bash run_screen_analyze_telegram.sh
#
# 临时改参数：
#   SECTOR_COUNT=8 TOP_N=5 SEND=false bash run_screen_analyze_telegram.sh

cd "$(dirname "$0")/.."

# Python 解释器。Windows/Git Bash 下默认使用项目虚拟环境。
PYTHON_BIN="${PYTHON_BIN:-.venv/Scripts/python.exe}"

# 参与筛选的热门板块数量。越大覆盖越广，但行情请求更多、运行更慢。
SECTOR_COUNT="${SECTOR_COUNT:-5}"

# 规则层排序后，取前 N 只股票进入精细分析。
TOP_N="${TOP_N:-3}"

# 是否调用 LLM 做 Top N 个股精细分析：true / false。
INCLUDE_LLM="${INCLUDE_LLM:-true}"

# 是否推送到 Telegram：true / false。
SEND="${SEND:-true}"

# 试跑模式：true 时只做筛选，不跑 LLM，不推送。
DRY_RUN="${DRY_RUN:-false}"

# 主流程初始化用的并发线程数。留空则使用 .env / config.py 默认值。
WORKERS="${WORKERS:-}"

# 是否开启 debug 日志：true / false。
DEBUG="${DEBUG:-false}"

# reports/ 下保存报告的文件名前缀。
REPORT_PREFIX="${REPORT_PREFIX:-screen_analyze_telegram}"

# LLM 精细分析无结果时，是否仍推送规则筛选报告：true / false。
SEND_SCREENING_ONLY_IF_NO_ANALYSIS="${SEND_SCREENING_ONLY_IF_NO_ANALYSIS:-true}"

# 推送前主动截断报告字符数。0 表示不主动截断；Telegram 内部仍会按 4096 字符分段。
MAX_REPORT_CHARS="${MAX_REPORT_CHARS:-0}"

args=(
  "-m" "daily_analysis.cli.screen_analyze_telegram"
  "--sector-count" "$SECTOR_COUNT"
  "--top-n" "$TOP_N"
  "--report-prefix" "$REPORT_PREFIX"
  "--max-report-chars" "$MAX_REPORT_CHARS"
)

if [[ "$INCLUDE_LLM" == "true" ]]; then
  args+=("--include-llm")
else
  args+=("--no-include-llm")
fi

if [[ "$SEND" == "true" ]]; then
  args+=("--send")
else
  args+=("--no-send")
fi

if [[ "$DRY_RUN" == "true" ]]; then
  args+=("--dry-run")
fi

if [[ -n "$WORKERS" ]]; then
  args+=("--workers" "$WORKERS")
fi

if [[ "$DEBUG" == "true" ]]; then
  args+=("--debug")
fi

if [[ "$SEND_SCREENING_ONLY_IF_NO_ANALYSIS" == "true" ]]; then
  args+=("--send-screening-only-if-no-analysis")
else
  args+=("--no-send-screening-only-if-no-analysis")
fi

"$PYTHON_BIN" "${args[@]}"
