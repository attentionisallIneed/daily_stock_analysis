# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - AI分析层
===================================

职责：
1. 封装 OpenAI 标准/兼容 API 调用逻辑
2. 结合预先搜索的新闻和技术面数据生成分析报告
3. 解析模型返回的 JSON 格式结果
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from config import get_config

logger = logging.getLogger(__name__)


# 股票名称映射（常见股票）
STOCK_NAME_MAP = {

}


@dataclass
class AnalysisResult:
    """
    AI 分析结果数据类 - 决策仪表盘版
    
    封装 LLM 返回的分析结果，包含决策仪表盘和详细分析
    """
    code: str
    name: str
    
    # ========== 核心指标 ==========
    sentiment_score: int  # 综合评分 0-100 (>70强烈看多, >60看多, 40-60震荡, <40看空)
    trend_prediction: str  # 趋势预测：强烈看多/看多/震荡/看空/强烈看空
    operation_advice: str  # 操作建议：买入/加仓/持有/减仓/卖出/观望
    confidence_level: str = "中"  # 置信度：高/中/低
    
    # ========== 决策仪表盘 (新增) ==========
    dashboard: Optional[Dict[str, Any]] = None  # 完整的决策仪表盘数据
    
    # ========== 走势分析 ==========
    trend_analysis: str = ""  # 走势形态分析（支撑位、压力位、趋势线等）
    short_term_outlook: str = ""  # 短期展望（1-3日）
    medium_term_outlook: str = ""  # 中期展望（1-2周）
    
    # ========== 技术面分析 ==========
    technical_analysis: str = ""  # 技术指标综合分析
    ma_analysis: str = ""  # 均线分析（多头/空头排列，金叉/死叉等）
    volume_analysis: str = ""  # 量能分析（放量/缩量，主力动向等）
    pattern_analysis: str = ""  # K线形态分析
    
    # ========== 基本面分析 ==========
    fundamental_analysis: str = ""  # 基本面综合分析
    sector_position: str = ""  # 板块地位和行业趋势
    company_highlights: str = ""  # 公司亮点/风险点
    
    # ========== 情绪面/消息面分析 ==========
    news_summary: str = ""  # 近期重要新闻/公告摘要
    market_sentiment: str = ""  # 市场情绪分析
    hot_topics: str = ""  # 相关热点话题
    
    # ========== 综合分析 ==========
    analysis_summary: str = ""  # 综合分析摘要
    key_points: str = ""  # 核心看点（3-5个要点）
    risk_warning: str = ""  # 风险提示
    buy_reason: str = ""  # 买入/卖出理由
    
    # ========== 元数据 ==========
    raw_response: Optional[str] = None  # 原始响应（调试用）
    search_performed: bool = False  # 是否执行了联网搜索
    data_sources: str = ""  # 数据来源说明
    success: bool = True
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'code': self.code,
            'name': self.name,
            'sentiment_score': self.sentiment_score,
            'trend_prediction': self.trend_prediction,
            'operation_advice': self.operation_advice,
            'confidence_level': self.confidence_level,
            'dashboard': self.dashboard,  # 决策仪表盘数据
            'trend_analysis': self.trend_analysis,
            'short_term_outlook': self.short_term_outlook,
            'medium_term_outlook': self.medium_term_outlook,
            'technical_analysis': self.technical_analysis,
            'ma_analysis': self.ma_analysis,
            'volume_analysis': self.volume_analysis,
            'pattern_analysis': self.pattern_analysis,
            'fundamental_analysis': self.fundamental_analysis,
            'sector_position': self.sector_position,
            'company_highlights': self.company_highlights,
            'news_summary': self.news_summary,
            'market_sentiment': self.market_sentiment,
            'hot_topics': self.hot_topics,
            'analysis_summary': self.analysis_summary,
            'key_points': self.key_points,
            'risk_warning': self.risk_warning,
            'buy_reason': self.buy_reason,
            'search_performed': self.search_performed,
            'success': self.success,
            'error_message': self.error_message,
        }
    
    def get_core_conclusion(self) -> str:
        """获取核心结论（一句话）"""
        if self.dashboard and 'core_conclusion' in self.dashboard:
            return self.dashboard['core_conclusion'].get('one_sentence', self.analysis_summary)
        return self.analysis_summary
    
    def get_position_advice(self, has_position: bool = False) -> str:
        """获取持仓建议"""
        if self.dashboard and 'core_conclusion' in self.dashboard:
            pos_advice = self.dashboard['core_conclusion'].get('position_advice', {})
            if has_position:
                return pos_advice.get('has_position', self.operation_advice)
            return pos_advice.get('no_position', self.operation_advice)
        return self.operation_advice
    
    def get_sniper_points(self) -> Dict[str, str]:
        """获取狙击点位"""
        if self.dashboard and 'battle_plan' in self.dashboard:
            return self.dashboard['battle_plan'].get('sniper_points', {})
        return {}
    
    def get_checklist(self) -> List[str]:
        """获取检查清单"""
        if self.dashboard and 'battle_plan' in self.dashboard:
            return self.dashboard['battle_plan'].get('action_checklist', [])
        return []
    
    def get_risk_alerts(self) -> List[str]:
        """获取风险警报"""
        if self.dashboard and 'intelligence' in self.dashboard:
            return self.dashboard['intelligence'].get('risk_alerts', [])
        return []
    
    def get_emoji(self) -> str:
        """根据操作建议返回对应 emoji"""
        emoji_map = {
            '买入': '🟢',
            '加仓': '🟢',
            '强烈买入': '💚',
            '持有': '🟡',
            '观望': '⚪',
            '减仓': '🟠',
            '卖出': '🔴',
            '强烈卖出': '❌',
        }
        return emoji_map.get(self.operation_advice, '🟡')
    
    def get_confidence_stars(self) -> str:
        """返回置信度星级"""
        star_map = {'高': '⭐⭐⭐', '中': '⭐⭐', '低': '⭐'}
        return star_map.get(self.confidence_level, '⭐⭐')


class OpenAIAnalyzer:
    """
    OpenAI 标准/兼容接口分析器

    职责：
    1. 调用 OpenAI Chat Completions 兼容接口进行股票分析
    2. 结合预先搜索的新闻和技术面数据生成分析报告
    3. 解析 AI 返回的 JSON 格式结果

    使用方式：
        analyzer = OpenAIAnalyzer()
        result = analyzer.analyze(context, news_context)
    """
    
    # ========================================
    # 系统提示词 - 决策仪表盘 v2.0
    # ========================================
    # 输出格式升级：从简单信号升级为决策仪表盘
    # 核心模块：核心结论 + 数据透视 + 舆情情报 + 作战计划
    # ========================================
    
    SYSTEM_PROMPT = """你是一位专注于趋势交易的 A 股投资分析师，负责生成专业的【决策仪表盘】分析报告。

## 核心交易理念（必须严格遵守）

### 1. 严进策略（不追高）
- **绝对不追高**：当股价偏离 MA5 超过规则层纪律线时，坚决不买入
- **乖离率公式**：(现价 - MA5) / MA5 × 100%
- 纪律线由规则层计算：默认最高 5%，低波动标的会按 ATR 自动收紧
- 乖离率 < 2%：最佳买点区间
- 乖离率 2% 至规则纪律线：只可小仓介入
- 乖离率超过规则纪律线：严禁追高！直接判定为"观望"
- 有效突破/趋势加速必须由规则层标记；只有未超过突破延伸线时，才可按突破策略低仓试探，不能混同为普通追涨

### 2. 趋势交易（顺势而为）
- **多头排列必须条件**：MA5 > MA10 > MA20
- 只做多头排列的股票，空头排列坚决不碰
- 均线发散上行优于均线粘合
- 趋势强度判断：看均线间距是否在扩大

### 3. 效率优先（筹码结构）
- 关注筹码集中度：90%集中度 < 15% 表示筹码集中
- 获利比例分析：70-90% 获利盘时需警惕获利回吐
- 平均成本与现价关系：现价高于平均成本 5-15% 为健康

### 4. 买点偏好（回踩支撑）
- **最佳买点**：缩量回踩 MA5 获得支撑
- **次优买点**：回踩 MA10 获得支撑
- **观望情况**：跌破 MA20 时观望

### 5. 风险排查重点
- 减持公告（股东、高管减持）
- 业绩预亏/大幅下滑
- 监管处罚/立案调查
- 行业政策利空
- 大额解禁

### 6. 品种差异
- 普通股票：重点看筹码、公告、财报、减持、个股流动性。
- 行业 ETF：重点看行业趋势、板块热度、相对强弱和成交活跃度，不把个股财报作为核心依据。
- 宽基 ETF / 指数：重点看大盘环境、成交额、市场宽度和宏观风险，指数仅用于观察不输出开仓仓位。

## 输出格式：决策仪表盘 JSON

请严格按照以下 JSON 格式输出，这是一个完整的【决策仪表盘】：

```json
{
    "sentiment_score": 0-100整数,
    "trend_prediction": "强烈看多/看多/震荡/看空/强烈看空",
    "operation_advice": "买入/加仓/持有/减仓/卖出/观望",
    "confidence_level": "高/中/低",
    
    "dashboard": {
        "core_conclusion": {
            "one_sentence": "一句话核心结论（30字以内，直接告诉用户做什么）",
            "signal_type": "🟢买入信号/🟡持有观望/🔴卖出信号/⚠️风险警告",
            "time_sensitivity": "立即行动/今日内/本周内/不急",
            "position_advice": {
                "no_position": "空仓者建议：具体操作指引",
                "has_position": "持仓者建议：具体操作指引"
            }
        },
        
        "data_perspective": {
            "trend_status": {
                "ma_alignment": "均线排列状态描述",
                "is_bullish": true/false,
                "trend_score": 0-100
            },
            "price_position": {
                "current_price": 当前价格数值,
                "ma5": MA5数值,
                "ma10": MA10数值,
                "ma20": MA20数值,
                "bias_ma5": 乖离率百分比数值,
                "bias_status": "安全/警戒/危险",
                "support_level": 支撑位价格,
                "resistance_level": 压力位价格
            },
            "volume_analysis": {
                "volume_ratio": 量比数值,
                "volume_status": "放量/缩量/平量",
                "turnover_rate": 换手率百分比,
                "volume_meaning": "量能含义解读（如：缩量回调表示抛压减轻）"
            },
            "chip_structure": {
                "profit_ratio": 获利比例,
                "avg_cost": 平均成本,
                "concentration": 筹码集中度,
                "chip_health": "健康/一般/警惕"
            }
        },
        
        "intelligence": {
            "latest_news": "【最新消息】近期重要新闻摘要",
            "risk_alerts": ["风险点1：具体描述", "风险点2：具体描述"],
            "positive_catalysts": ["利好1：具体描述", "利好2：具体描述"],
            "earnings_outlook": "业绩预期分析（基于年报预告、业绩快报等）",
            "sentiment_summary": "舆情情绪一句话总结"
        },
        
        "battle_plan": {
            "sniper_points": {
                "ideal_buy": "规则层理想买入点：XX元（来自MA5/MA10支撑）",
                "secondary_buy": "规则层次优买入点：XX元（来自MA10/MA20支撑）",
                "stop_loss": "规则层止损位：XX元（来自MA20/前低）",
                "take_profit": "规则层目标位：XX元（来自压力位/盈亏比）",
                "risk_reward_ratio": "规则层盈亏比：X.XX",
                "invalidation_condition": "规则层信号失效条件"
            },
            "position_strategy": {
                "suggested_position": "规则层建议仓位：X%",
                "entry_plan": "分批建仓策略描述",
                "risk_control": "风控策略描述"
            },
            "action_checklist": [
                "✅/⚠️/❌ 检查项1：多头排列",
                "✅/⚠️/❌ 检查项2：乖离率低于规则纪律线",
                "✅/⚠️/❌ 检查项3：量能配合",
                "✅/⚠️/❌ 检查项4：无重大利空",
                "✅/⚠️/❌ 检查项5：筹码健康"
            ]
        }
    },
    
    "analysis_summary": "100字综合分析摘要",
    "key_points": "3-5个核心看点，逗号分隔",
    "risk_warning": "风险提示",
    "buy_reason": "操作理由，引用交易理念",
    
    "trend_analysis": "走势形态分析",
    "short_term_outlook": "短期1-3日展望",
    "medium_term_outlook": "中期1-2周展望",
    "technical_analysis": "技术面综合分析",
    "ma_analysis": "均线系统分析",
    "volume_analysis": "量能分析",
    "pattern_analysis": "K线形态分析",
    "fundamental_analysis": "基本面分析",
    "sector_position": "板块行业分析",
    "company_highlights": "公司亮点/风险",
    "news_summary": "新闻摘要",
    "market_sentiment": "市场情绪",
    "hot_topics": "相关热点",
    
    "search_performed": true/false,
    "data_sources": "数据来源说明"
}
```

## 评分标准

### 强烈买入（80-100分）：
- ✅ 多头排列：MA5 > MA10 > MA20
- ✅ 低乖离率：<2%，最佳买点
- ✅ 缩量回调或放量突破
- ✅ 筹码集中健康
- ✅ 消息面有利好催化

### 买入（60-79分）：
- ✅ 多头排列或弱势多头
- ✅ 乖离率低于规则纪律线
- ✅ 量能正常
- ⚪ 允许一项次要条件不满足

### 观望（40-59分）：
- ⚠️ 乖离率超过规则纪律线（追高风险）
- ⚠️ 均线缠绕趋势不明
- ⚠️ 有风险事件

### 卖出/减仓（0-39分）：
- ❌ 空头排列
- ❌ 跌破MA20
- ❌ 放量下跌
- ❌ 重大利空

## 决策仪表盘核心原则

1. **核心结论先行**：一句话说清该买该卖
2. **分持仓建议**：空仓者和持仓者给不同建议
3. **精确狙击点**：必须使用规则层提供的买点、止损、目标位和盈亏比，不自行创造点位
4. **检查清单可视化**：用 ✅⚠️❌ 明确显示每项检查结果
5. **风险优先级**：舆情中的风险点要醒目标出"""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 AI 分析器
        
        使用 OpenAI 标准/兼容 API，配置来自 OPENAI_API_KEY、OPENAI_BASE_URL、OPENAI_MODEL
        """
        config = get_config()
        self._api_key = api_key or config.openai_api_key
        self._base_url = config.openai_base_url
        self._model_name = config.openai_model
        
        self._client = None
        self._is_available = False
        
        self._init_client()
        
    def _init_client(self) -> None:
        """初始化 OpenAI 标准客户端"""
        missing = []
        if not self._api_key:
            missing.append('OPENAI_API_KEY')
        if not self._base_url:
            missing.append('OPENAI_BASE_URL')
        if not self._model_name:
            missing.append('OPENAI_MODEL')
        if missing:
            logger.warning(f"LLM 配置缺失: {', '.join(missing)}，AI 分析功能不可用")
            self._client = None
            self._is_available = False
            return

        try:
            from openai import OpenAI
            import httpx

            logger.info(f"正在初始化 OpenAI 兼容客户端 (base_url: {self._base_url}, model: {self._model_name})...")

            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                http_client=httpx.Client(timeout=120)
            )
            self._is_available = True
            logger.info("OpenAI 兼容客户端初始化成功")

        except Exception as e:
            logger.error(f"OpenAI 兼容客户端初始化失败: {e}")
            self._client = None
            self._is_available = False
    

    
    def is_available(self) -> bool:
        """检查分析器是否可用"""
        return self._is_available

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        """从 OpenAI SDK 对象、兼容接口字典或纯文本响应中提取正文。"""
        def normalize_text(text: Any) -> str:
            value = str(text)
            lowered = value.lstrip().lower()
            if lowered.startswith("<!doctype") or lowered.startswith("<html"):
                raise ValueError("API 返回 HTML 页面，请检查 OPENAI_BASE_URL 是否为标准 /v1 接口地址")
            return value

        if isinstance(response, str):
            return normalize_text(response)

        if isinstance(response, dict):
            choices = response.get("choices") or []
            if choices:
                first = choices[0]
                message = first.get("message") if isinstance(first, dict) else None
                if isinstance(message, dict):
                    content = message.get("content")
                    if content:
                        return normalize_text(content)
                content = first.get("content") if isinstance(first, dict) else None
                if content:
                    return normalize_text(content)

        choices = getattr(response, "choices", None)
        if choices:
            message = getattr(choices[0], "message", None)
            content = getattr(message, "content", None) if message is not None else None
            if content:
                return normalize_text(content)

        if hasattr(response, "model_dump"):
            return OpenAIAnalyzer._extract_response_text(response.model_dump())

        raise ValueError("API 返回空响应或无法识别的响应格式")
    
    def _call_api_with_retry(self, prompt: str, generation_config: dict) -> str:
        """
        调用 AI API (仅支持 OpenAI 兼容接口)
        """
        config = get_config()
        max_retries = config.llm_max_retries
        base_delay = config.llm_retry_delay
        
        if not self._client:
            raise RuntimeError("OpenAI 客户端未初始化")

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))
                    delay = min(delay, 60)
                    logger.info(f"第 {attempt + 1} 次重试，等待 {delay:.1f} 秒...")
                    time.sleep(delay)
                
                response = self._client.chat.completions.create(
                    model=self._model_name,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=generation_config.get('temperature', 0.7),
                    max_tokens=generation_config.get('max_output_tokens', 8192),
                    stream=False
                )
                
                return self._extract_response_text(response)
                    
            except Exception as e:
                error_str = str(e)
                logger.warning(f"API 调用失败，第 {attempt + 1}/{max_retries} 次尝试: {error_str[:100]}")
                
                if attempt == max_retries - 1:
                    raise

        raise Exception("API 调用失败，已达最大重试次数")
    
    def analyze(
        self, 
        context: Dict[str, Any],
        news_context: Optional[str] = None
    ) -> AnalysisResult:
        """
        分析单只股票
        
        流程：
        1. 格式化输入数据（技术面 + 新闻）
        2. 调用 OpenAI 兼容 API（带重试）
        3. 解析 JSON 响应
        4. 返回结构化结果
        
        Args:
            context: 从 storage.get_analysis_context() 获取的上下文数据
            news_context: 预先搜索的新闻内容（可选）
            
        Returns:
            AnalysisResult 对象
        """
        code = context.get('code', 'Unknown')
        config = get_config()
        
        # 请求前增加延时（防止连续请求触发限流）
        request_delay = config.llm_request_delay
        if request_delay > 0:
            logger.debug(f"[LLM] 请求前等待 {request_delay:.1f} 秒...")
            time.sleep(request_delay)
        
        # 优先从上下文获取股票名称（由 main.py 传入）
        name = context.get('stock_name')
        if not name or name.startswith('股票'):
            # 备选：从 realtime 中获取
            if 'realtime' in context and context['realtime'].get('name'):
                name = context['realtime']['name']
            else:
                # 最后从映射表获取
                name = STOCK_NAME_MAP.get(code, f'股票{code}')
        
        # 如果模型不可用，返回默认结果
        if not self.is_available():
            return AnalysisResult(
                code=code,
                name=name,
                sentiment_score=50,
                trend_prediction='震荡',
                operation_advice='持有',
                confidence_level='低',
                analysis_summary='AI 分析功能未启用（未配置 API Key）',
                risk_warning='请配置 OPENAI_API_KEY、OPENAI_BASE_URL 和 OPENAI_MODEL 后重试',
                success=False,
                error_message='OpenAI 兼容 API 配置未完成',
            )
        
        try:
            # 格式化输入（包含技术面数据和新闻）
            prompt = self._format_prompt(context, name, news_context)
            
            # 获取模型名称
            model_name = self._model_name

            
            logger.info(f"========== AI 分析 {name}({code}) ==========")
            logger.info(f"[LLM配置] 模型: {model_name}")
            logger.info(f"[LLM配置] Prompt 长度: {len(prompt)} 字符")
            logger.info(f"[LLM配置] 是否包含新闻: {'是' if news_context else '否'}")
            
            # 记录完整 prompt 到日志（INFO级别记录摘要，DEBUG记录完整）
            prompt_preview = prompt[:500] + "..." if len(prompt) > 500 else prompt
            logger.info(f"[LLM Prompt 预览]\n{prompt_preview}")
            logger.debug(f"=== 完整 Prompt ({len(prompt)}字符) ===\n{prompt}\n=== End Prompt ===")
            
            # 设置生成配置
            generation_config = {
                "temperature": 0.7,
                "max_output_tokens": 8192,
            }
            
            logger.info(f"[LLM调用] 开始调用 OpenAI 兼容 API (temperature={generation_config['temperature']}, max_tokens={generation_config['max_output_tokens']})...")
            
            # 使用带重试的 API 调用
            start_time = time.time()
            response_text = self._call_api_with_retry(prompt, generation_config)
            elapsed = time.time() - start_time
            
            # 记录响应信息
            logger.info(f"[LLM返回] OpenAI 兼容 API 响应成功, 耗时 {elapsed:.2f}s, 响应长度 {len(response_text)} 字符")
            
            # 记录响应预览（INFO级别）和完整响应（DEBUG级别）
            response_preview = response_text[:300] + "..." if len(response_text) > 300 else response_text
            logger.info(f"[LLM返回 预览]\n{response_preview}")
            logger.debug(f"=== LLM 完整响应 ({len(response_text)}字符) ===\n{response_text}\n=== End Response ===")
            
            # 解析响应
            result = self._parse_response(response_text, code, name)
            result = self._apply_hard_rules(result, context)
            result.raw_response = response_text
            result.search_performed = bool(news_context)
            
            logger.info(f"[LLM解析] {name}({code}) 分析完成: {result.trend_prediction}, 评分 {result.sentiment_score}")
            
            return result
            
        except Exception as e:
            logger.error(f"AI 分析 {name}({code}) 失败: {e}")
            return AnalysisResult(
                code=code,
                name=name,
                sentiment_score=50,
                trend_prediction='震荡',
                operation_advice='持有',
                confidence_level='低',
                analysis_summary=f'分析过程出错: {str(e)[:100]}',
                risk_warning='分析失败，请稍后重试或手动分析',
                success=False,
                error_message=str(e),
            )
    
    def _format_prompt(
        self, 
        context: Dict[str, Any], 
        name: str,
        news_context: Optional[str] = None
    ) -> str:
        """
        格式化分析提示词（决策仪表盘 v2.0）
        
        包含：技术指标、实时行情（量比/换手率）、筹码分布、趋势分析、新闻
        
        Args:
            context: 技术面数据上下文（包含增强数据）
            name: 股票名称（默认值，可能被上下文覆盖）
            news_context: 预先搜索的新闻内容
        """
        code = context.get('code', 'Unknown')
        
        # 优先使用上下文中的股票名称（从 realtime_quote 获取）
        stock_name = context.get('stock_name', name)
        if not stock_name or stock_name == f'股票{code}':
            stock_name = STOCK_NAME_MAP.get(code, f'股票{code}')
            
        today = context.get('today', {})
        
        # ========== 构建决策仪表盘格式的输入 ==========
        prompt = f"""# 决策仪表盘分析请求

## 📊 股票基础信息
| 项目 | 数据 |
|------|------|
| 股票代码 | **{code}** |
| 股票名称 | **{stock_name}** |
| 分析日期 | {context.get('date', '未知')} |

---

## 📈 技术面数据

### 今日行情
| 指标 | 数值 |
|------|------|
| 收盘价 | {today.get('close', 'N/A')} 元 |
| 开盘价 | {today.get('open', 'N/A')} 元 |
| 最高价 | {today.get('high', 'N/A')} 元 |
| 最低价 | {today.get('low', 'N/A')} 元 |
| 涨跌幅 | {today.get('pct_chg', 'N/A')}% |
| 成交量 | {self._format_volume(today.get('volume'))} |
| 成交额 | {self._format_amount(today.get('amount'))} |

### 均线系统（关键判断指标）
| 均线 | 数值 | 说明 |
|------|------|------|
| MA5 | {today.get('ma5', 'N/A')} | 短期趋势线 |
| MA10 | {today.get('ma10', 'N/A')} | 中短期趋势线 |
| MA20 | {today.get('ma20', 'N/A')} | 中期趋势线 |
| 均线形态 | {context.get('ma_status', '未知')} | 多头/空头/缠绕 |
"""

        if 'market_context' in context:
            market_context = context['market_context'] or {}
            environment = market_context.get('environment') or {}
            overview = market_context.get('overview') or {}
            indices = overview.get('indices') or []
            index_text = ', '.join(
                f"{idx.get('name', '')}({idx.get('change_pct', 0):+.2f}%)"
                for idx in indices[:4]
            ) if indices else '无'
            top_sectors = environment.get('top_sectors') or overview.get('top_sectors') or []
            bottom_sectors = environment.get('bottom_sectors') or overview.get('bottom_sectors') or []
            top_sector_text = ', '.join(f"{s.get('name')}({s.get('change_pct', 0):+.2f}%)" for s in top_sectors[:3]) if top_sectors else '无'
            bottom_sector_text = ', '.join(f"{s.get('name')}({s.get('change_pct', 0):+.2f}%)" for s in bottom_sectors[:3]) if bottom_sectors else '无'
            reason_text = chr(10).join('- ' + reason for reason in environment.get('reasons', [])) or '- 无'
            prompt += f"""
### 市场/板块环境（仓位与信号过滤）
| 指标 | 数值 | 纪律约束 |
|------|------|----------|
| 市场状态 | {environment.get('market_status', '未知')} | 弱市降低仓位，极弱优先观望 |
| 环境评分 | {environment.get('market_score', 50)}/100 | 仅作为风控过滤，不替代个股趋势 |
| 风险等级 | {environment.get('risk_level', '中')} | 高风险不输出高置信度买入 |
| 环境摘要 | {environment.get('summary', '未知')} | |
| 指数表现 | {index_text} | |
| 板块热度 | {environment.get('sector_heat_summary', '无')} | |
| 领涨板块 | {top_sector_text} | 相关题材可加关注 |
| 领跌板块 | {bottom_sector_text} | 相关题材需警惕拖累 |

**环境判断依据**：
{reason_text}

**市场/板块纪律**：
- 大盘偏弱/极弱时，不得给高置信度买入；仓位建议必须保守。
- 大盘极弱且个股不是强势多头时，优先输出观望。
- 无法确认个股所属板块时，不要臆造板块归属，只基于已知新闻、股票名称和行业信息谨慎判断。
"""

        # 添加实时行情数据（量比、换手率等）
        if 'realtime' in context:
            rt = context['realtime']
            prompt += f"""
### 实时行情增强数据
| 指标 | 数值 | 解读 |
|------|------|------|
| 当前价格 | {rt.get('price', 'N/A')} 元 | |
| **量比** | **{rt.get('volume_ratio', 'N/A')}** | {rt.get('volume_ratio_desc', '')} |
| **换手率** | **{rt.get('turnover_rate', 'N/A')}%** | |
| 市盈率(动态) | {rt.get('pe_ratio', 'N/A')} | |
| 市净率 | {rt.get('pb_ratio', 'N/A')} | |
| 总市值 | {self._format_amount(rt.get('total_mv'))} | |
| 流通市值 | {self._format_amount(rt.get('circ_mv'))} | |
| 60日涨跌幅 | {rt.get('change_60d', 'N/A')}% | 中期表现 |
"""
        
        # 添加筹码分布数据
        if 'chip' in context:
            chip = context['chip']
            profit_ratio = chip.get('profit_ratio', 0)
            prompt += f"""
### 筹码分布数据（效率指标）
| 指标 | 数值 | 健康标准 |
|------|------|----------|
| **获利比例** | **{profit_ratio:.1%}** | 70-90%时警惕 |
| 平均成本 | {chip.get('avg_cost', 'N/A')} 元 | 现价应高于5-15% |
| 90%筹码集中度 | {chip.get('concentration_90', 0):.2%} | <15%为集中 |
| 70%筹码集中度 | {chip.get('concentration_70', 0):.2%} | |
| 筹码状态 | {chip.get('chip_status', '未知')} | |
"""
        
        # 添加趋势分析结果（基于交易理念的预判）
        if 'trend_analysis' in context:
            trend = context['trend_analysis']
            bias_ma5 = float(trend.get('bias_ma5') or 0)
            bias_threshold = float(trend.get('adaptive_bias_threshold') or 5)
            support_tolerance_pct = float(trend.get('adaptive_support_tolerance') or 0.02) * 100
            bias_warning = f"🚨 超过{bias_threshold:.2f}%，严禁追高！" if bias_ma5 > bias_threshold else "✅ 安全范围"
            support_confirmation = trend.get('support_confirmation') or '暂无明确K线支撑确认'
            rs_period = int(trend.get('relative_strength_period') or 20)
            rs_status = trend.get('relative_strength_status') or '未提供基准/行业数据'
            rs_summary = trend.get('relative_strength_summary') or '暂无相对强弱数据'
            rs_score = int(float(trend.get('relative_strength_score') or 0))
            sector_name = trend.get('sector_name') or '未提供'
            ma20_breakdown_text = '是' if trend.get('ma20_breakdown') else '否'
            support_levels = trend.get('support_levels') or []
            resistance_levels = trend.get('resistance_levels') or []
            support_text = ', '.join(f"{level:.2f}" for level in support_levels[:3]) if support_levels else '无'
            resistance_text = ', '.join(f"{level:.2f}" for level in resistance_levels[:3]) if resistance_levels else '无'
            instrument_type = trend.get('instrument_type') or '普通股票'
            strategy_profile = trend.get('strategy_profile') or '普通股票趋势回踩策略'
            strategy_notes = '；'.join(trend.get('strategy_notes') or []) or '按普通趋势回踩纪律处理'
            breakout_extension_threshold = float(trend.get('breakout_extension_threshold') or bias_threshold)
            breakout_reasons = trend.get('breakout_reasons') or []
            breakout_risks = trend.get('breakout_risks') or []
            breakout_detail = '；'.join(breakout_reasons) or trend.get('breakout_status') or '无明确突破'
            breakout_risk_text = '；'.join(breakout_risks) or '无'
            prompt += f"""
### 趋势分析预判（基于交易理念）
| 指标 | 数值 | 判定 |
|------|------|------|
| 品种策略 | {instrument_type} / {strategy_profile} | {strategy_notes} |
| 趋势状态 | {trend.get('trend_status', '未知')} | |
| 均线排列 | {trend.get('ma_alignment', '未知')} | MA5>MA10>MA20为多头 |
| 当前价 | {trend.get('current_price', 'N/A')} | |
| MA5/MA10/MA20/MA60 | {trend.get('ma5', 'N/A')} / {trend.get('ma10', 'N/A')} / {trend.get('ma20', 'N/A')} / {trend.get('ma60', 'N/A')} | |
| 趋势强度 | {trend.get('trend_strength', 0)}/100 | |
| **乖离率(MA5)** | **{trend.get('bias_ma5', 0):+.2f}%** | {bias_warning} |
| 乖离率(MA10) | {trend.get('bias_ma10', 0):+.2f}% | |
| ATR20 / ATR占比 | {trend.get('atr_20', 0):.2f} / {trend.get('atr_pct', 0):.2f}% | 用于自适应阈值和止损 |
| 20日收益波动率 | {trend.get('volatility_20d', 0):.2f}% | 辅助识别波动环境 |
| 自适应追高线 | {bias_threshold:.2f}% | 默认最高5%，低波动标的收紧 |
| 自适应支撑容忍度 | {support_tolerance_pct:.2f}% | MA5/MA10支撑判定使用 |
| {rs_period}日个股/大盘/行业收益 | {trend.get('stock_return_20d', 0):+.2f}% / {trend.get('benchmark_return_20d', 0):+.2f}% / {trend.get('sector_return_20d', 0):+.2f}% | 行业：{sector_name} |
| 相对大盘/相对行业 | {trend.get('stock_vs_benchmark', 0):+.2f}pct / {trend.get('stock_vs_sector', 0):+.2f}pct | 用于识别是否强于市场与所属行业 |
| RS结论 | {rs_status}（RS {rs_score:+d}） | {rs_summary} |
| MA5/MA10支撑确认 | {trend.get('support_ma5', False)} / {trend.get('support_ma10', False)} | 必须有K线确认才算有效支撑 |
| 回踩收回MA5/MA10 | {trend.get('ma5_touch_reclaim', False)} / {trend.get('ma10_touch_reclaim', False)} | low<=均线且close>=均线 |
| 阳线/下影线 | {trend.get('bullish_candle', False)} / {trend.get('lower_shadow_ratio', 0):.2f}% | 下影线表示承接 |
| 连续守住MA5/MA10 | {trend.get('ma5_hold_days', 0)}日 / {trend.get('ma10_hold_days', 0)}日 | 连续未跌破关键均线 |
| 是否跌破MA20 | {ma20_breakdown_text} | 跌破则买入信号失效或降级 |
| K线支撑结论 | {support_confirmation} | |
| 形态信号 | {trend.get('pattern_signal', '回踩优先')} | 回踩策略与突破策略分开处理 |
| 突破结论 | {trend.get('breakout_status', '无明确突破')} | {breakout_detail} |
| 突破位/突破分 | {trend.get('breakout_level', 0):.2f} / {trend.get('breakout_score', 0):+d} | 有效突破：{trend.get('breakout_valid', False)} |
| 突破延伸线 | {breakout_extension_threshold:.2f}% | 超过则视为突破后追高 |
| 突破风险 | {breakout_risk_text} | |
| 量能状态 | {trend.get('volume_status', '未知')} | {trend.get('volume_trend', '')} |
| 规则支撑位 | {support_text} | 优先参考 MA5/MA10/MA20 附近支撑 |
| 规则压力位 | {resistance_text} | 目标位优先参考近期压力 |
| 系统信号 | {trend.get('buy_signal', '未知')} | |
| 系统评分 | {trend.get('signal_score', 0)}/100 | |
| 规则理想买点 | {trend.get('ideal_buy', 'N/A')} | 由规则层计算，LLM不得自行改写 |
| 规则次优买点 | {trend.get('secondary_buy', 'N/A')} | 由规则层计算，LLM不得自行改写 |
| 规则止损位 | {trend.get('stop_loss', 'N/A')} | 由规则层计算，LLM不得自行改写 |
| 规则目标位 | {trend.get('take_profit', 'N/A')} | 由规则层计算，LLM不得自行改写 |
| 规则盈亏比 | {trend.get('risk_reward_ratio', 0):.2f} | <1.2不买，1.2-1.8低仓试探，>=1.8正常仓位 |
| 失效条件 | {trend.get('invalidation_condition', 'N/A')} | |
| 规则建议仓位 | {trend.get('final_position_pct', 0):.1f}% | 由规则层按评分×大盘×盈亏比×单票风险预算计算 |
| 基础/市场/盈亏比乘数 | {trend.get('base_position_pct', 0):.1f}% / {trend.get('market_position_multiplier', 0):.2f} / {trend.get('risk_reward_position_multiplier', 0):.2f} | |
| 单票风险距离/仓位上限 | {trend.get('single_trade_risk_pct', 0):.2f}% / {trend.get('max_position_by_risk_pct', 0):.1f}% | |
| 仓位提示 | {trend.get('position_note', 'N/A')} | LLM不得自行放大仓位 |
| 中期趋势 | {trend.get('ma60_trend', '未知')} | MA60斜率 {trend.get('ma60_slope', 0):+.2f}% |

### 硬规则约束（最终 JSON 必须服从）
- 若乖离率(MA5) > 自适应追高线（当前{bias_threshold:.2f}%），operation_advice 不得输出“买入/加仓/强烈买入”，必须以“观望”为主。
- 例外：仅当规则层标记有效突破/趋势加速，且 MA5 乖离未超过突破延伸线（当前{breakout_extension_threshold:.2f}%）时，才可按突破策略低仓试探；超过延伸线仍必须观望。
- 若趋势状态为空头排列/强势空头，operation_advice 不得输出买入类建议。
- 若筹码获利比例过高且筹码分散，必须在 risk_warning 和 risk_alerts 中明确提示获利盘兑现风险。
- 买点、止损、目标位、盈亏比必须使用规则层给出的数值，LLM 只解释来源，不得自行创造点位。
- 若规则盈亏比 < 1.2，operation_advice 不得输出买入类建议；1.2-1.8 之间只能低仓试探。
- 若收盘跌破 MA20，operation_advice 不得输出买入/加仓/强烈买入。
- 仓位必须使用规则建议仓位；不得自行放大，规则建议仓位为0%时不得输出买入/加仓/强烈买入。
- 若市场环境为偏弱/极弱，不得输出高置信度买入；极弱环境且个股非强势多头时，优先观望并降低仓位。
- 若官方公告出现减持、处罚、立案、预亏、解禁、退市等风险，必须优先写入 risk_warning 和 risk_alerts，并降低买入置信度。

#### 系统分析理由
**买入理由**：
{chr(10).join('- ' + r for r in trend.get('signal_reasons', ['无'])) if trend.get('signal_reasons') else '- 无'}

**风险因素**：
{chr(10).join('- ' + r for r in trend.get('risk_factors', ['无'])) if trend.get('risk_factors') else '- 无'}
"""
        
        # 添加昨日对比数据
        if 'yesterday' in context:
            volume_change = context.get('volume_change_ratio', 'N/A')
            prompt += f"""
### 量价变化
- 成交量较昨日变化：{volume_change}倍
- 价格较昨日变化：{context.get('price_change_ratio', 'N/A')}%
"""

        if context.get('company_intel_context'):
            prompt += f"""
---

## 🧾 官方公告、解禁与财务数据
以下信息来自官方公告、限售解禁或结构化财务接口，优先级高于搜索摘要；如与搜索结果冲突，以官方公告和结构化数据为准。

```
{context.get('company_intel_context')}
```
"""
        
        # 添加新闻搜索结果（重点区域）
        prompt += """
---

## 📰 舆情情报
"""
        if news_context:
            prompt += f"""
以下是 **{stock_name}({code})** 近7日的新闻搜索结果，请重点提取：
1. 🚨 **风险警报**：减持、处罚、利空
2. 🎯 **利好催化**：业绩、合同、政策
3. 📊 **业绩预期**：年报预告、业绩快报

```
{news_context}
```
"""
        else:
            prompt += """
未搜索到该股票近期的相关新闻。请主要依据技术面数据进行分析。
"""
        
        # 明确的输出要求
        prompt += f"""
---

## ✅ 分析任务

请为 **{stock_name}({code})** 生成【决策仪表盘】，严格按照 JSON 格式输出。

### 重点关注（必须明确回答）：
1. ❓ 是否满足 MA5>MA10>MA20 多头排列？
2. ❓ 当前乖离率是否在安全范围内（低于规则层自适应追高线）？—— 超过纪律线必须标注"严禁追高"
3. ❓ 量能是否配合（缩量回调/放量突破）？
4. ❓ 筹码结构是否健康？
5. ❓ 消息面有无重大利空？（减持、处罚、业绩变脸等）

### 决策仪表盘要求：
- **核心结论**：一句话说清该买/该卖/该等
- **持仓分类建议**：空仓者怎么做 vs 持仓者怎么做
- **具体狙击点位**：使用规则层提供的买入价、止损价、目标价和盈亏比（精确到分），只解释不改写
- **仓位策略**：使用规则层建议仓位和风控上限，只解释不放大
- **检查清单**：每项用 ✅/⚠️/❌ 标记

请输出完整的 JSON 格式决策仪表盘。"""
        
        return prompt
    
    def _format_volume(self, volume: Optional[float]) -> str:
        """格式化成交量显示"""
        if volume is None:
            return 'N/A'
        if volume >= 1e8:
            return f"{volume / 1e8:.2f} 亿股"
        elif volume >= 1e4:
            return f"{volume / 1e4:.2f} 万股"
        else:
            return f"{volume:.0f} 股"
    
    def _format_amount(self, amount: Optional[float]) -> str:
        """格式化成交额显示"""
        if amount is None:
            return 'N/A'
        if amount >= 1e8:
            return f"{amount / 1e8:.2f} 亿元"
        elif amount >= 1e4:
            return f"{amount / 1e4:.2f} 万元"
        else:
            return f"{amount:.0f} 元"
    
    def _parse_response(
        self, 
        response_text: str, 
        code: str, 
        name: str
    ) -> AnalysisResult:
        """
        解析 LLM 响应（决策仪表盘版）
        
        尝试从响应中提取 JSON 格式的分析结果，包含 dashboard 字段
        如果解析失败，尝试智能提取或返回默认结果
        """
        try:
            # 清理响应文本：移除 markdown 代码块标记
            cleaned_text = response_text
            if '```json' in cleaned_text:
                cleaned_text = cleaned_text.replace('```json', '').replace('```', '')
            elif '```' in cleaned_text:
                cleaned_text = cleaned_text.replace('```', '')
            
            # 尝试找到 JSON 内容
            json_start = cleaned_text.find('{')
            json_end = cleaned_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = cleaned_text[json_start:json_end]
                
                # 尝试修复常见的 JSON 问题
                json_str = self._fix_json_string(json_str)
                
                data = json.loads(json_str)
                
                # 提取 dashboard 数据
                dashboard = data.get('dashboard', None)
                
                # 解析所有字段，使用默认值防止缺失
                return AnalysisResult(
                    code=code,
                    name=name,
                    # 核心指标
                    sentiment_score=int(data.get('sentiment_score', 50)),
                    trend_prediction=data.get('trend_prediction', '震荡'),
                    operation_advice=data.get('operation_advice', '持有'),
                    confidence_level=data.get('confidence_level', '中'),
                    # 决策仪表盘
                    dashboard=dashboard,
                    # 走势分析
                    trend_analysis=data.get('trend_analysis', ''),
                    short_term_outlook=data.get('short_term_outlook', ''),
                    medium_term_outlook=data.get('medium_term_outlook', ''),
                    # 技术面
                    technical_analysis=data.get('technical_analysis', ''),
                    ma_analysis=data.get('ma_analysis', ''),
                    volume_analysis=data.get('volume_analysis', ''),
                    pattern_analysis=data.get('pattern_analysis', ''),
                    # 基本面
                    fundamental_analysis=data.get('fundamental_analysis', ''),
                    sector_position=data.get('sector_position', ''),
                    company_highlights=data.get('company_highlights', ''),
                    # 情绪面/消息面
                    news_summary=data.get('news_summary', ''),
                    market_sentiment=data.get('market_sentiment', ''),
                    hot_topics=data.get('hot_topics', ''),
                    # 综合
                    analysis_summary=data.get('analysis_summary', '分析完成'),
                    key_points=data.get('key_points', ''),
                    risk_warning=data.get('risk_warning', ''),
                    buy_reason=data.get('buy_reason', ''),
                    # 元数据
                    search_performed=data.get('search_performed', False),
                    data_sources=data.get('data_sources', '技术面数据'),
                    success=True,
                )
            else:
                # 没有找到 JSON，尝试从纯文本中提取信息
                logger.warning(f"无法从响应中提取 JSON，使用原始文本分析")
                return self._parse_text_response(response_text, code, name)
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}，尝试从文本提取")
            return self._parse_text_response(response_text, code, name)
    
    def _apply_hard_rules(self, result: AnalysisResult, context: Dict[str, Any]) -> AnalysisResult:
        """Apply non-negotiable trading discipline after LLM parsing."""
        trend = context.get('trend_analysis') or {}
        chip = context.get('chip') or {}
        company_intel = context.get('company_intel') or {}
        market_context = context.get('market_context') or {}
        market_environment = market_context.get('environment') or {}
        warnings = []
        buy_advices = {'买入', '加仓', '强烈买入'}

        bias_ma5 = float(trend.get('bias_ma5') or 0)
        trend_status = str(trend.get('trend_status') or '')
        market_status = str(market_environment.get('market_status') or '')
        risk_reward_ratio = float(trend.get('risk_reward_ratio') or 0)
        final_position_pct = float(trend.get('final_position_pct') or 0)
        position_note = str(trend.get('position_note') or '')
        single_trade_risk_pct = float(trend.get('single_trade_risk_pct') or 0)
        max_position_by_risk_pct = float(trend.get('max_position_by_risk_pct') or 0)
        bias_threshold = float(trend.get('adaptive_bias_threshold') or 5)
        ma20_breakdown = bool(trend.get('ma20_breakdown'))
        relative_strength_score = int(float(trend.get('relative_strength_score') or 0))
        relative_strength_status = str(trend.get('relative_strength_status') or '')
        breakout_valid = bool(trend.get('breakout_valid'))
        breakout_extension_threshold = float(trend.get('breakout_extension_threshold') or bias_threshold)
        breakout_status = str(trend.get('breakout_status') or '')
        instrument_type = str(trend.get('instrument_type') or '普通股票')
        official_risk_flags = list(company_intel.get('risk_flags') or [])

        if risk_reward_ratio and risk_reward_ratio < 1.2 and result.operation_advice in buy_advices:
            result.operation_advice = '观望'
            result.trend_prediction = '震荡'
            result.sentiment_score = min(result.sentiment_score, 59)
            result.confidence_level = '中'
            warnings.append(f"规则盈亏比为{risk_reward_ratio:.2f}，低于1.20，不满足买入纪律")
        elif 1.2 <= risk_reward_ratio < 1.8:
            if result.confidence_level == '高':
                result.confidence_level = '中'
            if result.operation_advice in buy_advices:
                result.sentiment_score = min(result.sentiment_score, 69)
            warnings.append(f"规则盈亏比为{risk_reward_ratio:.2f}，仅适合低仓试探")
        if bias_ma5 > bias_threshold and result.operation_advice in buy_advices:
            if breakout_valid and bias_ma5 <= breakout_extension_threshold:
                result.sentiment_score = min(result.sentiment_score, 79)
                if result.confidence_level == '高':
                    result.confidence_level = '中'
                warnings.append(
                    f"乖离率MA5为{bias_ma5:.2f}%，超过{bias_threshold:.2f}%回踩纪律线；"
                    f"但规则层确认有效突破（{breakout_status}），未超过{breakout_extension_threshold:.2f}%突破延伸线，"
                    "只能按突破策略和规则仓位试探"
                )
            else:
                result.operation_advice = '观望'
                result.trend_prediction = '震荡'
                result.sentiment_score = min(result.sentiment_score, 59)
                result.confidence_level = '中'
                warnings.append(
                    f"乖离率MA5为{bias_ma5:.2f}%，超过{bias_threshold:.2f}%纪律线，"
                    f"且无有效突破确认或已超过{breakout_extension_threshold:.2f}%突破延伸线，禁止追高"
                )

        if any(status in trend_status for status in ['空头排列', '强势空头']) and result.operation_advice in buy_advices:
            result.operation_advice = '观望'
            result.trend_prediction = '看空'
            result.sentiment_score = min(result.sentiment_score, 39)
            result.confidence_level = '中'
            warnings.append(f"趋势状态为{trend_status}，不允许买入类建议")

        if ma20_breakdown and result.operation_advice in buy_advices:
            result.operation_advice = '观望'
            result.trend_prediction = '震荡'
            result.sentiment_score = min(result.sentiment_score, 49)
            result.confidence_level = '中'
            warnings.append("收盘跌破MA20，买入信号失效或降级")

        if relative_strength_score <= -6 and result.operation_advice in buy_advices:
            result.sentiment_score = min(result.sentiment_score, 69)
            if result.confidence_level == '高':
                result.confidence_level = '中'
            warnings.append(f"相对强弱{relative_strength_status}，不支持高置信度买入")

        if official_risk_flags:
            risk_summary = "；".join(str(flag) for flag in official_risk_flags[:3])
            warnings.append(f"官方公告/财务风险：{risk_summary}")
            if result.operation_advice in buy_advices:
                severe_keywords = ['处罚', '立案', '预亏', '退市', '亏损']
                if any(keyword in risk_summary for keyword in severe_keywords):
                    result.sentiment_score = min(result.sentiment_score, 59)
                    result.operation_advice = '观望'
                    result.trend_prediction = '震荡'
                else:
                    result.sentiment_score = min(result.sentiment_score, 69)
                if result.confidence_level == '高':
                    result.confidence_level = '中'

        if final_position_pct <= 0 and result.operation_advice in buy_advices:
            result.operation_advice = '观望'
            result.trend_prediction = '震荡'
            result.sentiment_score = min(result.sentiment_score, 59)
            result.confidence_level = '中'
            warnings.append("规则仓位模型建议0%，不允许买入类建议")
        elif 0 < final_position_pct <= 10 and result.operation_advice in buy_advices:
            if result.confidence_level == '高':
                result.confidence_level = '中'
            result.sentiment_score = min(result.sentiment_score, 69)
            warnings.append(f"规则建议仓位仅{final_position_pct:.1f}%，只能低仓位试探")

        if market_status == '极弱':
            if result.operation_advice in buy_advices:
                result.operation_advice = '观望'
                result.trend_prediction = '震荡'
            result.sentiment_score = min(result.sentiment_score, 55)
            result.confidence_level = '低' if result.confidence_level == '高' else result.confidence_level
            warnings.append("大盘环境极弱，优先控制仓位并等待市场企稳")
        elif market_status == '偏弱':
            if result.confidence_level == '高':
                result.confidence_level = '中'
            if result.operation_advice in buy_advices:
                result.sentiment_score = min(result.sentiment_score, 65)
            warnings.append("大盘环境偏弱，买入类操作需降低仓位并等待确认")

        profit_ratio = float(chip.get('profit_ratio') or 0)
        concentration_90 = float(chip.get('concentration_90') or 0)
        if profit_ratio >= 0.9 and concentration_90 >= 0.15:
            warnings.append(f"获利比例{profit_ratio:.1%}且90%筹码集中度{concentration_90:.2%}，需警惕获利盘兑现")
            result.sentiment_score = min(result.sentiment_score, 69)
            if result.confidence_level == '高':
                result.confidence_level = '中'

        support_levels = trend.get('support_levels') or []
        resistance_levels = trend.get('resistance_levels') or []
        primary_support = min(support_levels, key=lambda x: abs(x - float(trend.get('current_price') or x))) if support_levels else None
        primary_resistance = min(resistance_levels) if resistance_levels else None

        if result.dashboard:
            if official_risk_flags:
                intelligence = result.dashboard.setdefault('intelligence', {})
                risk_alerts = intelligence.setdefault('risk_alerts', [])
                for flag in official_risk_flags[:5]:
                    text = f"官方公告/财务风险：{flag}"
                    if text not in risk_alerts:
                        risk_alerts.append(text)

            data_perspective = result.dashboard.setdefault('data_perspective', {})
            data_perspective['instrument_strategy'] = {
                'instrument_type': instrument_type,
                'strategy_profile': str(trend.get('strategy_profile') or ''),
                'strategy_notes': trend.get('strategy_notes') or [],
            }
            data_perspective['pattern_status'] = {
                'pattern_signal': str(trend.get('pattern_signal') or ''),
                'breakout_status': breakout_status,
                'breakout_score': int(float(trend.get('breakout_score') or 0)),
                'breakout_level': float(trend.get('breakout_level') or 0),
                'breakout_extension_threshold': breakout_extension_threshold,
            }
            price_position = data_perspective.setdefault('price_position', {})
            if primary_support is not None:
                price_position['support_level'] = round(float(primary_support), 2)
            if primary_resistance is not None:
                price_position['resistance_level'] = round(float(primary_resistance), 2)

            battle_plan = result.dashboard.setdefault('battle_plan', {})
            sniper_points = battle_plan.setdefault('sniper_points', {})
            if trend.get('ideal_buy'):
                sniper_points['ideal_buy'] = f"规则层理想买入点：{float(trend['ideal_buy']):.2f}元"
            if trend.get('secondary_buy'):
                sniper_points['secondary_buy'] = f"规则层次优买入点：{float(trend['secondary_buy']):.2f}元"
            if trend.get('stop_loss'):
                sniper_points['stop_loss'] = f"规则层止损位：{float(trend['stop_loss']):.2f}元"
            if trend.get('take_profit'):
                sniper_points['take_profit'] = f"规则层目标位：{float(trend['take_profit']):.2f}元"
            if risk_reward_ratio:
                sniper_points['risk_reward_ratio'] = f"规则层盈亏比：{risk_reward_ratio:.2f}"
            if trend.get('invalidation_condition'):
                sniper_points['invalidation_condition'] = trend['invalidation_condition']

            position_strategy = battle_plan.setdefault('position_strategy', {})
            if final_position_pct <= 0:
                position_strategy['suggested_position'] = '规则层建议仓位：0.0%（不开新仓）'
                position_strategy['entry_plan'] = '等待评分、市场环境、盈亏比或止损距离改善后再评估'
            elif final_position_pct <= 10:
                position_strategy['suggested_position'] = f"规则层建议仓位：{final_position_pct:.1f}%（低仓试探）"
                position_strategy['entry_plan'] = '仅在规则买点附近分批试探，不追高加仓'
            else:
                position_strategy['suggested_position'] = f"规则层建议仓位：{final_position_pct:.1f}%"
                position_strategy['entry_plan'] = '按规则买点分批执行，未触发买点则等待'

            risk_control_parts = []
            if trend.get('stop_loss'):
                risk_control_parts.append(f"止损位使用规则层{float(trend['stop_loss']):.2f}元")
            if single_trade_risk_pct:
                risk_control_parts.append(f"单票风险距离{single_trade_risk_pct:.2f}%")
            if max_position_by_risk_pct:
                risk_control_parts.append(f"单票风险预算仓位上限{max_position_by_risk_pct:.1f}%")
            if position_note:
                risk_control_parts.append(position_note)
            position_strategy['risk_control'] = '；'.join(risk_control_parts) or '遵守规则层止损和仓位上限'

        if warnings:
            result.risk_warning = self._append_warnings(result.risk_warning, warnings)
            if result.dashboard:
                intelligence = result.dashboard.setdefault('intelligence', {})
                risk_alerts = intelligence.setdefault('risk_alerts', [])
                for warning in warnings:
                    if warning not in risk_alerts:
                        risk_alerts.append(warning)
                core = result.dashboard.get('core_conclusion', {})
                if core and result.operation_advice == '观望':
                    if market_status == '极弱':
                        core['one_sentence'] = '大盘环境极弱，暂以观望为主'
                    else:
                        core['one_sentence'] = '硬规则触发，暂以观望为主'
                    core['signal_type'] = '🟡持有观望'
                    position_advice = core.setdefault('position_advice', {})
                    if market_status == '极弱':
                        position_advice['no_position'] = '空仓等待市场企稳后再寻找回踩买点'
                    else:
                        position_advice['no_position'] = '空仓等待回踩到规则支撑位附近，不追高买入'
                battle_plan = result.dashboard.setdefault('battle_plan', {})
                position_strategy = battle_plan.setdefault('position_strategy', {})
                if result.operation_advice == '观望':
                    position_strategy['suggested_position'] = '规则层建议仓位：0.0%（不开新仓）' if final_position_pct <= 0 else f"规则层建议仓位：{final_position_pct:.1f}%（仅观察，不主动加仓）"
                elif risk_reward_ratio and risk_reward_ratio < 1.8 and result.operation_advice in buy_advices:
                    position_strategy['suggested_position'] = f"规则层建议仓位：{final_position_pct:.1f}%（低仓位试探）"
                elif market_status == '偏弱' and result.operation_advice in buy_advices:
                    position_strategy['suggested_position'] = f"规则层建议仓位：{final_position_pct:.1f}%（等待市场确认）"

        return result

    @staticmethod
    def _append_warnings(existing: str, warnings: List[str]) -> str:
        parts = [existing] if existing else []
        parts.extend(warnings)
        return '；'.join(part for part in parts if part)

    def _fix_json_string(self, json_str: str) -> str:
        """修复常见的 JSON 格式问题"""
        import re
        
        # 移除注释
        json_str = re.sub(r'//.*?\n', '\n', json_str)
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
        
        # 修复尾随逗号
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        # 确保布尔值是小写
        json_str = json_str.replace('True', 'true').replace('False', 'false')
        
        return json_str
    
    def _parse_text_response(
        self, 
        response_text: str, 
        code: str, 
        name: str
    ) -> AnalysisResult:
        """从纯文本响应中尽可能提取分析信息"""
        # 尝试识别关键词来判断情绪
        sentiment_score = 50
        trend = '震荡'
        advice = '持有'
        
        text_lower = response_text.lower()
        
        # 简单的情绪识别
        positive_keywords = ['看多', '买入', '上涨', '突破', '强势', '利好', '加仓', 'bullish', 'buy']
        negative_keywords = ['看空', '卖出', '下跌', '跌破', '弱势', '利空', '减仓', 'bearish', 'sell']
        
        positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
        negative_count = sum(1 for kw in negative_keywords if kw in text_lower)
        
        if positive_count > negative_count + 1:
            sentiment_score = 65
            trend = '看多'
            advice = '买入'
        elif negative_count > positive_count + 1:
            sentiment_score = 35
            trend = '看空'
            advice = '卖出'
        
        # 截取前500字符作为摘要
        summary = response_text[:500] if response_text else '无分析结果'
        
        return AnalysisResult(
            code=code,
            name=name,
            sentiment_score=sentiment_score,
            trend_prediction=trend,
            operation_advice=advice,
            confidence_level='低',
            analysis_summary=summary,
            key_points='JSON解析失败，仅供参考',
            risk_warning='分析结果可能不准确，建议结合其他信息判断',
            raw_response=response_text,
            success=True,
        )
    
    def batch_analyze(
        self, 
        contexts: List[Dict[str, Any]],
        delay_between: float = 2.0
    ) -> List[AnalysisResult]:
        """
        批量分析多只股票
        
        注意：为避免 API 速率限制，每次分析之间会有延迟
        
        Args:
            contexts: 上下文数据列表
            delay_between: 每次分析之间的延迟（秒）
            
        Returns:
            AnalysisResult 列表
        """
        results = []
        
        for i, context in enumerate(contexts):
            if i > 0:
                logger.debug(f"等待 {delay_between} 秒后继续...")
                time.sleep(delay_between)
            
            result = self.analyze(context)
            results.append(result)
        
        return results


# 便捷函数
def get_analyzer() -> OpenAIAnalyzer:
    """获取 OpenAI 兼容分析器实例"""
    return OpenAIAnalyzer()


GeminiAnalyzer = OpenAIAnalyzer


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.DEBUG)
    
    # 模拟上下文数据
    test_context = {
        'code': '600519',
        'date': '2026-01-09',
        'today': {
            'open': 1800.0,
            'high': 1850.0,
            'low': 1780.0,
            'close': 1820.0,
            'volume': 10000000,
            'amount': 18200000000,
            'pct_chg': 1.5,
            'ma5': 1810.0,
            'ma10': 1800.0,
            'ma20': 1790.0,
            'volume_ratio': 1.2,
        },
        'ma_status': '多头排列 📈',
        'volume_change_ratio': 1.3,
        'price_change_ratio': 1.5,
    }
    
    analyzer = OpenAIAnalyzer()
    
    if analyzer.is_available():
        print("=== AI 分析测试 ===")
        result = analyzer.analyze(test_context)
        print(f"分析结果: {result.to_dict()}")
    else:
        print("OpenAI 兼容 API 配置未完成，跳过测试")
