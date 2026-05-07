# -*- coding: utf-8 -*-
"""
===================================
趋势交易分析器 - 基于用户交易理念
===================================

交易理念核心原则：
1. 严进策略 - 不追高，追求每笔交易成功率
2. 趋势交易 - MA5>MA10>MA20 多头排列，顺势而为
3. 效率优先 - 关注筹码结构好的股票
4. 买点偏好 - 在 MA5/MA10 附近回踩买入

技术标准：
- 多头排列：MA5 > MA10 > MA20
- 乖离率：(Close - MA5) / MA5 低于自适应纪律线（默认最高 5%）
- 量能形态：缩量回调优先
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum

import pandas as pd

logger = logging.getLogger(__name__)


class TrendStatus(Enum):
    """趋势状态枚举"""
    STRONG_BULL = "强势多头"      # MA5 > MA10 > MA20，且间距扩大
    BULL = "多头排列"             # MA5 > MA10 > MA20
    WEAK_BULL = "弱势多头"        # MA5 > MA10，但 MA10 < MA20
    CONSOLIDATION = "盘整"        # 均线缠绕
    WEAK_BEAR = "弱势空头"        # MA5 < MA10，但 MA10 > MA20
    BEAR = "空头排列"             # MA5 < MA10 < MA20
    STRONG_BEAR = "强势空头"      # MA5 < MA10 < MA20，且间距扩大


class VolumeStatus(Enum):
    """量能状态枚举"""
    HEAVY_VOLUME_UP = "放量上涨"       # 量价齐升
    HEAVY_VOLUME_DOWN = "放量下跌"     # 放量杀跌
    SHRINK_VOLUME_UP = "缩量上涨"      # 无量上涨
    SHRINK_VOLUME_DOWN = "缩量回调"    # 缩量回调（好）
    NORMAL = "量能正常"


class BuySignal(Enum):
    """买入信号枚举"""
    STRONG_BUY = "强烈买入"       # 多条件满足
    BUY = "买入"                  # 基本条件满足
    HOLD = "持有"                 # 已持有可继续
    WAIT = "观望"                 # 等待更好时机
    SELL = "卖出"                 # 趋势转弱
    STRONG_SELL = "强烈卖出"      # 趋势破坏


@dataclass
class TrendAnalysisResult:
    """趋势分析结果"""
    code: str
    
    # 趋势判断
    trend_status: TrendStatus = TrendStatus.CONSOLIDATION
    ma_alignment: str = ""           # 均线排列描述
    trend_strength: float = 0.0      # 趋势强度 0-100
    
    # 均线数据
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma60: float = 0.0
    current_price: float = 0.0
    
    # 乖离率（与 MA5 的偏离度）
    bias_ma5: float = 0.0            # (Close - MA5) / MA5 * 100
    bias_ma10: float = 0.0
    bias_ma20: float = 0.0
    
    # 中期趋势
    ma60_trend: str = ""              # MA60 趋势描述
    price_vs_ma60: float = 0.0        # 现价相对 MA60 的偏离度
    ma60_slope: float = 0.0           # MA60 近20日斜率百分比
    medium_trend_risk: bool = False   # 中期趋势是否压制买入

    # 量能分析
    volume_status: VolumeStatus = VolumeStatus.NORMAL
    volume_ratio_5d: float = 0.0     # 当日成交量/5日均量
    volume_trend: str = ""           # 量能趋势描述

    # 波动率自适应参数
    atr_20: float = 0.0               # 20日平均真实波幅
    atr_pct: float = 0.0              # ATR / 现价 * 100
    volatility_20d: float = 0.0       # 近20日收益率标准差（%）
    adaptive_bias_threshold: float = 5.0
    adaptive_support_tolerance: float = 0.02

    # 相对强弱（RS）
    relative_strength_period: int = 20
    stock_return_20d: float = 0.0
    benchmark_return_20d: float = 0.0
    sector_return_20d: float = 0.0
    stock_vs_benchmark: float = 0.0
    stock_vs_sector: float = 0.0
    sector_vs_benchmark: float = 0.0
    relative_strength_score: int = 0
    relative_strength_status: str = "未提供基准/行业数据"
    relative_strength_summary: str = ""
    sector_name: str = ""
    
    # 支撑压力
    support_ma5: bool = False        # MA5 是否构成支撑
    support_ma10: bool = False       # MA10 是否构成支撑
    ma5_touch_reclaim: bool = False  # 盘中触及/跌破 MA5 后收回
    ma10_touch_reclaim: bool = False # 盘中触及/跌破 MA10 后收回
    bullish_candle: bool = False     # 当日阳线确认
    lower_shadow_ratio: float = 0.0  # 下影线占全日振幅比例（%）
    ma5_hold_days: int = 0           # 连续未跌破 MA5 的天数
    ma10_hold_days: int = 0          # 连续未跌破 MA10 的天数
    ma20_breakdown: bool = False     # 收盘跌破 MA20
    support_confirmation: str = ""
    resistance_levels: List[float] = field(default_factory=list)
    support_levels: List[float] = field(default_factory=list)
    
    # 买入信号
    buy_signal: BuySignal = BuySignal.WAIT
    signal_score: int = 0            # 综合评分 0-100
    signal_reasons: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)

    # 规则层交易计划
    ideal_buy: float = 0.0
    secondary_buy: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    risk_reward_ratio: float = 0.0
    invalidation_condition: str = ""
    position_note: str = ""
    base_position_pct: float = 0.0
    market_position_multiplier: float = 0.0
    risk_reward_position_multiplier: float = 0.0
    single_trade_risk_pct: float = 0.0
    max_position_by_risk_pct: float = 0.0
    final_position_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'code': self.code,
            'trend_status': self.trend_status.value,
            'ma_alignment': self.ma_alignment,
            'trend_strength': self.trend_strength,
            'ma5': self.ma5,
            'ma10': self.ma10,
            'ma20': self.ma20,
            'ma60': self.ma60,
            'current_price': self.current_price,
            'bias_ma5': self.bias_ma5,
            'bias_ma10': self.bias_ma10,
            'bias_ma20': self.bias_ma20,
            'price_vs_ma60': self.price_vs_ma60,
            'ma60_slope': self.ma60_slope,
            'ma60_trend': self.ma60_trend,
            'medium_trend_risk': self.medium_trend_risk,
            'volume_status': self.volume_status.value,
            'volume_ratio_5d': self.volume_ratio_5d,
            'volume_trend': self.volume_trend,
            'atr_20': self.atr_20,
            'atr_pct': self.atr_pct,
            'volatility_20d': self.volatility_20d,
            'adaptive_bias_threshold': self.adaptive_bias_threshold,
            'adaptive_support_tolerance': self.adaptive_support_tolerance,
            'relative_strength_period': self.relative_strength_period,
            'stock_return_20d': self.stock_return_20d,
            'benchmark_return_20d': self.benchmark_return_20d,
            'sector_return_20d': self.sector_return_20d,
            'stock_vs_benchmark': self.stock_vs_benchmark,
            'stock_vs_sector': self.stock_vs_sector,
            'sector_vs_benchmark': self.sector_vs_benchmark,
            'relative_strength_score': self.relative_strength_score,
            'relative_strength_status': self.relative_strength_status,
            'relative_strength_summary': self.relative_strength_summary,
            'sector_name': self.sector_name,
            'support_ma5': self.support_ma5,
            'support_ma10': self.support_ma10,
            'ma5_touch_reclaim': self.ma5_touch_reclaim,
            'ma10_touch_reclaim': self.ma10_touch_reclaim,
            'bullish_candle': self.bullish_candle,
            'lower_shadow_ratio': self.lower_shadow_ratio,
            'ma5_hold_days': self.ma5_hold_days,
            'ma10_hold_days': self.ma10_hold_days,
            'ma20_breakdown': self.ma20_breakdown,
            'support_confirmation': self.support_confirmation,
            'support_levels': self.support_levels,
            'resistance_levels': self.resistance_levels,
            'buy_signal': self.buy_signal.value,
            'signal_score': self.signal_score,
            'signal_reasons': self.signal_reasons,
            'risk_factors': self.risk_factors,
            'ideal_buy': self.ideal_buy,
            'secondary_buy': self.secondary_buy,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'risk_reward_ratio': self.risk_reward_ratio,
            'invalidation_condition': self.invalidation_condition,
            'position_note': self.position_note,
            'base_position_pct': self.base_position_pct,
            'market_position_multiplier': self.market_position_multiplier,
            'risk_reward_position_multiplier': self.risk_reward_position_multiplier,
            'single_trade_risk_pct': self.single_trade_risk_pct,
            'max_position_by_risk_pct': self.max_position_by_risk_pct,
            'final_position_pct': self.final_position_pct,
        }


class StockTrendAnalyzer:
    """
    股票趋势分析器
    
    基于用户交易理念实现：
    1. 趋势判断 - MA5>MA10>MA20 多头排列
    2. 乖离率检测 - 不追高，偏离 MA5 超过自适应纪律线不买
    3. 量能分析 - 偏好缩量回调
    4. 买点识别 - 回踩 MA5/MA10 支撑
    """
    
    # 交易参数配置
    BIAS_THRESHOLD = 5.0        # 乖离率阈值（%），超过此值不买入
    ATR_PERIOD = 20
    ATR_BIAS_MULTIPLIER = 1.2
    ATR_STOP_MULTIPLIER = 1.5
    VOLUME_SHRINK_RATIO = 0.7   # 缩量判断阈值（当日量/5日均量）
    VOLUME_HEAVY_RATIO = 1.5    # 放量判断阈值
    MA_SUPPORT_TOLERANCE = 0.02  # MA 支撑判断容忍度（2%）
    MIN_SUPPORT_TOLERANCE = 0.01  # 低波动标的支撑容忍度下限（1%）
    LOWER_SHADOW_CONFIRM_RATIO = 35.0
    SUPPORT_HOLD_DAYS = 2
    RELATIVE_STRENGTH_PERIOD = 20
    RS_OUTPERFORM_THRESHOLD = 3.0
    RS_UNDERPERFORM_THRESHOLD = -3.0
    RS_SECTOR_THRESHOLD = 2.0
    ACCOUNT_RISK_BUDGET_PCT = 1.0  # 单票单次交易最大组合亏损预算（%）
    MAX_POSITION_PCT = 30.0
    MARKET_POSITION_MULTIPLIERS = {
        "强势": 1.0,
        "偏强": 0.8,
        "震荡": 0.5,
        "偏弱": 0.3,
        "极弱": 0.0,
    }
    
    def __init__(self):
        """初始化分析器"""
        pass
    
    def analyze(
        self,
        df: pd.DataFrame,
        code: str,
        benchmark_df: Optional[pd.DataFrame] = None,
        sector_df: Optional[pd.DataFrame] = None,
        sector_name: str = "",
    ) -> TrendAnalysisResult:
        """
        分析股票趋势
        
        Args:
            df: 包含 OHLCV 数据的 DataFrame
            code: 股票代码
            benchmark_df: 可选的大盘/宽基指数日线数据，用于计算相对大盘强弱
            sector_df: 可选的行业/板块日线数据，用于计算相对行业强弱
            sector_name: 可选的行业/板块名称
            
        Returns:
            TrendAnalysisResult 分析结果
        """
        result = TrendAnalysisResult(code=code)
        
        if df is None or df.empty or len(df) < 20:
            logger.warning(f"{code} 数据不足，无法进行趋势分析")
            result.risk_factors.append("数据不足，无法完成分析")
            return result
        
        # 确保数据按日期排序
        df = df.sort_values('date').reset_index(drop=True)
        
        # 计算均线
        df = self._calculate_mas(df)
        
        # 获取最新数据
        latest = df.iloc[-1]
        result.current_price = float(latest['close'])
        result.ma5 = float(latest['MA5'])
        result.ma10 = float(latest['MA10'])
        result.ma20 = float(latest['MA20'])
        result.ma60 = float(latest.get('MA60', 0))
        self._analyze_volatility(df, result)
        
        # 1. 趋势判断
        self._analyze_trend(df, result)
        self._analyze_medium_trend(df, result)

        # 2. 乖离率计算
        self._calculate_bias(result)

        # 2.5 相对强弱分析
        self._analyze_relative_strength(
            df,
            result,
            benchmark_df=benchmark_df,
            sector_df=sector_df,
            sector_name=sector_name,
        )
        
        # 3. 量能分析
        self._analyze_volume(df, result)
        
        # 4. 支撑压力分析
        self._analyze_support_resistance(df, result)

        # 5. 规则层交易计划
        self._calculate_trade_plan(df, result)

        # 6. 生成买入信号
        self._generate_signal(result)

        # 7. 默认按中性市场环境生成规则层仓位，主流程可在注入大盘环境后重算
        self.apply_position_model(result)
        
        return result

    def apply_position_model(
        self,
        result: TrendAnalysisResult,
        market_status: Optional[str] = None,
        account_risk_budget_pct: Optional[float] = None,
    ) -> TrendAnalysisResult:
        """根据系统评分、大盘环境、盈亏比和单票风险预算计算建议仓位。"""
        market_status = market_status or "震荡"
        risk_budget = account_risk_budget_pct or self.ACCOUNT_RISK_BUDGET_PCT

        result.base_position_pct = self._score_to_base_position(result.signal_score)
        result.market_position_multiplier = self.MARKET_POSITION_MULTIPLIERS.get(market_status, 0.5)
        result.risk_reward_position_multiplier = self._risk_reward_position_multiplier(result.risk_reward_ratio)

        raw_position = (
            result.base_position_pct
            * result.market_position_multiplier
            * result.risk_reward_position_multiplier
        )

        result.single_trade_risk_pct = 0.0
        result.max_position_by_risk_pct = 0.0
        if result.ideal_buy > result.stop_loss > 0:
            result.single_trade_risk_pct = round((result.ideal_buy - result.stop_loss) / result.ideal_buy * 100, 2)
            if result.single_trade_risk_pct > 0 and risk_budget > 0:
                result.max_position_by_risk_pct = round(risk_budget / result.single_trade_risk_pct * 100, 2)

        if raw_position <= 0:
            result.final_position_pct = 0.0
        elif result.max_position_by_risk_pct > 0:
            result.final_position_pct = round(min(raw_position, result.max_position_by_risk_pct, self.MAX_POSITION_PCT), 1)
        else:
            result.final_position_pct = 0.0

        result.position_note = self._build_position_note(result, market_status, raw_position)
        return result

    def _score_to_base_position(self, score: int) -> float:
        if score >= 85:
            return 30.0
        if score >= 75:
            return 20.0
        if score >= 65:
            return 10.0
        return 0.0

    def _risk_reward_position_multiplier(self, risk_reward_ratio: float) -> float:
        if risk_reward_ratio >= 2.0:
            return 1.0
        if risk_reward_ratio >= 1.8:
            return 0.8
        if risk_reward_ratio >= 1.2:
            return 0.4
        return 0.0

    def _build_position_note(
        self,
        result: TrendAnalysisResult,
        market_status: str,
        raw_position: float,
    ) -> str:
        if result.base_position_pct <= 0:
            return "评分未达到开仓阈值，规则仓位为0%"
        if result.market_position_multiplier <= 0:
            return f"市场环境{market_status}，规则仓位为0%"
        if result.risk_reward_position_multiplier <= 0:
            return "盈亏比不足，规则仓位为0%"
        if result.max_position_by_risk_pct <= 0:
            return "缺少有效止损或风险距离，规则仓位为0%"

        cap_text = ""
        if result.final_position_pct < raw_position:
            cap_text = f"，受单票风险预算限制（上限{result.max_position_by_risk_pct:.1f}%）"

        return (
            f"规则建议仓位{result.final_position_pct:.1f}%"
            f"（基础{result.base_position_pct:.0f}% × 市场{result.market_position_multiplier:.1f}"
            f" × 盈亏比{result.risk_reward_position_multiplier:.1f}{cap_text}）"
        )
    
    def _calculate_mas(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算均线和波动率指标。"""
        df = df.copy()
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        if len(df) >= 60:
            df['MA60'] = df['close'].rolling(window=60).mean()
        else:
            df['MA60'] = df['MA20']  # 数据不足时使用 MA20 替代

        prev_close = df['close'].shift(1)
        true_ranges = pd.concat(
            [
                df['high'] - df['low'],
                (df['high'] - prev_close).abs(),
                (df['low'] - prev_close).abs(),
            ],
            axis=1,
        )
        df['TR'] = true_ranges.max(axis=1)
        df['ATR20'] = df['TR'].rolling(window=self.ATR_PERIOD).mean()
        df['VOLATILITY20'] = df['close'].pct_change().rolling(window=20).std() * 100
        return df

    @staticmethod
    def _to_float(value: Any) -> float:
        """Safely coerce pandas/numeric values to a plain float."""
        try:
            if pd.isna(value):
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _analyze_volatility(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """根据 ATR 生成自适应乖离阈值、支撑容忍度和止损参考。"""
        latest = df.iloc[-1]
        result.atr_20 = self._to_float(latest.get('ATR20'))
        result.volatility_20d = self._to_float(latest.get('VOLATILITY20'))

        if result.current_price > 0 and result.atr_20 > 0:
            result.atr_pct = round(result.atr_20 / result.current_price * 100, 2)

        if result.atr_pct > 0:
            result.adaptive_bias_threshold = round(
                min(self.BIAS_THRESHOLD, self.ATR_BIAS_MULTIPLIER * result.atr_pct),
                2,
            )
            result.adaptive_support_tolerance = round(
                max(self.MIN_SUPPORT_TOLERANCE, result.atr_pct / 100 * 0.5),
                4,
            )
        else:
            result.adaptive_bias_threshold = self.BIAS_THRESHOLD
            result.adaptive_support_tolerance = self.MA_SUPPORT_TOLERANCE

    def _analyze_relative_strength(
        self,
        df: pd.DataFrame,
        result: TrendAnalysisResult,
        benchmark_df: Optional[pd.DataFrame] = None,
        sector_df: Optional[pd.DataFrame] = None,
        sector_name: str = "",
    ) -> None:
        """计算个股相对大盘/行业的 20 日强弱。"""
        result.relative_strength_period = self.RELATIVE_STRENGTH_PERIOD
        result.sector_name = sector_name or ""

        stock_return = self._period_return_pct(df, self.RELATIVE_STRENGTH_PERIOD)
        if stock_return is None:
            result.relative_strength_status = "个股历史数据不足，无法计算RS"
            result.relative_strength_summary = result.relative_strength_status
            return

        result.stock_return_20d = round(stock_return, 2)
        score = 0
        notes = [f"个股近{self.RELATIVE_STRENGTH_PERIOD}日收益{result.stock_return_20d:+.2f}%"]

        benchmark_return = self._period_return_pct(benchmark_df, self.RELATIVE_STRENGTH_PERIOD)
        if benchmark_return is not None:
            result.benchmark_return_20d = round(benchmark_return, 2)
            result.stock_vs_benchmark = round(stock_return - benchmark_return, 2)
            notes.append(f"相对大盘{result.stock_vs_benchmark:+.2f}pct")
            if result.stock_vs_benchmark >= self.RS_OUTPERFORM_THRESHOLD:
                score += 5
            elif result.stock_vs_benchmark <= self.RS_UNDERPERFORM_THRESHOLD:
                score -= 5

        sector_return = self._period_return_pct(sector_df, self.RELATIVE_STRENGTH_PERIOD)
        if sector_return is not None:
            result.sector_return_20d = round(sector_return, 2)
            result.stock_vs_sector = round(stock_return - sector_return, 2)
            sector_label = result.sector_name or "行业"
            notes.append(f"相对{sector_label}{result.stock_vs_sector:+.2f}pct")
            if result.stock_vs_sector >= self.RS_SECTOR_THRESHOLD:
                score += 3
            elif result.stock_vs_sector <= -self.RS_SECTOR_THRESHOLD:
                score -= 4

            if benchmark_return is not None:
                result.sector_vs_benchmark = round(sector_return - benchmark_return, 2)
                notes.append(f"{sector_label}相对大盘{result.sector_vs_benchmark:+.2f}pct")
                if result.sector_vs_benchmark >= self.RS_SECTOR_THRESHOLD:
                    score += 2
                elif result.sector_vs_benchmark <= -self.RS_SECTOR_THRESHOLD:
                    score -= 2

        result.relative_strength_score = max(-10, min(10, score))

        if benchmark_return is None and sector_return is None:
            result.relative_strength_status = "未提供基准/行业数据"
        elif result.relative_strength_score >= 6:
            result.relative_strength_status = "明显强于基准/行业"
        elif result.relative_strength_score >= 2:
            result.relative_strength_status = "相对偏强"
        elif result.relative_strength_score <= -6:
            result.relative_strength_status = "明显弱于基准/行业"
        elif result.relative_strength_score <= -2:
            result.relative_strength_status = "相对偏弱"
        else:
            result.relative_strength_status = "相对中性"

        result.relative_strength_summary = "；".join(notes)

    def _period_return_pct(self, df: Optional[pd.DataFrame], period: int) -> Optional[float]:
        """计算最近 period 个交易日的收盘收益率。"""
        if df is None or df.empty or 'close' not in df.columns or len(df) <= period:
            return None

        working = df.copy()
        if 'date' in working.columns:
            working = working.sort_values('date')

        latest_close = self._to_float(working['close'].iloc[-1])
        base_close = self._to_float(working['close'].iloc[-period - 1])
        if latest_close <= 0 or base_close <= 0:
            return None
        return (latest_close - base_close) / base_close * 100
    
    def _analyze_trend(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        分析趋势状态
        
        核心逻辑：判断均线排列和趋势强度
        """
        ma5, ma10, ma20 = result.ma5, result.ma10, result.ma20
        
        # 判断均线排列
        if ma5 > ma10 > ma20:
            # 检查间距是否在扩大（强势）
            prev = df.iloc[-5] if len(df) >= 5 else df.iloc[-1]
            prev_spread = (prev['MA5'] - prev['MA20']) / prev['MA20'] * 100 if prev['MA20'] > 0 else 0
            curr_spread = (ma5 - ma20) / ma20 * 100 if ma20 > 0 else 0
            
            if curr_spread > prev_spread and curr_spread > 5:
                result.trend_status = TrendStatus.STRONG_BULL
                result.ma_alignment = "强势多头排列，均线发散上行"
                result.trend_strength = 90
            else:
                result.trend_status = TrendStatus.BULL
                result.ma_alignment = "多头排列 MA5>MA10>MA20"
                result.trend_strength = 75
                
        elif ma5 > ma10 and ma10 <= ma20:
            result.trend_status = TrendStatus.WEAK_BULL
            result.ma_alignment = "弱势多头，MA5>MA10 但 MA10≤MA20"
            result.trend_strength = 55
            
        elif ma5 < ma10 < ma20:
            prev = df.iloc[-5] if len(df) >= 5 else df.iloc[-1]
            prev_spread = (prev['MA20'] - prev['MA5']) / prev['MA5'] * 100 if prev['MA5'] > 0 else 0
            curr_spread = (ma20 - ma5) / ma5 * 100 if ma5 > 0 else 0
            
            if curr_spread > prev_spread and curr_spread > 5:
                result.trend_status = TrendStatus.STRONG_BEAR
                result.ma_alignment = "强势空头排列，均线发散下行"
                result.trend_strength = 10
            else:
                result.trend_status = TrendStatus.BEAR
                result.ma_alignment = "空头排列 MA5<MA10<MA20"
                result.trend_strength = 25
                
        elif ma5 < ma10 and ma10 >= ma20:
            result.trend_status = TrendStatus.WEAK_BEAR
            result.ma_alignment = "弱势空头，MA5<MA10 但 MA10≥MA20"
            result.trend_strength = 40
            
        else:
            result.trend_status = TrendStatus.CONSOLIDATION
            result.ma_alignment = "均线缠绕，趋势不明"
            result.trend_strength = 50
    
    def _analyze_medium_trend(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        分析中期趋势状态

        使用 MA60 约束短线买入信号，避免下降趋势中的短期反抽被误判为买点。
        """
        if result.ma60 <= 0:
            result.ma60_trend = "MA60数据不足"
            return

        result.price_vs_ma60 = (result.current_price - result.ma60) / result.ma60 * 100

        if len(df) >= 80 and df['MA60'].iloc[-20] > 0:
            prev_ma60 = df['MA60'].iloc[-20]
            result.ma60_slope = (result.ma60 - prev_ma60) / prev_ma60 * 100

        if result.current_price < result.ma60 and result.ma60_slope < 0:
            result.medium_trend_risk = True
            result.ma60_trend = "现价低于下行MA60，中期趋势压制"
        elif result.current_price >= result.ma60 and result.ma60_slope >= 0:
            result.ma60_trend = "现价位于上行MA60上方，中期趋势向好"
        elif result.current_price >= result.ma60:
            result.ma60_trend = "现价站上MA60，但中期趋势尚未确认上行"
        else:
            result.ma60_trend = "现价低于MA60，中期趋势偏弱"

    def _calculate_bias(self, result: TrendAnalysisResult) -> None:
        """
        计算乖离率
        
        乖离率 = (现价 - 均线) / 均线 * 100%
        
        严进策略：乖离率超过自适应纪律线不追高
        """
        price = result.current_price
        
        if result.ma5 > 0:
            result.bias_ma5 = (price - result.ma5) / result.ma5 * 100
        if result.ma10 > 0:
            result.bias_ma10 = (price - result.ma10) / result.ma10 * 100
        if result.ma20 > 0:
            result.bias_ma20 = (price - result.ma20) / result.ma20 * 100
    
    def _analyze_volume(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        分析量能
        
        偏好：缩量回调 > 放量上涨 > 缩量上涨 > 放量下跌
        """
        if len(df) < 5:
            return
        
        latest = df.iloc[-1]
        vol_5d_avg = df['volume'].iloc[-6:-1].mean()
        
        if vol_5d_avg > 0:
            result.volume_ratio_5d = float(latest['volume']) / vol_5d_avg
        
        # 判断价格变化
        prev_close = df.iloc[-2]['close']
        price_change = (latest['close'] - prev_close) / prev_close * 100
        
        # 量能状态判断
        if result.volume_ratio_5d >= self.VOLUME_HEAVY_RATIO:
            if price_change > 0:
                result.volume_status = VolumeStatus.HEAVY_VOLUME_UP
                result.volume_trend = "放量上涨，多头力量强劲"
            else:
                result.volume_status = VolumeStatus.HEAVY_VOLUME_DOWN
                result.volume_trend = "放量下跌，注意风险"
        elif result.volume_ratio_5d <= self.VOLUME_SHRINK_RATIO:
            if price_change > 0:
                result.volume_status = VolumeStatus.SHRINK_VOLUME_UP
                result.volume_trend = "缩量上涨，上攻动能不足"
            else:
                result.volume_status = VolumeStatus.SHRINK_VOLUME_DOWN
                result.volume_trend = "缩量回调，洗盘特征明显（好）"
        else:
            result.volume_status = VolumeStatus.NORMAL
            result.volume_trend = "量能正常"
    
    def _analyze_support_resistance(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        分析支撑压力位
        
        买点偏好：回踩 MA5/MA10 获得支撑
        """
        latest = df.iloc[-1]
        open_price = self._to_float(latest.get('open'))
        high = self._to_float(latest.get('high'))
        low = self._to_float(latest.get('low'))
        price = result.current_price
        support_tolerance = result.adaptive_support_tolerance or self.MA_SUPPORT_TOLERANCE

        candle_range = high - low
        if candle_range > 0:
            lower_shadow = max(min(open_price, price) - low, 0.0)
            result.lower_shadow_ratio = round(lower_shadow / candle_range * 100, 2)
        result.bullish_candle = price > open_price
        result.ma5_hold_days = self._count_ma_hold_days(df, 'MA5')
        result.ma10_hold_days = self._count_ma_hold_days(df, 'MA10')
        result.ma20_breakdown = result.ma20 > 0 and price < result.ma20

        confirmation_notes = []
        if result.bullish_candle:
            confirmation_notes.append("阳线确认")
        if result.lower_shadow_ratio >= self.LOWER_SHADOW_CONFIRM_RATIO:
            confirmation_notes.append(f"下影线承接({result.lower_shadow_ratio:.1f}%)")

        # 检查是否在 MA5 附近获得支撑
        if result.ma5 > 0:
            ma5_distance = abs(price - result.ma5) / result.ma5
            result.ma5_touch_reclaim = low <= result.ma5 <= price
            ma5_hold_confirmed = result.ma5_hold_days >= self.SUPPORT_HOLD_DAYS
            ma5_candle_confirmed = result.bullish_candle or result.lower_shadow_ratio >= self.LOWER_SHADOW_CONFIRM_RATIO
            if ma5_distance <= support_tolerance and price >= result.ma5 and (
                result.ma5_touch_reclaim or ma5_hold_confirmed or ma5_candle_confirmed
            ):
                result.support_ma5 = True
                result.support_levels.append(result.ma5)
                if result.ma5_touch_reclaim:
                    confirmation_notes.append("回踩MA5后收回")
                elif ma5_hold_confirmed:
                    confirmation_notes.append(f"连续{result.ma5_hold_days}日守住MA5")
        
        # 检查是否在 MA10 附近获得支撑
        if result.ma10 > 0:
            ma10_distance = abs(price - result.ma10) / result.ma10
            result.ma10_touch_reclaim = low <= result.ma10 <= price
            ma10_hold_confirmed = result.ma10_hold_days >= self.SUPPORT_HOLD_DAYS
            ma10_candle_confirmed = result.bullish_candle or result.lower_shadow_ratio >= self.LOWER_SHADOW_CONFIRM_RATIO
            if ma10_distance <= support_tolerance and price >= result.ma10 and (
                result.ma10_touch_reclaim or ma10_hold_confirmed or ma10_candle_confirmed
            ):
                result.support_ma10 = True
                if result.ma10 not in result.support_levels:
                    result.support_levels.append(result.ma10)
                if result.ma10_touch_reclaim:
                    confirmation_notes.append("回踩MA10后收回")
                elif ma10_hold_confirmed:
                    confirmation_notes.append(f"连续{result.ma10_hold_days}日守住MA10")
        
        # MA20 作为重要支撑
        if result.ma20 > 0 and price >= result.ma20:
            result.support_levels.append(result.ma20)
        elif result.ma20_breakdown:
            confirmation_notes.append("收盘跌破MA20")

        result.support_confirmation = "；".join(dict.fromkeys(confirmation_notes)) or "暂无明确K线支撑确认"
        
        # 近期高点作为压力
        if len(df) >= 20:
            recent_high = df['high'].iloc[-20:].max()
            if recent_high > price:
                result.resistance_levels.append(recent_high)

    def _count_ma_hold_days(self, df: pd.DataFrame, ma_column: str, days: int = 3) -> int:
        """统计最近连续几个交易日的最低价没有跌破指定均线。"""
        count = 0
        for _, row in df.tail(days).iloc[::-1].iterrows():
            ma_value = self._to_float(row.get(ma_column))
            low = self._to_float(row.get('low'))
            close = self._to_float(row.get('close'))
            if ma_value > 0 and close >= ma_value and low >= ma_value:
                count += 1
            else:
                break
        return count
    
    def _calculate_trade_plan(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """计算规则层买点、止损、目标位和盈亏比。"""
        price = result.current_price
        bias_threshold = result.adaptive_bias_threshold or self.BIAS_THRESHOLD
        support_tolerance = result.adaptive_support_tolerance or self.MA_SUPPORT_TOLERANCE
        valid_supports = [level for level in [result.ma5, result.ma10, result.ma20] if level > 0]

        if not valid_supports or price <= 0:
            return

        if result.bias_ma5 >= bias_threshold:
            result.ideal_buy = round(result.ma5, 2)
        else:
            nearby_supports = [level for level in valid_supports if abs(price - level) / level <= support_tolerance]
            result.ideal_buy = round(min(nearby_supports, key=lambda level: abs(price - level)) if nearby_supports else result.ma5, 2)

        if result.ma10 > 0 and result.ma10 != result.ideal_buy:
            result.secondary_buy = round(result.ma10, 2)
        elif result.ma20 > 0:
            result.secondary_buy = round(result.ma20, 2)

        recent_low = float(df['low'].iloc[-20:].min()) if len(df) >= 20 else 0.0
        ma20_stop = result.ma20 * 0.98 if result.ma20 > 0 else 0.0
        atr_stop = result.ideal_buy - self.ATR_STOP_MULTIPLIER * result.atr_20 if result.atr_20 > 0 else 0.0
        stop_candidates = [level for level in [ma20_stop, recent_low * 0.98, atr_stop] if 0 < level < result.ideal_buy]
        if stop_candidates:
            result.stop_loss = round(max(stop_candidates), 2)

        resistance_candidates = [level for level in result.resistance_levels if level > result.ideal_buy]
        if resistance_candidates:
            result.take_profit = round(min(resistance_candidates), 2)
        elif result.stop_loss > 0:
            risk = result.ideal_buy - result.stop_loss
            result.take_profit = round(result.ideal_buy + risk * 1.8, 2)

        if result.ideal_buy > result.stop_loss > 0 and result.take_profit > result.ideal_buy:
            risk = result.ideal_buy - result.stop_loss
            reward = result.take_profit - result.ideal_buy
            result.risk_reward_ratio = round(reward / risk, 2)

        if result.stop_loss > 0:
            if result.atr_20 > 0:
                result.invalidation_condition = f"跌破止损位{result.stop_loss:.2f}元或回撤超过1.5倍ATR"
            else:
                result.invalidation_condition = f"跌破止损位{result.stop_loss:.2f}元或有效跌破MA20"
        elif result.ma20 > 0:
            result.invalidation_condition = f"有效跌破MA20({result.ma20:.2f}元)"

        if result.risk_reward_ratio >= 1.8:
            result.position_note = "盈亏比较优，可按规则仓位执行"
        elif result.risk_reward_ratio >= 1.2:
            result.position_note = "盈亏比一般，仅适合低仓试探"
        elif result.risk_reward_ratio > 0:
            result.position_note = "盈亏比不足，等待更优买点"

    def _generate_signal(self, result: TrendAnalysisResult) -> None:
        """
        生成买入信号
        
        综合评分系统：
        - 趋势（40分）：多头排列得分高
        - 乖离率（30分）：接近 MA5 得分高
        - 量能（20分）：缩量回调得分高
        - 支撑（10分）：获得均线支撑得分高
        """
        score = 0
        reasons = []
        risks = []
        bias_threshold = result.adaptive_bias_threshold or self.BIAS_THRESHOLD
        
        # === 趋势评分（40分）===
        trend_scores = {
            TrendStatus.STRONG_BULL: 40,
            TrendStatus.BULL: 35,
            TrendStatus.WEAK_BULL: 25,
            TrendStatus.CONSOLIDATION: 15,
            TrendStatus.WEAK_BEAR: 10,
            TrendStatus.BEAR: 5,
            TrendStatus.STRONG_BEAR: 0,
        }
        trend_score = trend_scores.get(result.trend_status, 15)
        score += trend_score
        
        if result.trend_status in [TrendStatus.STRONG_BULL, TrendStatus.BULL]:
            reasons.append(f"✅ {result.trend_status.value}，顺势做多")
        elif result.trend_status in [TrendStatus.BEAR, TrendStatus.STRONG_BEAR]:
            risks.append(f"⚠️ {result.trend_status.value}，不宜做多")
        
        # === 乖离率评分（30分）===
        bias = result.bias_ma5
        if bias < 0:
            # 价格在 MA5 下方（回调中）
            if bias > -3:
                score += 30
                reasons.append(f"✅ 价格略低于MA5({bias:.1f}%)，回踩买点")
            elif bias > -5:
                score += 25
                reasons.append(f"✅ 价格回踩MA5({bias:.1f}%)，观察支撑")
            else:
                score += 10
                risks.append(f"⚠️ 乖离率过大({bias:.1f}%)，可能破位")
        elif bias < 2:
            score += 28
            reasons.append(f"✅ 价格贴近MA5({bias:.1f}%)，介入好时机")
        elif bias < bias_threshold:
            score += 20
            reasons.append(f"⚡ 价格略高于MA5({bias:.1f}%)，未超过自适应追高线")
        else:
            score += 5
            risks.append(f"❌ 乖离率过高({bias:.1f}%>{bias_threshold:.1f}%)，严禁追高！")
        
        # === 量能评分（20分）===
        volume_scores = {
            VolumeStatus.SHRINK_VOLUME_DOWN: 20,  # 缩量回调最佳
            VolumeStatus.HEAVY_VOLUME_UP: 15,     # 放量上涨次之
            VolumeStatus.NORMAL: 12,
            VolumeStatus.SHRINK_VOLUME_UP: 8,     # 无量上涨较差
            VolumeStatus.HEAVY_VOLUME_DOWN: 0,    # 放量下跌最差
        }
        vol_score = volume_scores.get(result.volume_status, 10)
        score += vol_score
        
        if result.volume_status == VolumeStatus.SHRINK_VOLUME_DOWN:
            reasons.append("✅ 缩量回调，主力洗盘")
        elif result.volume_status == VolumeStatus.HEAVY_VOLUME_DOWN:
            risks.append("⚠️ 放量下跌，注意风险")
        
        # === 支撑评分（10分）===
        if result.support_ma5:
            score += 5
            reasons.append("✅ MA5支撑有效（K线确认）")
        if result.support_ma10:
            score += 5
            reasons.append("✅ MA10支撑有效（K线确认）")

        # === 相对强弱评分（-10~+10分）===
        if result.relative_strength_score > 0:
            score += result.relative_strength_score
            reasons.append(
                f"✅ 相对强弱{result.relative_strength_status}"
                f"（RS {result.relative_strength_score:+d}）：{result.relative_strength_summary}"
            )
        elif result.relative_strength_score < 0:
            score += result.relative_strength_score
            risks.append(
                f"⚠️ 相对强弱{result.relative_strength_status}"
                f"（RS {result.relative_strength_score:+d}）：{result.relative_strength_summary}"
            )
            if result.relative_strength_score <= -6:
                score = min(score, 64)

        if result.current_price < result.ma5 and not (result.support_ma5 or result.support_ma10):
            score = min(score, 64)
            risks.append("⚠️ 回踩均线但尚未出现K线支撑确认，等待收回均线")

        if result.ma20_breakdown:
            score = min(score, 49)
            risks.append("⚠️ 收盘跌破MA20，买入信号失效或降级")

        if result.ma60_trend:
            if result.medium_trend_risk:
                score = min(score, 60)
                risks.append(f"⚠️ {result.ma60_trend}，限制追多")
            else:
                reasons.append(f"✅ {result.ma60_trend}")

        if result.bias_ma5 >= bias_threshold:
            score = min(score, 59)

        if result.risk_reward_ratio > 0:
            if result.risk_reward_ratio < 1.2:
                score = min(score, 49)
                risks.append(f"⚠️ 盈亏比不足({result.risk_reward_ratio:.2f}<1.20)，等待更优点位")
            elif result.risk_reward_ratio < 1.8:
                score = min(score, 69)
                risks.append(f"⚠️ 盈亏比一般({result.risk_reward_ratio:.2f})，仅适合低仓试探")
            else:
                reasons.append(f"✅ 盈亏比{result.risk_reward_ratio:.2f}，具备交易空间")

        # === 综合判断 ===
        result.signal_score = max(0, min(100, score))
        result.signal_reasons = reasons
        result.risk_factors = risks
        
        # 生成买入信号
        if result.signal_score >= 80 and result.trend_status in [TrendStatus.STRONG_BULL, TrendStatus.BULL]:
            result.buy_signal = BuySignal.STRONG_BUY
        elif result.signal_score >= 65 and result.trend_status in [TrendStatus.STRONG_BULL, TrendStatus.BULL, TrendStatus.WEAK_BULL]:
            result.buy_signal = BuySignal.BUY
        elif result.signal_score >= 50:
            result.buy_signal = BuySignal.HOLD
        elif result.signal_score >= 35:
            result.buy_signal = BuySignal.WAIT
        elif result.trend_status in [TrendStatus.BEAR, TrendStatus.STRONG_BEAR]:
            result.buy_signal = BuySignal.STRONG_SELL
        else:
            result.buy_signal = BuySignal.SELL
    
    def format_analysis(self, result: TrendAnalysisResult) -> str:
        """
        格式化分析结果为文本
        
        Args:
            result: 分析结果
            
        Returns:
            格式化的分析文本
        """
        lines = [
            f"=== {result.code} 趋势分析 ===",
            f"",
            f"📊 趋势判断: {result.trend_status.value}",
            f"   均线排列: {result.ma_alignment}",
            f"   趋势强度: {result.trend_strength}/100",
            f"",
            f"📈 均线数据:",
            f"   现价: {result.current_price:.2f}",
            f"   MA5:  {result.ma5:.2f} (乖离 {result.bias_ma5:+.2f}%)",
            f"   MA10: {result.ma10:.2f} (乖离 {result.bias_ma10:+.2f}%)",
            f"   MA20: {result.ma20:.2f} (乖离 {result.bias_ma20:+.2f}%)",
            f"   MA60: {result.ma60:.2f} (相对 {result.price_vs_ma60:+.2f}%, 斜率 {result.ma60_slope:+.2f}%)",
            f"   中期趋势: {result.ma60_trend}",
            f"   ATR20: {result.atr_20:.2f} ({result.atr_pct:.2f}%), "
            f"追高线: {result.adaptive_bias_threshold:.2f}%, "
            f"支撑容忍: {result.adaptive_support_tolerance * 100:.2f}%",
            f"   相对强弱: {result.relative_strength_status} "
            f"(个股{result.stock_return_20d:+.2f}%, "
            f"相对大盘{result.stock_vs_benchmark:+.2f}pct, "
            f"相对行业{result.stock_vs_sector:+.2f}pct, "
            f"RS {result.relative_strength_score:+d})",
            f"   K线确认: {result.support_confirmation}",
            f"",
            f"📊 量能分析: {result.volume_status.value}",
            f"   量比(vs5日): {result.volume_ratio_5d:.2f}",
            f"   量能趋势: {result.volume_trend}",
            f"",
            f"🎯 规则交易计划:",
            f"   理想买点: {result.ideal_buy:.2f}",
            f"   次优买点: {result.secondary_buy:.2f}",
            f"   止损位: {result.stop_loss:.2f}",
            f"   目标位: {result.take_profit:.2f}",
            f"   盈亏比: {result.risk_reward_ratio:.2f}",
            f"   失效条件: {result.invalidation_condition or 'N/A'}",
            f"   仓位提示: {result.position_note or 'N/A'}",
            f"   规则仓位: {result.final_position_pct:.1f}% "
            f"(单笔风险距离 {result.single_trade_risk_pct:.2f}%, 风险预算上限 {result.max_position_by_risk_pct:.1f}%)",
            f"",
            f"🎯 操作建议: {result.buy_signal.value}",
            f"   综合评分: {result.signal_score}/100",
        ]
        
        if result.signal_reasons:
            lines.append(f"")
            lines.append(f"✅ 买入理由:")
            for reason in result.signal_reasons:
                lines.append(f"   {reason}")
        
        if result.risk_factors:
            lines.append(f"")
            lines.append(f"⚠️ 风险因素:")
            for risk in result.risk_factors:
                lines.append(f"   {risk}")
        
        return "\n".join(lines)


def analyze_stock(df: pd.DataFrame, code: str) -> TrendAnalysisResult:
    """
    便捷函数：分析单只股票
    
    Args:
        df: 包含 OHLCV 数据的 DataFrame
        code: 股票代码
        
    Returns:
        TrendAnalysisResult 分析结果
    """
    analyzer = StockTrendAnalyzer()
    return analyzer.analyze(df, code)


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)
    
    # 模拟数据测试
    import numpy as np
    
    dates = pd.date_range(start='2025-01-01', periods=60, freq='D')
    np.random.seed(42)
    
    # 模拟多头排列的数据
    base_price = 10.0
    prices = [base_price]
    for i in range(59):
        change = np.random.randn() * 0.02 + 0.003  # 轻微上涨趋势
        prices.append(prices[-1] * (1 + change))
    
    df = pd.DataFrame({
        'date': dates,
        'open': prices,
        'high': [p * (1 + np.random.uniform(0, 0.02)) for p in prices],
        'low': [p * (1 - np.random.uniform(0, 0.02)) for p in prices],
        'close': prices,
        'volume': [np.random.randint(1000000, 5000000) for _ in prices],
    })
    
    analyzer = StockTrendAnalyzer()
    result = analyzer.analyze(df, '000001')
    print(analyzer.format_analysis(result).encode('utf-8', errors='ignore').decode('utf-8'))
