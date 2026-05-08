# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 主调度程序
===================================

职责：
1. 协调各模块完成股票分析流程
2. 实现低并发的线程池调度
3. 全局异常处理，确保单股失败不影响整体
4. 提供命令行入口

使用方式：
    python main.py              # 正常运行
    python main.py --debug      # 调试模式
    python main.py --dry-run    # 仅获取数据不分析

交易理念（已融入分析）：
- 严进策略：不追高，乖离率 > 5% 不买入
- 趋势交易：只做 MA5>MA10>MA20 多头排列
- 效率优先：关注筹码集中度好的股票
- 买点偏好：缩量回踩 MA5/MA10 支撑
"""
import os

import argparse
import logging
import sys
import time
import warnings
import pandas as pd

# 配置代理：默认使用 Clash HTTP 代理（可通过环境变量覆盖）
os.environ.setdefault("http_proxy", "http://127.0.0.1:7890")
os.environ.setdefault("https_proxy", "http://127.0.0.1:7890")
os.environ.setdefault("HTTP_PROXY", os.environ["http_proxy"])
os.environ.setdefault("HTTPS_PROXY", os.environ["https_proxy"])

# 国内数据源域名加入 no_proxy，强制直连
# 这样可以同时保证：
# 1. AkShare/Tushare 直连国内服务器（解决 ProxyError）
# 2. OpenAI/Telegram 继续走代理（解决无法访问的问题）
domestic_domains = [
    "eastmoney.com", "dfcfw.com", "sina.com.cn", "163.com", "baidu.com", 
    "push2.eastmoney.com", "emob.eastmoney.com", "cninfo.com.cn"
]
no_proxy = os.environ.get("no_proxy", "")
# 确保 no_proxy 包含所有国内域名
for domain in domestic_domains:
    if domain not in no_proxy:
        if no_proxy:
            no_proxy += ","
        no_proxy += domain
os.environ["no_proxy"] = no_proxy
os.environ["NO_PROXY"] = no_proxy
# 配置日志基本格式，防止 logging 未初始化前调用 info 报错（虽然这里 logging 已经导入）
# 但更规范的做法是等待 main 函数内初始化日志，或者直接 print
# 这里为了调试方便，直接 print
print(f"代理配置优化: 已设置 no_proxy={no_proxy}")
pass


# 忽略 pandas 的 SettingWithCopyWarning warnings
warnings.filterwarnings('ignore', category=pd.errors.SettingWithCopyWarning)

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timezone, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from feishu_doc import FeishuDocManager

from config import get_config, Config
from storage import get_db, DatabaseManager
from data_provider import DataFetcherManager
from data_provider.akshare_fetcher import AkshareFetcher, RealtimeQuote, ChipDistribution
from company_intel import CompanyIntelligence, CompanyIntelligenceService
from analyzer import OpenAIAnalyzer, AnalysisResult, STOCK_NAME_MAP
from notification import NotificationService, NotificationChannel, send_daily_report
from search_service import SearchService, SearchResponse
from stock_analyzer import StockTrendAnalyzer, TrendAnalysisResult
from stock_screener import ScreeningResult, StockScreener
from market_analyzer import MarketAnalyzer, evaluate_market_environment
from theme_backtester import ThemeBacktester
from theme_radar import ThemeRadar
from user_manager import UserManager

# 配置日志格式
LOG_FORMAT = '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def setup_logging(debug: bool = False, log_dir: str = "./logs") -> None:
    """
    配置日志系统（同时输出到控制台和文件）
    
    Args:
        debug: 是否启用调试模式
        log_dir: 日志文件目录
    """
    level = logging.DEBUG if debug else logging.INFO
    
    # 创建日志目录
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # 日志文件路径（按日期分文件）
    today_str = datetime.now().strftime('%Y%m%d')
    log_file = log_path / f"stock_analysis_{today_str}.log"
    debug_log_file = log_path / f"stock_analysis_debug_{today_str}.log"
    
    # 创建根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # 根 logger 设为 DEBUG，由 handler 控制输出级别
    
    # Handler 1: 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(console_handler)
    
    # Handler 2: 常规日志文件（INFO 级别，10MB 轮转）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(file_handler)
    
    # Handler 3: 调试日志文件（DEBUG 级别，包含所有详细信息）
    debug_handler = RotatingFileHandler(
        debug_log_file,
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=3,
        encoding='utf-8'
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(debug_handler)
    
    # 降低第三方库的日志级别
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    logging.getLogger('google').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    
    logging.info(f"日志系统初始化完成，日志目录: {log_path.absolute()}")
    logging.info(f"常规日志: {log_file}")
    logging.info(f"调试日志: {debug_log_file}")


logger = logging.getLogger(__name__)


class StockAnalysisPipeline:
    """
    股票分析主流程调度器
    
    职责：
    1. 管理整个分析流程
    2. 协调数据获取、存储、搜索、分析、通知等模块
    3. 实现并发控制和异常处理
    """
    
    def __init__(
        self,
        config: Optional[Config] = None,
        max_workers: Optional[int] = None
    ):
        """
        初始化调度器
        
        Args:
            config: 配置对象（可选，默认使用全局配置）
            max_workers: 最大并发线程数（可选，默认从配置读取）
        """
        self.config = config or get_config()
        self.max_workers = max_workers or self.config.max_workers
        
        # 初始化各模块
        self.db = get_db()
        self.fetcher_manager = DataFetcherManager()
        self.akshare_fetcher = AkshareFetcher()  # 用于获取增强数据（量比、筹码等）
        self.trend_analyzer = StockTrendAnalyzer()  # 趋势分析器
        self.analyzer = OpenAIAnalyzer()
        self.notifier = NotificationService()
        self.company_intel_service = CompanyIntelligenceService(self.akshare_fetcher)
        self._market_context: Optional[Dict[str, Any]] = None
        self._benchmark_history = None
        self._benchmark_history_loaded = False
        
        # 初始化搜索服务
        self.search_service = SearchService(
            tavily_keys=self.config.tavily_api_keys,
            serpapi_keys=self.config.serpapi_keys,
        )
        
        # 初始化用户管理器
        self.user_manager = UserManager()
        if self.user_manager.has_users():
            logger.info(f"已启用多用户模式，加载了 {len(self.user_manager.users)} 个用户配置")
        
        
        logger.info(f"调度器初始化完成，最大并发数: {self.max_workers}")
        logger.info("已启用趋势分析器 (MA5>MA10>MA20 多头判断)")
        if self.search_service.is_available:
            logger.info("搜索服务已启用 (Tavily/SerpAPI)")
        else:
            logger.warning("搜索服务未启用（未配置 API Key）")
    
    def fetch_and_save_stock_data(
        self, 
        code: str,
        force_refresh: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        获取并保存单只股票数据
        
        断点续传逻辑：
        1. 检查数据库是否已有今日数据
        2. 如果有且不强制刷新，则跳过网络请求
        3. 否则从数据源获取并保存
        
        Args:
            code: 股票代码
            force_refresh: 是否强制刷新（忽略本地缓存）
            
        Returns:
            Tuple[是否成功, 错误信息]
        """
        try:
            today = date.today()
            
            # 断点续传检查：如果今日数据已存在，跳过
            if not force_refresh and self.db.has_today_data(code, today):
                logger.info(f"[{code}] 今日数据已存在，跳过获取（断点续传）")
                return True, None
            
            # 从数据源获取数据
            logger.info(f"[{code}] 开始从数据源获取数据...")
            df, source_name = self.fetcher_manager.get_daily_data(code, days=250)
            
            if df is None or df.empty:
                return False, "获取数据为空"
            
            # 保存到数据库
            saved_count = self.db.save_daily_data(df, code, source_name)
            logger.info(f"[{code}] 数据保存成功（来源: {source_name}，新增 {saved_count} 条）")
            
            return True, None
            
        except Exception as e:
            error_msg = f"获取/保存数据失败: {str(e)}"
            logger.error(f"[{code}] {error_msg}")
            return False, error_msg
    
    def _get_market_context(self) -> Dict[str, Any]:
        """获取单轮运行内复用的大盘/板块环境。"""
        if self._market_context is not None:
            return self._market_context

        neutral_context = {
            'overview': {},
            'environment': {
                'market_score': 50,
                'market_status': '震荡',
                'risk_level': '中',
                'summary': '市场环境数据不足，按中性处理',
                'reasons': ['市场环境数据获取失败或缺失'],
                'avg_index_change': 0.0,
                'top_sectors': [],
                'bottom_sectors': [],
                'sector_heat_summary': '领涨板块：无；领跌板块：无',
            },
        }

        try:
            market_analyzer = MarketAnalyzer(search_service=None, analyzer=None)
            overview = market_analyzer.get_market_overview()
            environment = evaluate_market_environment(overview)
            self._market_context = {
                'overview': overview.to_dict(),
                'environment': environment,
            }
            logger.info(
                f"大盘环境: {environment['market_status']} "
                f"(评分={environment['market_score']}, 风险={environment['risk_level']})"
            )
        except Exception as e:
            logger.warning(f"获取大盘环境失败，使用中性环境: {e}")
            self._market_context = neutral_context

        return self._market_context

    def _get_benchmark_history(self):
        """获取单轮运行内复用的宽基指数日线，用于个股相对强弱计算。"""
        if self._benchmark_history_loaded:
            return self._benchmark_history

        try:
            self._benchmark_history = self.akshare_fetcher.get_index_daily_data("000300", days=250)
            logger.info("[RS] 已获取沪深300指数日线作为相对强弱基准")
        except Exception as e:
            logger.warning(f"[RS] 获取沪深300基准日线失败，跳过相对大盘强弱计算: {e}")
            self._benchmark_history = None
        self._benchmark_history_loaded = True
        return self._benchmark_history

    def analyze_stock(self, code: str) -> Optional[AnalysisResult]:
        """
        分析单只股票（增强版：含量比、换手率、筹码分析、多维度情报）
        
        流程：
        1. 获取实时行情（量比、换手率）
        2. 获取筹码分布
        3. 获取官方公告和结构化财务指标
        4. 进行趋势分析（基于交易理念）
        5. 多维度情报搜索（最新消息+风险排查+业绩预期）
        6. 从数据库获取分析上下文
        7. 调用 AI 进行综合分析
        
        Args:
            code: 股票代码
            
        Returns:
            AnalysisResult 或 None（如果分析失败）
        """
        try:
            # 获取股票名称（优先从实时行情获取真实名称）
            stock_name = STOCK_NAME_MAP.get(code, '')
            
            # Step 1: 获取实时行情（量比、换手率等）
            realtime_quote: Optional[RealtimeQuote] = None
            try:
                realtime_quote = self.akshare_fetcher.get_realtime_quote(code)
                if realtime_quote:
                    # 使用实时行情返回的真实股票名称
                    if realtime_quote.name:
                        stock_name = realtime_quote.name
                    logger.info(f"[{code}] {stock_name} 实时行情: 价格={realtime_quote.price}, "
                              f"量比={realtime_quote.volume_ratio}, 换手率={realtime_quote.turnover_rate}%")
            except Exception as e:
                logger.warning(f"[{code}] 获取实时行情失败: {e}")
            
            # 如果从实时行情获取名称失败，尝试使用专用接口获取
            if not stock_name and realtime_quote is None:
                try:
                    fetched_name = self.akshare_fetcher.get_stock_name(code)
                    if fetched_name:
                        stock_name = fetched_name
                        logger.info(f"[{code}] 通过辅助接口获取到名称: {stock_name}")
                except Exception as e:
                     logger.warning(f"[{code}] 辅助接口获取名称失败: {e}")

            # 如果还是没有名称，使用代码作为名称
            if not stock_name:
                stock_name = f'股票{code}'
            
            # Step 2: 获取筹码分布
            chip_data: Optional[ChipDistribution] = None
            try:
                chip_data = self.akshare_fetcher.get_chip_distribution(code)
                if chip_data:
                    logger.info(f"[{code}] 筹码分布: 获利比例={chip_data.profit_ratio:.1%}, "
                              f"90%集中度={chip_data.concentration_90:.2%}")
            except Exception as e:
                logger.warning(f"[{code}] 获取筹码分布失败: {e}")

            # Step 3: 官方公告与结构化财务指标
            company_intel: Optional[CompanyIntelligence] = None
            try:
                company_intel = self.company_intel_service.get_company_intelligence(code, stock_name)
                logger.info(
                    f"[{code}] 官方情报: 公告{len(company_intel.announcements)}条, "
                    f"风险{len(company_intel.risk_flags)}条"
                )
            except Exception as e:
                logger.warning(f"[{code}] 获取官方公告/财务数据失败: {e}")
            
            # Step 4: 趋势分析（基于交易理念）
            trend_result: Optional[TrendAnalysisResult] = None
            try:
                # 获取历史数据进行趋势分析
                context = self.db.get_analysis_context(code)
                if context and 'raw_data' in context:
                    import pandas as pd
                    raw_data = context['raw_data']
                    if isinstance(raw_data, list) and len(raw_data) > 0:
                        df = pd.DataFrame(raw_data)
                        benchmark_df = self._get_benchmark_history()
                        trend_result = self.trend_analyzer.analyze(
                            df,
                            code,
                            benchmark_df=benchmark_df,
                            security_name=stock_name,
                        )
                        logger.info(f"[{code}] 趋势分析: {trend_result.trend_status.value}, "
                                  f"买入信号={trend_result.buy_signal.value}, 评分={trend_result.signal_score}, "
                                  f"RS={trend_result.relative_strength_status}")
            except Exception as e:
                logger.warning(f"[{code}] 趋势分析失败: {e}")
            
            # Step 5: 多维度情报搜索（最新消息+风险排查+业绩预期）
            news_context = None
            if self.search_service.is_available:
                logger.info(f"[{code}] 开始多维度情报搜索...")
                
                # 使用多维度搜索（最多3次搜索）
                intel_results = self.search_service.search_comprehensive_intel(
                    stock_code=code,
                    stock_name=stock_name,
                    max_searches=3
                )
                
                # 格式化情报报告
                if intel_results:
                    news_context = self.search_service.format_intel_report(intel_results, stock_name)
                    total_results = sum(
                        len(r.results) for r in intel_results.values() if r.success
                    )
                    logger.info(f"[{code}] 情报搜索完成: 共 {total_results} 条结果")
                    logger.debug(f"[{code}] 情报搜索结果:\n{news_context}")
            else:
                logger.info(f"[{code}] 搜索服务不可用，跳过情报搜索")
            
            # Step 6: 获取分析上下文（技术面数据）
            context = self.db.get_analysis_context(code)
            
            if context is None:
                logger.warning(f"[{code}] 无法获取分析上下文，跳过分析")
                return None
            
            # Step 7: 增强上下文数据（添加实时行情、筹码、趋势分析结果、股票名称、大盘环境）
            market_context = self._get_market_context()
            if trend_result:
                market_environment = market_context.get('environment') or {}
                self.trend_analyzer.apply_position_model(
                    trend_result,
                    market_status=market_environment.get('market_status', '震荡'),
                )
            enhanced_context = self._enhance_context(
                context,
                realtime_quote,
                chip_data,
                company_intel,
                trend_result,
                stock_name,
                market_context
            )
            
            # Step 8: 调用 AI 分析（传入增强的上下文和新闻）
            result = self.analyzer.analyze(enhanced_context, news_context=news_context)
            
            return result
            
        except Exception as e:
            logger.error(f"[{code}] 分析失败: {e}")
            logger.exception(f"[{code}] 详细错误信息:")
            return None
    
    def _enhance_context(
        self,
        context: Dict[str, Any],
        realtime_quote: Optional[RealtimeQuote],
        chip_data: Optional[ChipDistribution],
        company_intel: Optional[CompanyIntelligence],
        trend_result: Optional[TrendAnalysisResult],
        stock_name: str = "",
        market_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        增强分析上下文
        
        将实时行情、筹码分布、趋势分析结果、股票名称添加到上下文中
        
        Args:
            context: 原始上下文
            realtime_quote: 实时行情数据
            chip_data: 筹码分布数据
            company_intel: 官方公告和结构化财务数据
            trend_result: 趋势分析结果
            stock_name: 股票名称
            
        Returns:
            增强后的上下文
        """
        enhanced = context.copy()
        
        # 添加股票名称
        if stock_name:
            enhanced['stock_name'] = stock_name
        elif realtime_quote and realtime_quote.name:
            enhanced['stock_name'] = realtime_quote.name

        if market_context:
            enhanced['market_context'] = market_context

        # 添加实时行情
        if realtime_quote:
            enhanced['realtime'] = {
                'name': realtime_quote.name,  # 股票名称
                'price': realtime_quote.price,
                'volume_ratio': realtime_quote.volume_ratio,
                'volume_ratio_desc': self._describe_volume_ratio(realtime_quote.volume_ratio),
                'turnover_rate': realtime_quote.turnover_rate,
                'pe_ratio': realtime_quote.pe_ratio,
                'pb_ratio': realtime_quote.pb_ratio,
                'total_mv': realtime_quote.total_mv,
                'circ_mv': realtime_quote.circ_mv,
                'change_60d': realtime_quote.change_60d,
            }
        
        # 添加筹码分布
        if chip_data:
            current_price = realtime_quote.price if realtime_quote else 0
            enhanced['chip'] = {
                'profit_ratio': chip_data.profit_ratio,
                'avg_cost': chip_data.avg_cost,
                'concentration_90': chip_data.concentration_90,
                'concentration_70': chip_data.concentration_70,
                'chip_status': chip_data.get_chip_status(current_price),
            }

        if company_intel:
            enhanced['company_intel'] = company_intel.to_dict()
            enhanced['company_intel_context'] = company_intel.format_context()
        
        # 添加趋势分析结果
        if trend_result:
            enhanced['trend_analysis'] = {
                'instrument_type': trend_result.instrument_type.value,
                'strategy_profile': trend_result.strategy_profile,
                'strategy_notes': trend_result.strategy_notes,
                'trend_status': trend_result.trend_status.value,
                'ma_alignment': trend_result.ma_alignment,
                'trend_strength': trend_result.trend_strength,
                'bias_ma5': trend_result.bias_ma5,
                'bias_ma10': trend_result.bias_ma10,
                'bias_ma20': trend_result.bias_ma20,
                'ma60_trend': trend_result.ma60_trend,
                'price_vs_ma60': trend_result.price_vs_ma60,
                'ma60_slope': trend_result.ma60_slope,
                'medium_trend_risk': trend_result.medium_trend_risk,
                'current_price': trend_result.current_price,
                'ma5': trend_result.ma5,
                'ma10': trend_result.ma10,
                'ma20': trend_result.ma20,
                'ma60': trend_result.ma60,
                'support_ma5': trend_result.support_ma5,
                'support_ma10': trend_result.support_ma10,
                'ma5_touch_reclaim': trend_result.ma5_touch_reclaim,
                'ma10_touch_reclaim': trend_result.ma10_touch_reclaim,
                'bullish_candle': trend_result.bullish_candle,
                'lower_shadow_ratio': trend_result.lower_shadow_ratio,
                'ma5_hold_days': trend_result.ma5_hold_days,
                'ma10_hold_days': trend_result.ma10_hold_days,
                'ma20_breakdown': trend_result.ma20_breakdown,
                'support_confirmation': trend_result.support_confirmation,
                'support_levels': trend_result.support_levels,
                'resistance_levels': trend_result.resistance_levels,
                'pattern_signal': trend_result.pattern_signal,
                'breakout_status': trend_result.breakout_status,
                'breakout_level': trend_result.breakout_level,
                'breakout_score': trend_result.breakout_score,
                'breakout_valid': trend_result.breakout_valid,
                'breakout_extension_threshold': trend_result.breakout_extension_threshold,
                'new_high_20d': trend_result.new_high_20d,
                'volume_breakout': trend_result.volume_breakout,
                'platform_breakout': trend_result.platform_breakout,
                'ma_compression_breakout': trend_result.ma_compression_breakout,
                'limit_up_pullback': trend_result.limit_up_pullback,
                'breakout_retest_valid': trend_result.breakout_retest_valid,
                'trend_acceleration': trend_result.trend_acceleration,
                'breakout_reasons': trend_result.breakout_reasons,
                'breakout_risks': trend_result.breakout_risks,
                'volume_status': trend_result.volume_status.value,
                'volume_trend': trend_result.volume_trend,
                'atr_20': trend_result.atr_20,
                'atr_pct': trend_result.atr_pct,
                'volatility_20d': trend_result.volatility_20d,
                'adaptive_bias_threshold': trend_result.adaptive_bias_threshold,
                'adaptive_support_tolerance': trend_result.adaptive_support_tolerance,
                'relative_strength_period': trend_result.relative_strength_period,
                'stock_return_20d': trend_result.stock_return_20d,
                'benchmark_return_20d': trend_result.benchmark_return_20d,
                'sector_return_20d': trend_result.sector_return_20d,
                'stock_vs_benchmark': trend_result.stock_vs_benchmark,
                'stock_vs_sector': trend_result.stock_vs_sector,
                'sector_vs_benchmark': trend_result.sector_vs_benchmark,
                'relative_strength_score': trend_result.relative_strength_score,
                'relative_strength_status': trend_result.relative_strength_status,
                'relative_strength_summary': trend_result.relative_strength_summary,
                'sector_name': trend_result.sector_name,
                'buy_signal': trend_result.buy_signal.value,
                'signal_score': trend_result.signal_score,
                'signal_reasons': trend_result.signal_reasons,
                'risk_factors': trend_result.risk_factors,
                'ideal_buy': trend_result.ideal_buy,
                'secondary_buy': trend_result.secondary_buy,
                'stop_loss': trend_result.stop_loss,
                'take_profit': trend_result.take_profit,
                'risk_reward_ratio': trend_result.risk_reward_ratio,
                'invalidation_condition': trend_result.invalidation_condition,
                'position_note': trend_result.position_note,
                'base_position_pct': trend_result.base_position_pct,
                'market_position_multiplier': trend_result.market_position_multiplier,
                'risk_reward_position_multiplier': trend_result.risk_reward_position_multiplier,
                'single_trade_risk_pct': trend_result.single_trade_risk_pct,
                'max_position_by_risk_pct': trend_result.max_position_by_risk_pct,
                'final_position_pct': trend_result.final_position_pct,
            }
        
        return enhanced
    
    def _describe_volume_ratio(self, volume_ratio: float) -> str:
        """
        量比描述
        
        量比 = 当前成交量 / 过去5日平均成交量
        """
        if volume_ratio < 0.5:
            return "极度萎缩"
        elif volume_ratio < 0.8:
            return "明显萎缩"
        elif volume_ratio < 1.2:
            return "正常"
        elif volume_ratio < 2.0:
            return "温和放量"
        elif volume_ratio < 3.0:
            return "明显放量"
        else:
            return "巨量"
    
    def process_single_stock(
        self, 
        code: str,
        skip_analysis: bool = False
    ) -> Optional[AnalysisResult]:
        """
        处理单只股票的完整流程
        
        包括：
        1. 获取数据
        2. 保存数据
        3. AI 分析
        
        此方法会被线程池调用，需要处理好异常
        
        Args:
            code: 股票代码
            skip_analysis: 是否跳过 AI 分析
            
        Returns:
            AnalysisResult 或 None
        """
        logger.info(f"========== 开始处理 {code} ==========")
        
        try:
            # Step 1: 获取并保存数据
            success, error = self.fetch_and_save_stock_data(code)
            
            if not success:
                logger.warning(f"[{code}] 数据获取失败: {error}")
                # 即使获取失败，也尝试用已有数据分析
            
            # Step 2: AI 分析
            if skip_analysis:
                logger.info(f"[{code}] 跳过 AI 分析（dry-run 模式）")
                return None
            
            result = self.analyze_stock(code)
            
            if result:
                logger.info(
                    f"[{code}] 分析完成: {result.operation_advice}, "
                    f"评分 {result.sentiment_score}"
                )
            
            return result
            
        except Exception as e:
            # 捕获所有异常，确保单股失败不影响整体
            logger.exception(f"[{code}] 处理过程发生未知异常: {e}")
            return None
    
    def run(
        self, 
        stock_codes: Optional[List[str]] = None,
        dry_run: bool = False,
        send_notification: bool = True
    ) -> List[AnalysisResult]:
        """
        运行完整的分析流程
        
        流程：
        1. 获取待分析的股票列表
        2. 使用线程池并发处理
        3. 收集分析结果
        4. 发送通知
        
        Args:
            stock_codes: 股票代码列表（可选，默认使用配置中的自选股）
            dry_run: 是否仅获取数据不分析
            send_notification: 是否发送推送通知
            
        Returns:
            分析结果列表
        """
        start_time = time.time()
        
        # 使用配置中的股票列表
        if stock_codes is None:
            # 基础自选股列表
            codes = set(self.config.stock_list)
            
            # 如果有多用户配置，合并用户关注的股票
            if self.user_manager.has_users():
                user_stocks = self.user_manager.get_all_stocks()
                codes.update(user_stocks)
                logger.info(f"合并用户关注股票后，共 {len(codes)} 只股票")
                
            stock_codes = list(codes)
        
        if not stock_codes:
            logger.error("未配置自选股列表，请在 .env 文件中设置 STOCK_LIST")
            return []
        
        logger.info(f"===== 开始分析 {len(stock_codes)} 只股票 =====")
        logger.info(f"股票列表: {', '.join(stock_codes)}")
        logger.info(f"并发数: {self.max_workers}, 模式: {'仅获取数据' if dry_run else '完整分析'}")
        
        results: List[AnalysisResult] = []
        
        # 使用线程池并发处理
        # 注意：max_workers 设置较低（默认3）以避免触发反爬
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交任务
            future_to_code = {
                executor.submit(
                    self.process_single_stock, 
                    code, 
                    skip_analysis=dry_run
                ): code
                for code in stock_codes
            }
            
            # 收集结果
            for future in as_completed(future_to_code):
                code = future_to_code[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"[{code}] 任务执行失败: {e}")
        
        # 统计
        elapsed_time = time.time() - start_time
        
        # dry-run 模式下，数据获取成功即视为成功
        if dry_run:
            # 检查哪些股票的数据今天已存在
            success_count = sum(1 for code in stock_codes if self.db.has_today_data(code))
            fail_count = len(stock_codes) - success_count
        else:
            success_count = len(results)
            fail_count = len(stock_codes) - success_count
        
        logger.info(f"===== 分析完成 =====")
        logger.info(f"成功: {success_count}, 失败: {fail_count}, 耗时: {elapsed_time:.2f} 秒")
        
        # 发送通知
        if results and send_notification and not dry_run:
            self._send_notifications(results)
        
        return results
    
    def _send_notifications(self, results: List[AnalysisResult]) -> None:
        """
        发送分析结果通知
        
        生成决策仪表盘格式的报告
        
        Args:
            results: 分析结果列表
        """
        try:
            logger.info("生成决策仪表盘日报...")
            
            # 生成决策仪表盘格式的详细日报
            report = self.notifier.generate_dashboard_report(results)
            
            # 保存到本地
            filepath = self.notifier.save_report_to_file(report)
            logger.info(f"决策仪表盘日报已保存: {filepath}")
            
            # 推送通知
            if self.notifier.is_available():
                channels = self.notifier.get_available_channels()

                # 企业微信：只发精简版（平台限制）
                wechat_success = False
                if NotificationChannel.WECHAT in channels:
                    dashboard_content = self.notifier.generate_wechat_dashboard(results)
                    logger.info(f"企业微信仪表盘长度: {len(dashboard_content)} 字符")
                    logger.debug(f"企业微信推送内容:\n{dashboard_content}")
                    wechat_success = self.notifier.send_to_wechat(dashboard_content)

                # 其他渠道：发完整报告（避免自定义 Webhook 被 wechat 截断逻辑污染）
                non_wechat_success = False
                for channel in channels:
                    if channel == NotificationChannel.WECHAT:
                        continue
                    if channel == NotificationChannel.FEISHU:
                        non_wechat_success = self.notifier.send_to_feishu(report) or non_wechat_success
                    elif channel == NotificationChannel.TELEGRAM:
                        non_wechat_success = self.notifier.send_to_telegram(report) or non_wechat_success
                    elif channel == NotificationChannel.EMAIL:
                        # 如果有多用户配置，发送个性化分析报告
                        if self.user_manager.has_users():
                            logger.info("正在发送个性化邮件通知...")
                            for user in self.user_manager.get_users():
                                # 筛选该用户关注的股票结果
                                user_results = [r for r in results if r.code in user.stocks]
                                if not user_results:
                                    continue
                                    
                                logger.info(f"向 {user.name} ({user.email}) 发送报告，包含 {len(user_results)} 只股票")
                                # 生成用户专属报告
                                user_report = self.notifier.generate_dashboard_report(user_results)
                                # 发送邮件
                                self.notifier.send_to_email(user_report, receivers=[user.email])
                            
                            # 同时也向配置文件中的默认收件人（管理员）发送全量报告
                            if self.config.email_receivers:
                                logger.info("正在向默认收件人（管理员）发送全量分析报告...")
                                self.notifier.send_to_email(report)
                                
                            non_wechat_success = True
                        else:
                            # 默认模式：发送给全局配置的收件人
                            non_wechat_success = self.notifier.send_to_email(report) or non_wechat_success
                    elif channel == NotificationChannel.CUSTOM:
                        non_wechat_success = self.notifier.send_to_custom(report) or non_wechat_success
                    else:
                        logger.warning(f"未知通知渠道: {channel}")

                success = wechat_success or non_wechat_success
                if success:
                    logger.info("决策仪表盘推送成功")
                else:
                    logger.warning("决策仪表盘推送失败")
            else:
                logger.info("通知渠道未配置，跳过推送")
                
        except Exception as e:
            logger.error(f"发送通知失败: {e}")

    def run_hot_sector_screening(
        self,
        top_n: int = 3,
        sector_count: int = 5,
        run_llm: bool = False,
        send_notification: bool = True,
    ) -> ScreeningResult:
        """运行热门板块驱动选股，并可选对 Top N 复用精细分析链路。"""
        logger.info(
            f"===== 开始热门板块选股：板块数={sector_count}, Top N={top_n}, "
            f"精细分析={'启用' if run_llm else '关闭'} ====="
        )
        screener = StockScreener(
            daily_fetcher=self.fetcher_manager,
            sector_fetcher=self.akshare_fetcher,
            trend_analyzer=self.trend_analyzer,
        )
        screening_result = screener.screen_hot_sectors(
            sector_count=sector_count,
            top_n=top_n,
        )

        if run_llm and screening_result.selected:
            logger.info(f"对 Top {len(screening_result.selected)} 候选股执行精细分析")
            for candidate in screening_result.selected:
                detail = self.process_single_stock(candidate.code, skip_analysis=False)
                if detail:
                    screening_result.detailed_results.append(detail)

        report = screening_result.format_report()
        date_str = datetime.now().strftime('%Y%m%d')
        filepath = self.notifier.save_report_to_file(report, f"hot_sector_screening_{date_str}.md")
        logger.info(f"热门板块选股报告已保存: {filepath}")

        if send_notification and self.notifier.is_available():
            success = self.notifier.send(report)
            if success:
                logger.info("热门板块选股报告推送成功")
            else:
                logger.warning("热门板块选股报告推送失败")

        logger.info(
            f"热门板块选股完成：有效候选 {len(screening_result.candidates)}，"
            f"过滤 {len(screening_result.filtered)}，入选 {len(screening_result.selected)}"
        )
        return screening_result

    def run_theme_radar(
        self,
        theme_count: int = 5,
        leader_top_n: int = 3,
        lookback_days: int = 7,
        include_detail_analysis: bool = True,
        include_concepts: bool = True,
        send_notification: bool = True,
    ):
        """运行热点主题 LLM 雷达，并可选复用 Top 个股精细分析链路。"""
        logger.info(
            f"===== 开始热点主题雷达：主题数={theme_count}, Top N={leader_top_n}, "
            f"回看={lookback_days}日, 精细分析={'启用' if include_detail_analysis else '关闭'} ====="
        )
        radar = ThemeRadar(
            market_analyzer=MarketAnalyzer(search_service=self.search_service, analyzer=self.analyzer),
            search_service=self.search_service,
            sector_fetcher=self.akshare_fetcher,
            daily_fetcher=self.fetcher_manager,
            trend_analyzer=self.trend_analyzer,
            analyzer=self.analyzer,
            detail_analyzer=lambda code: self.process_single_stock(code, skip_analysis=False),
        )
        result = radar.run(
            theme_count=theme_count,
            leader_top_n=leader_top_n,
            lookback_days=lookback_days,
            include_detail_analysis=include_detail_analysis,
            include_concepts=include_concepts,
            save_history=True,
        )

        report = result.report_markdown or radar.format_report(result)
        date_str = datetime.now().strftime('%Y%m%d')
        filepath = self.notifier.save_report_to_file(report, f"theme_radar_{date_str}.md")
        logger.info(f"热点主题雷达报告已保存: {filepath}")

        if send_notification and self.notifier.is_available():
            success = self.notifier.send(report)
            if success:
                logger.info("热点主题雷达报告推送成功")
            else:
                logger.warning("热点主题雷达报告推送失败")

        logger.info(
            f"热点主题雷达完成：主题 {len(result.themes)}，候选龙头 {len(result.selected_stocks)}，"
            f"历史文件 {result.history_path or '未保存'}"
        )
        return result

    def run_theme_backtest(self, history_path: str = "data/theme_radar", send_notification: bool = False):
        """运行主题/龙头最小回测并保存 Markdown 报告。"""
        backtester = ThemeBacktester()
        result = backtester.run_backtest(history_path)
        report = backtester.format_report(result)
        date_str = datetime.now().strftime('%Y%m%d')
        filepath = self.notifier.save_report_to_file(report, f"theme_backtest_{date_str}.md")
        logger.info(f"热点主题回测报告已保存: {filepath}")
        if send_notification and self.notifier.is_available():
            self.notifier.send(report)
        return result


def parse_arguments() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='A股自选股智能分析系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python main.py                    # 正常运行
  python main.py --debug            # 调试模式
  python main.py --dry-run          # 仅获取数据，不进行 AI 分析
  python main.py --stocks 600519,000001  # 指定分析特定股票
  python main.py --no-notify        # 不发送推送通知
  python main.py --schedule         # 启用定时任务模式
  python main.py --market-review    # 仅运行大盘复盘
  python main.py --screen-hot-sectors --screen-no-llm  # 热门板块规则选股
  python main.py --theme-radar --theme-no-llm-detail   # 热点主题雷达
  python main.py --theme-backtest   # 主题雷达历史最小回测
        '''
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='启用调试模式，输出详细日志'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅获取数据，不进行 AI 分析'
    )
    
    parser.add_argument(
        '--stocks',
        type=str,
        help='指定要分析的股票代码，逗号分隔（覆盖配置文件）'
    )
    
    parser.add_argument(
        '--no-notify',
        action='store_true',
        help='不发送推送通知'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='并发线程数（默认使用配置值）'
    )
    
    parser.add_argument(
        '--schedule',
        action='store_true',
        help='启用定时任务模式，每日定时执行'
    )
    
    parser.add_argument(
        '--market-review',
        action='store_true',
        help='仅运行大盘复盘分析'
    )
    
    parser.add_argument(
        '--no-market-review',
        action='store_true',
        help='跳过大盘复盘分析'
    )

    parser.add_argument(
        '--screen-hot-sectors',
        action='store_true',
        help='启用热门板块驱动选股模式'
    )

    parser.add_argument(
        '--screen-top-n',
        type=int,
        default=3,
        help='热门板块选股后进入精细分析的 Top N，默认3'
    )

    parser.add_argument(
        '--screen-sector-count',
        type=int,
        default=5,
        help='用于粗筛的热门板块数量，默认5'
    )

    parser.add_argument(
        '--screen-no-llm',
        action='store_true',
        help='只输出规则层排序，不运行 Top N 精细 LLM 报告'
    )

    parser.add_argument(
        '--theme-radar',
        action='store_true',
        help='启用热点主题雷达模式'
    )

    parser.add_argument(
        '--theme-top-n',
        type=int,
        default=3,
        help='热点主题雷达进入精细分析的候选龙头数量，默认3'
    )

    parser.add_argument(
        '--theme-count',
        type=int,
        default=5,
        help='热点主题雷达输出主题数量，默认5'
    )

    parser.add_argument(
        '--theme-lookback-days',
        type=int,
        default=7,
        help='热点主题新闻与主题回看天数，默认7'
    )

    parser.add_argument(
        '--theme-no-llm-detail',
        action='store_true',
        help='只输出主题和规则层候选，不运行 Top 个股精细 LLM'
    )

    parser.add_argument(
        '--theme-include-concepts',
        action='store_true',
        default=True,
        help='热点主题雷达包含概念板块，默认启用'
    )

    parser.add_argument(
        '--theme-backtest',
        action='store_true',
        help='对已保存的主题雷达历史运行最小回测'
    )
    
    return parser.parse_args()


def run_market_review(
    notifier: NotificationService,
    analyzer=None,
    search_service=None,
    send_notification: bool = True
) -> Optional[str]:
    """
    执行大盘复盘分析

    Args:
        notifier: 通知服务
        analyzer: AI分析器（可选）
        search_service: 搜索服务（可选）
        send_notification: 是否推送通知

    Returns:
        复盘报告文本
    """
    logger.info("开始执行大盘复盘分析...")
    
    try:
        market_analyzer = MarketAnalyzer(
            search_service=search_service,
            analyzer=analyzer
        )
        
        # 执行复盘
        review_report = market_analyzer.run_daily_review()
        
        if review_report:
            # 保存报告到文件
            date_str = datetime.now().strftime('%Y%m%d')
            report_filename = f"market_review_{date_str}.md"
            filepath = notifier.save_report_to_file(
                f"# 🎯 大盘复盘\n\n{review_report}", 
                report_filename
            )
            logger.info(f"大盘复盘报告已保存: {filepath}")
            
            # 推送通知
            if send_notification and notifier.is_available():
                # 添加标题
                report_content = f"🎯 大盘复盘\n\n{review_report}"

                success = notifier.send(report_content)
                if success:
                    logger.info("大盘复盘推送成功")
                else:
                    logger.warning("大盘复盘推送失败")
            elif not send_notification:
                logger.info("已禁用通知，跳过大盘复盘推送")

            return review_report
        
    except Exception as e:
        logger.error(f"大盘复盘分析失败: {e}")
    
    return None


def run_full_analysis(
    config: Config,
    args: argparse.Namespace,
    stock_codes: Optional[List[str]] = None
):
    """
    执行完整的分析流程（个股 + 大盘复盘）
    
    这是定时任务调用的主函数
    """
    try:
        # 创建调度器
        pipeline = StockAnalysisPipeline(
            config=config,
            max_workers=args.workers
        )
        
        # 1. 运行个股分析
        results = pipeline.run(
            stock_codes=stock_codes,
            dry_run=args.dry_run,
            send_notification=not args.no_notify
        )
        
        # 2. 运行大盘复盘（如果启用且不是仅个股模式）
        market_report = ""
        if config.market_review_enabled and not args.no_market_review and not args.dry_run:
            # 只调用一次，并获取结果
            review_result = run_market_review(
                notifier=pipeline.notifier,
                analyzer=pipeline.analyzer,
                search_service=pipeline.search_service,
                send_notification=not args.no_notify
            )
            # 如果有结果，赋值给 market_report 用于后续飞书文档生成
            if review_result:
                market_report = review_result
        
        # 输出摘要
        if results:
            logger.info("\n===== 分析结果摘要 =====")
            for r in sorted(results, key=lambda x: x.sentiment_score, reverse=True):
                emoji = r.get_emoji()
                logger.info(
                    f"{emoji} {r.name}({r.code}): {r.operation_advice} | "
                    f"评分 {r.sentiment_score} | {r.trend_prediction}"
                )
        
        logger.info("\n任务执行完成")

        # === 新增：生成飞书云文档 ===
        try:
            feishu_doc = FeishuDocManager()
            if feishu_doc.is_configured() and (results or market_report):
                logger.info("正在创建飞书云文档...")

                # 1. 准备标题 "01-01 13:01大盘复盘"
                tz_cn = timezone(timedelta(hours=8))
                now = datetime.now(tz_cn)
                doc_title = f"{now.strftime('%Y-%m-%d %H:%M')} 大盘复盘"

                # 2. 准备内容 (拼接个股分析和大盘复盘)
                full_content = ""

                # 添加大盘复盘内容（如果有）
                if market_report:
                    full_content += f"# 📈 大盘复盘\n\n{market_report}\n\n---\n\n"

                # 添加个股决策仪表盘（使用 NotificationService 生成）
                if results:
                    dashboard_content = pipeline.notifier.generate_dashboard_report(results)
                    full_content += f"# 🚀 个股决策仪表盘\n\n{dashboard_content}"

                # 3. 创建文档
                doc_url = feishu_doc.create_daily_doc(doc_title, full_content)
                if doc_url:
                    logger.info(f"飞书云文档创建成功: {doc_url}")
                    if not args.no_notify:
                        pipeline.notifier.send(f"[{now.strftime('%Y-%m-%d %H:%M')}] 复盘文档创建成功: {doc_url}")
                    else:
                        logger.info("已禁用通知，跳过飞书文档链接推送")

        except Exception as e:
            logger.error(f"飞书文档生成失败: {e}")
        
    except Exception as e:
        logger.exception(f"分析流程执行失败: {e}")


def main() -> int:
    """
    主入口函数
    
    Returns:
        退出码（0 表示成功）
    """
    # 解析命令行参数
    args = parse_arguments()
    
    # 加载配置（在设置日志前加载，以获取日志目录）
    config = get_config()
    
    # 配置日志（输出到控制台和文件）
    setup_logging(debug=args.debug, log_dir=config.log_dir)
    
    logger.info("=" * 60)
    logger.info("A股自选股智能分析系统 启动")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # 验证配置
    warnings = config.validate()
    for warning in warnings:
        logger.warning(warning)
    
    # 解析股票列表
    stock_codes = None
    if args.stocks:
        stock_codes = [code.strip() for code in args.stocks.split(',') if code.strip()]
        logger.info(f"使用命令行指定的股票列表: {stock_codes}")
    
    try:
        # 模式0: 热点主题 LLM 雷达
        if getattr(args, "theme_radar", False):
            logger.info("模式: 热点主题 LLM 雷达")
            pipeline = StockAnalysisPipeline(
                config=config,
                max_workers=args.workers
            )
            pipeline.run_theme_radar(
                theme_count=args.theme_count,
                leader_top_n=args.theme_top_n,
                lookback_days=args.theme_lookback_days,
                include_detail_analysis=not args.theme_no_llm_detail and not args.dry_run,
                include_concepts=args.theme_include_concepts,
                send_notification=not args.no_notify,
            )
            return 0

        # 模式0.5: 热点主题历史回测
        if getattr(args, "theme_backtest", False):
            logger.info("模式: 热点主题历史回测")
            pipeline = StockAnalysisPipeline(
                config=config,
                max_workers=args.workers
            )
            pipeline.run_theme_backtest(send_notification=not args.no_notify)
            return 0

        # 模式0: 热门板块驱动选股
        if args.screen_hot_sectors:
            logger.info("模式: 热门板块驱动选股")
            pipeline = StockAnalysisPipeline(
                config=config,
                max_workers=args.workers
            )
            pipeline.run_hot_sector_screening(
                top_n=args.screen_top_n,
                sector_count=args.screen_sector_count,
                run_llm=not args.screen_no_llm and not args.dry_run,
                send_notification=not args.no_notify,
            )
            return 0

        # 模式1: 仅大盘复盘
        if args.market_review:
            logger.info("模式: 仅大盘复盘")
            notifier = NotificationService()
            
            # 初始化搜索服务和分析器（如果有配置）
            search_service = None
            analyzer = None
            
            if config.tavily_api_keys or config.serpapi_keys:
                search_service = SearchService(
                    tavily_keys=config.tavily_api_keys,
                    serpapi_keys=config.serpapi_keys
                )
            
            if config.openai_api_key and config.openai_base_url and config.openai_model:
                analyzer = OpenAIAnalyzer()

            run_market_review(
                notifier,
                analyzer,
                search_service,
                send_notification=not args.no_notify
            )
            return 0
        
        # 模式2: 定时任务模式
        if args.schedule or config.schedule_enabled:
            logger.info("模式: 定时任务")
            logger.info(f"每日执行时间: {config.schedule_time}")
            
            from scheduler import run_with_schedule
            
            def scheduled_task():
                run_full_analysis(config, args, stock_codes)
            
            run_with_schedule(
                task=scheduled_task,
                schedule_time=config.schedule_time,
                run_immediately=True  # 启动时先执行一次
            )
            return 0
        
        # 模式3: 正常单次运行
        run_full_analysis(config, args, stock_codes)
        
        logger.info("\n程序执行完成")
        return 0
        
    except KeyboardInterrupt:
        logger.info("\n用户中断，程序退出")
        return 130
        
    except Exception as e:
        logger.exception(f"程序执行失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
