# 热点板块 LLM 雷达规划与开发文档

> 本文档用于规划“新闻 + 资金动向 + LLM”的热点板块发现能力，并说明如何与当前规则层选股、个股精细分析链路集成。项目输出仅用于投资研究和自选股复盘辅助，不构成投资建议或自动交易指令。

## 1. 背景与目标

当前项目已经具备自选股日度分析、热门板块规则选股、趋势/相对强弱/突破形态评分、官方公告与财务风险排查、搜索情报补充和 LLM 决策仪表盘等能力。下一阶段希望把系统从“跟踪已有股票池”进一步扩展为“主动发现市场热点并筛选潜在龙头”。

新增能力的目标是构建一条热点发现流水线：

```text
新闻/政策/公告/资金动向
        ↓
LLM 主题聚类与催化归因
        ↓
板块行情与资金共振验证
        ↓
龙头候选规则层筛选
        ↓
Top N 个股精细化分析
        ↓
主题跟踪、复盘与退潮信号
```

核心定位：

1. 发现当日或近期火热主题/板块，而不是只依赖已有自选股。
2. 让 LLM 负责语义聚类、催化逻辑归纳、证据链整理和持续性判断。
3. 让规则层负责候选池排序、追高约束、买点、止损、仓位和风险兜底。
4. 只对高质量 Top N 候选调用现有精细分析链路，控制成本与噪声。
5. 建立可复盘的数据结构，为后续回测主题有效性和龙头筛选质量做准备。

## 2. 设计边界

### 2.1 LLM 负责什么

LLM 适合处理非结构化信息和跨新闻事件的语义归纳：

- 将新闻、政策、公告、产业事件聚类成若干主题。
- 提炼每个主题的核心催化，例如政策驱动、产业趋势、订单变化、价格上涨、技术突破等。
- 判断主题与行业/概念板块的对应关系。
- 总结证据链，包括新闻标题、来源、时间、摘要和关联标的。
- 给出主题持续性、扩散程度、短期风险和后续验证信号。

### 2.2 LLM 不负责什么

以下内容不得由 LLM 自由生成或直接决定：

- 个股买卖结论。
- 买点、止损、目标价、仓位。
- 无证据的板块归因或龙头断言。
- 对资金流、成交额、涨幅等结构化指标的臆造。
- 对官方公告、财务风险、解禁风险的优先级覆盖。

这些内容继续由现有规则层、结构化数据和硬规则后处理负责。

## 3. 现有能力复用清单

### 3.1 热门板块规则选股

复用 `stock_screener.py`：

- `StockScreener.screen_hot_sectors()`：基于热门行业/概念板块生成候选池。
- `SectorCandidate`：表示进入粗筛的热门板块。
- `ScreenedStock`：表示规则层筛出的个股候选。
- `ScreeningResult`：保存板块、候选股、入选股、过滤原因和精细报告。
- `ScreeningResult.format_report()`：输出规则层选股 Markdown 报告。

该模块已实现低成本粗筛和排序，是热点雷达后半段的核心复用能力。

### 3.2 板块与行情数据

复用 `data_provider/akshare_fetcher.py`：

- `AkshareFetcher.get_hot_sectors()`：获取当日热门行业/概念板块。
- `AkshareFetcher.get_sector_constituents()`：获取板块成分股。
- `AkshareFetcher.get_sector_daily_data()`：获取板块日线，用于板块趋势和相对强弱。
- `AkshareFetcher.get_index_daily_data()`：获取宽基指数日线，用作相对强弱基准。

后续资金增强可继续在该数据适配层扩展主力资金、行业资金、ETF 资金、龙虎榜等接口。

### 3.3 市场环境

复用 `market_analyzer.py`：

- `MarketAnalyzer.get_market_overview()`：获取指数、涨跌家数、涨停跌停、成交额、北向资金、领涨/领跌板块。
- `evaluate_market_environment()`：输出市场评分、市场状态、风险等级、板块热度摘要。

热点主题的置信度应受到市场环境约束：弱市中的热点更强调低仓观察和持续性验证，强势环境中的热点可更积极进入候选池。

### 3.4 个股趋势与规则层评分

复用 `stock_analyzer.py`：

- `StockTrendAnalyzer.analyze()`：计算趋势状态、均线、乖离、量能、ATR、自适应追高线、相对强弱、支撑确认、突破形态、盈亏比和规则仓位。
- `TrendAnalysisResult`：为候选龙头评分提供结构化指标。

热点雷达不重新实现买点逻辑，而是使用现有趋势交易规则。

### 3.5 个股精细分析

复用 `main.py`：

- `StockAnalysisPipeline.analyze_stock()`：对 Top N 候选股运行现有精细分析流程。

该流程已经整合实时行情、筹码、官方公告、结构化财务、趋势分析、搜索情报、大盘环境和 LLM 决策仪表盘。

### 3.6 新闻与公司情报

复用并扩展：

- `search_service.py`：已有 Tavily/SerpAPI 搜索抽象，可扩展主题新闻搜索、政策搜索、产业链搜索。
- `company_intel.py`：已有官方公告、限售解禁、财务指标整理。官方风险优先级高于搜索摘要和 LLM 判断。

## 4. 总体架构

### 4.1 数据采集层

输入数据分为三类：

1. 非结构化文本：财经新闻、政策、产业事件、公司公告标题、研报摘要等。
2. 结构化市场数据：板块涨跌幅、成交额、换手率、领涨股、指数表现、涨跌家数、涨停跌停、北向资金。
3. 结构化个股数据：日线、实时行情、相对强弱、突破状态、公告/财务/解禁风险。

MVP 可先复用现有搜索服务和 AkShare 板块数据，资金项先使用当前可稳定获取的板块涨幅、成交额、换手率、领涨股、北向资金等。

### 4.2 主题发现层

主题发现层负责把新闻与市场现象组织成候选主题：

```text
搜索结果 + 热门板块 + 市场环境
        ↓
构造 LLM 主题发现 prompt
        ↓
输出严格 JSON：主题、催化、证据、关联板块、风险、置信度
```

LLM 输出应包含证据 ID，确保每个主题都能追溯到输入数据。

### 4.3 板块验证层

板块验证层用结构化数据检查 LLM 发现的主题是否得到市场验证：

- 关联板块是否在涨幅榜或成交额榜靠前。
- 板块是否强于主要指数。
- 板块内上涨扩散度是否足够。
- 板块领涨股是否有持续性，而非单日脉冲。
- 是否存在相反证据，例如板块高开低走、放量滞涨、核心股冲高回落。

验证结果进入主题热度分和风险提示。

### 4.4 龙头筛选层

龙头筛选层不直接听从 LLM 的“龙头”判断，而是按规则层排序：

- 优先使用板块接口返回的领涨股作为初始线索。
- 使用 `StockScreener` 获取板块成分股并过滤 ST、停牌、成交额过低、历史数据不足、过度追高等标的。
- 使用 `StockTrendAnalyzer` 计算趋势、相对强弱、突破、回踩、仓位和风险。
- 结合主题证据相关度、板块内地位、成交额、涨幅强度和官方风险进行综合评分。

### 4.5 精细分析层

对主题雷达筛出的 Top N 个股调用 `StockAnalysisPipeline.analyze_stock()`：

- 获取实时行情和筹码。
- 获取官方公告、财务、解禁。
- 获取新闻与风险搜索结果。
- 注入大盘环境和规则层趋势结果。
- 调用 LLM 生成最终决策仪表盘。
- 经硬规则修正后输出。

### 4.6 输出与跟踪层

输出每日热点雷达 Markdown 报告，并为后续跟踪保存结构化结果：

- 今日热点主题 Top 3-5。
- 每个主题的催化逻辑、证据链、资金验证、关联板块、候选龙头、风险点。
- Top 个股精细分析摘要。
- 过滤和降权原因。
- 后续观察信号，例如政策落地、成交额维持、板块扩散、核心股是否继续强于板块。

## 5. 建议新增模块

### 5.1 `theme_radar.py`

职责：热点主题雷达主编排器。

建议类：`ThemeRadar`。

主要方法：

```python
class ThemeRadar:
    def run(
        self,
        theme_count: int = 5,
        leader_top_n: int = 3,
        lookback_days: int = 7,
        include_detail_analysis: bool = True,
    ) -> ThemeRadarResult:
        ...
```

内部流程：

1. 获取市场环境。
2. 获取热门行业/概念板块。
3. 搜索近期市场热点、政策、产业事件。
4. 构造主题发现输入。
5. 调用 LLM 生成主题候选。
6. 将主题映射到现有板块。
7. 对关联板块调用 `StockScreener` 筛选候选龙头。
8. 对 Top N 调用 `analyze_stock()`。
9. 输出 `ThemeRadarResult` 和 Markdown 报告。

### 5.2 `theme_models.py`

若数据结构较多，建议单独拆分模型文件；MVP 也可先放在 `theme_radar.py`。

建议 dataclass：

```python
@dataclass
class ThemeEvidence:
    id: str
    source: str
    title: str
    summary: str
    published_at: str = ""
    url: str = ""
    related_sectors: list[str] = field(default_factory=list)
    related_stocks: list[str] = field(default_factory=list)

@dataclass
class LeaderCandidate:
    code: str
    name: str
    sector_name: str
    leader_reason: str
    composite_score: float
    rs_score: float = 0.0
    breakout_score: float = 0.0
    liquidity_score: float = 0.0
    risk_flags: list[str] = field(default_factory=list)

@dataclass
class ThemeSignal:
    name: str
    related_sectors: list[str]
    heat_score: float
    news_score: float
    capital_score: float
    market_score: float
    persistence_score: float
    catalysts: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    leader_candidates: list[LeaderCandidate] = field(default_factory=list)
    confidence: str = "中"

@dataclass
class ThemeRadarResult:
    generated_at: str
    market_environment: dict
    themes: list[ThemeSignal]
    selected_stocks: list[LeaderCandidate]
    filtered_reasons: list[dict]
    detailed_results: list = field(default_factory=list)
```

### 5.3 `capital_flow.py`

职责：统一资金动向数据适配。

MVP 可先封装当前较稳定的数据：

- 北向资金净流入。
- 板块成交额。
- 板块换手率。
- 领涨股。
- 个股成交额和换手率。

P1/P2 再补充：

- 行业/概念主力资金流。
- ETF 资金流。
- 龙虎榜。
- 融资融券。
- 大单净流入。

建议对每个资金源打上 `source`、`updated_at`、`reliability`，避免不同接口口径混用后不可解释。

### 5.4 Prompt 组织

可新增 `prompts/theme_discovery.py`，也可先在 `theme_radar.py` 内维护 prompt。

Prompt 设计要求：

- 强制输出 JSON。
- 主题必须引用输入证据 ID。
- 不允许输出无证据主题。
- 主题名称应简洁，例如“AI 应用端扩散”“固态电池产业化”“低空经济政策催化”。
- 每个主题必须给出 `confidence`、`catalysts`、`risks`、`related_sectors`、`evidence_ids`、`unsupported_claims`。
- 如果新闻热但行情未验证，应标注“舆情热、资金未确认”。
- 如果行情强但新闻证据弱，应标注“资金驱动、催化待确认”。

## 6. 核心评分框架

### 6.1 主题总分

建议主题总分满分 100：

| 维度 | 权重 | 说明 |
| --- | ---: | --- |
| 新闻/政策热度 | 25 | 新闻频次、新鲜度、来源权威性、政策或产业催化强度 |
| 资金共振 | 25 | 板块涨幅、成交额、换手率、北向/主力/ETF/龙虎榜等资金信号 |
| 板块强度 | 20 | 板块相对大盘、板块趋势、上涨扩散度、领涨股表现 |
| 龙头质量 | 20 | 候选龙头相对强弱、成交额、突破/回踩质量、不过度追高 |
| 风险与持续性 | 10 | 证据稳定性、退潮风险、政策兑现风险、官方风险扣分 |

### 6.2 主题分层

| 分数 | 分层 | 处理方式 |
| ---: | --- | --- |
| >= 80 | 高热度强验证 | 进入 Top 主题，筛选 Top 龙头并精细分析 |
| 65-79 | 有热度待确认 | 输出观察主题，筛选候选但降低置信度 |
| 50-64 | 单边信号 | 仅记录，不主动进入精细分析 |
| < 50 | 噪声或证据不足 | 不输出或放入附录 |

### 6.3 龙头评分

龙头评分建议复用 `StockScreener` 的综合分，并增加主题相关度：

| 维度 | 建议权重 | 说明 |
| --- | ---: | --- |
| 板块内强度 | 20 | 是否领涨、成交额排名、是否强于板块 |
| 趋势与买点 | 25 | 复用趋势评分、低乖离、回踩确认、突破有效性 |
| 相对强弱 | 15 | 强于大盘、强于行业/概念 |
| 流动性 | 10 | 成交额、换手率、非一字板、可交易性 |
| 主题相关度 | 15 | 是否被新闻/公告/产业链证据明确关联 |
| 风险扣分 | 15 | 官方公告风险、财务风险、解禁风险、过度追高 |

## 7. LLM 输出 JSON 草案

主题发现输出建议：

```json
{
  "generated_at": "2026-05-08 15:30:00",
  "market_summary": "市场偏强，成交额放大，热点集中在 AI 与新能源方向",
  "themes": [
    {
      "name": "AI 应用端扩散",
      "confidence": "高",
      "heat_score": 84,
      "news_score": 22,
      "capital_score": 20,
      "market_score": 18,
      "persistence_score": 14,
      "related_sectors": ["软件开发", "传媒", "算力概念"],
      "catalysts": ["多家公司发布 AI 应用产品", "产业政策继续支持人工智能落地"],
      "risks": ["部分个股短期涨幅较高", "若成交额无法维持，主题可能分化"],
      "evidence_ids": ["news_001", "news_004", "sector_002"],
      "unsupported_claims": []
    }
  ]
}
```

要求：

- `themes` 数量默认 3-5。
- `evidence_ids` 不能为空。
- `unsupported_claims` 非空时，该主题不得进入高置信度。
- 分数用于排序，但最终仍需规则层校验。

## 8. 开发阶段规划

### P0：文档与规则对齐

目标：完成本规划文档，明确系统边界、复用模块、数据结构、CLI 入口和验收方式。

交付物：

- `docs/hot_sector_llm_radar_development_plan.md`。

验收：

- 文档结构完整。
- 与 `docs/strategy_logic_and_optimization.md` 不冲突。
- 明确 LLM 与规则层职责边界。

### P1：MVP 主题雷达

目标：用现有搜索服务和热门板块数据生成主题雷达日报。

建议实现：

1. 新增 `theme_radar.py`。
2. 新增主题数据结构。
3. 复用 `SearchService` 搜索近期市场热点、政策、产业事件。
4. 复用 `AkshareFetcher.get_hot_sectors()` 获取热门板块。
5. 调用 LLM 生成主题 JSON。
6. 将主题映射到板块。
7. 复用 `StockScreener.screen_hot_sectors()` 获取候选股。
8. 输出主题雷达 Markdown 报告。

建议 CLI：

```bash
python main.py --theme-radar
python main.py --theme-radar --theme-top-n 5
python main.py --theme-radar --theme-no-llm-detail
```

验收：

- 无 LLM 精细分析时，也能输出主题 + 板块 + 候选股报告。
- LLM 主题输出能引用证据 ID。
- 主题与板块映射失败时不会臆造，报告中标注“待确认”。

### P2：资金动向增强

目标：让主题热度不仅依赖新闻，还能被资金验证。

建议接入：

- 行业/概念板块成交额和换手率。
- 北向资金方向。
- 主力资金流。
- ETF 资金流。
- 龙虎榜。
- 个股大单净流入。

验收：

- 主题报告区分“新闻热、资金弱”“资金强、新闻弱”“新闻与资金共振”。
- 资金字段带来源和更新时间。
- 资金缺失时按中性处理，不影响基础报告生成。

### P3：主题跟踪闭环

目标：让系统能判断主题延续、分化和退潮。

建议实现：

- 保存每日 `ThemeRadarResult`。
- 记录主题连续出现天数。
- 跟踪主题 Top 龙头次日、3 日、5 日表现。
- 跟踪板块成交额是否维持。
- 标记退潮信号：核心股跌破 MA20、板块成交额萎缩、涨停家数下降、负面公告增多。

验收：

- 报告中出现“新主题 / 延续主题 / 分化主题 / 退潮主题”。
- 能输出主题过去若干日表现。
- 能解释主题降级原因。

### P4：回测与评估

目标：验证主题热度分和龙头筛选分是否有预测价值。

建议指标：

- 主题出现后 1/3/5/10 日板块收益。
- 龙头候选后 1/3/5/10 日收益。
- 最大回撤。
- 胜率。
- 盈亏比。
- 高热度主题与中低热度主题的表现差异。
- LLM 高置信度主题与低置信度主题的表现差异。

验收：

- 输出最小回测报告。
- 可以回答“新闻热度、资金共振、板块强度、龙头质量哪个维度更有效”。
- 可以据此调整权重。

## 9. 报告格式建议

### 9.1 Markdown 报告结构

```markdown
# 热点板块 LLM 雷达日报

> 生成时间：YYYY-MM-DD HH:mm:ss
> 用途：投资研究与复盘辅助，不构成投资建议。

## 1. 市场环境

- 市场状态：偏强/震荡/偏弱
- 市场评分：xx/100
- 成交额：xx 亿
- 北向资金：净流入/净流出 xx 亿
- 领涨板块：...
- 主要风险：...

## 2. 今日热点主题 Top 3-5

| 排名 | 主题 | 置信度 | 热度分 | 新闻验证 | 资金验证 | 关联板块 | 状态 |
| --- | --- | --- | ---: | --- | --- | --- | --- |

## 3. 主题详情

### 主题一：AI 应用端扩散

- 核心催化：...
- 证据链：...
- 资金/行情验证：...
- 关联板块：...
- 候选龙头：...
- 风险点：...
- 后续观察：...

## 4. 候选龙头排序

| 排名 | 代码 | 名称 | 主题 | 板块 | 综合分 | 趋势 | RS | 突破 | 风险 |
| --- | --- | --- | --- | --- | ---: | --- | ---: | --- | --- |

## 5. Top 个股精细报告摘要

复用现有个股决策仪表盘摘要。

## 6. 过滤与降权原因

列出被过滤或降权的高热度股票及原因。
```

### 9.2 主题状态枚举

建议使用以下状态：

- `新发酵`：首次出现或新闻催化明显增强。
- `加速`：新闻与资金共振，板块和核心股继续增强。
- `分化`：主题仍热，但只有少数核心股维持强势。
- `退潮`：成交额萎缩、核心股转弱、负面风险增加。
- `待确认`：新闻或资金只有单边信号，证据不足。

## 10. 风险控制原则

1. 官方公告、财务、解禁风险优先级高于搜索摘要和 LLM 主题判断。
2. 主题热不等于个股可买，个股必须通过趋势、买点、盈亏比和仓位规则。
3. 涨幅过高且超过突破延伸线的股票，即使是龙头也应标注追高风险。
4. 板块强但个股弱于板块，不应作为龙头候选。
5. 新闻密集但板块资金不确认，只能作为观察主题。
6. 资金强但新闻证据不足，应标注“资金驱动，催化待确认”。
7. 弱市中的热点要降低主题置信度或降低精细分析数量。
8. LLM 输出中存在 `unsupported_claims` 时，不允许进入高置信度主题。

## 11. 建议 CLI 与配置

### 11.1 CLI 参数

建议在 `main.py` 后续实现：

```bash
python main.py --theme-radar
python main.py --theme-radar --theme-top-n 5
python main.py --theme-radar --theme-lookback-days 7
python main.py --theme-radar --theme-no-llm-detail
python main.py --theme-radar --theme-include-concepts
```

参数说明：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--theme-radar` | false | 启用热点主题雷达模式 |
| `--theme-top-n` | 3 | 进入精细分析的候选龙头数量 |
| `--theme-count` | 5 | 输出主题数量 |
| `--theme-lookback-days` | 7 | 新闻与主题回看天数 |
| `--theme-no-llm-detail` | false | 只输出主题和规则层候选，不跑 Top 个股精细 LLM |
| `--theme-include-concepts` | true | 是否包含概念板块 |

### 11.2 配置项

建议后续加入配置：

```yaml
theme_radar:
  enabled: false
  theme_count: 5
  leader_top_n: 3
  lookback_days: 7
  min_theme_score: 65
  min_leader_score: 60
  include_concepts: true
  save_history: true
```

## 12. 测试与验收计划

### 12.1 单元测试

未来实现代码时建议覆盖：

- LLM JSON 解析失败时的降级处理。
- 无证据主题过滤。
- 主题与板块映射。
- 主题评分计算。
- 龙头候选评分。
- 风险扣分和官方风险阻断。
- Markdown 报告格式。

建议测试文件：

- `test_theme_radar.py`
- `test_capital_flow.py`
- `test_theme_prompt_parser.py`

### 12.2 集成测试

建议覆盖：

1. 无 LLM / 无搜索 API Key 时，仍能基于热门板块输出规则层雷达。
2. 搜索可用时，能生成主题 JSON 并映射板块。
3. 主题雷达 Top N 能复用 `StockScreener`。
4. 精细分析开启时，Top 个股能复用 `analyze_stock()`。
5. 官方风险命中时，候选龙头被降权或标记风险。

### 12.3 人工验收

人工抽查重点：

- 主题是否都能追溯到新闻/资金证据。
- LLM 是否臆造了不存在的政策或公司关系。
- 关联板块是否合理。
- 候选龙头是否真的强于板块和大盘。
- 高热度主题是否同时具备新闻和资金验证。
- 被过滤股票的过滤原因是否可解释。

## 13. 推荐落地顺序

1. 完成本文档，明确边界和开发目标。
2. 新增 `ThemeRadarResult`、`ThemeSignal` 等数据结构。
3. 新增 `ThemeRadar`，先串联市场环境、热门板块和搜索结果。
4. 增加主题发现 prompt 和 JSON 解析。
5. 复用 `StockScreener` 输出候选龙头。
6. 接入 `analyze_stock()` 输出 Top N 精细报告。
7. 保存历史主题结果，增加连续性和退潮信号。
8. 增强资金数据源。
9. 回测主题与龙头评分有效性。

## 14. 与现有策略文档的关系

`docs/strategy_logic_and_optimization.md` 记录的是当前策略体系、已完成能力和后续优化路线。本文档聚焦下一阶段“热点主题发现 + 龙头筛选 + 精细分析”的产品与技术设计。

二者关系：

- 原策略文档是底层交易纪律和规则层依据。
- 本文档是新增主题雷达能力的开发蓝图。
- 实现时应保持“规则层约束，LLM 解释归纳”的原则一致。
- 热点雷达只扩展候选来源，不改变现有买点、仓位和风控纪律。
