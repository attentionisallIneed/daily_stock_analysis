# 热点主题雷达核验问题修复开发文档

> 本文档基于当前 `ThemeRadar` 实现的核验结果，沉淀已发现的问题、修复方案、优先级和验收标准。项目输出仅用于投资研究和复盘辅助，不构成投资建议或自动交易指令。

## 1. 背景

热点主题雷达已经完成首轮开发，并具备以下能力：

- 通过 `ThemeRadar` 串联市场环境、热门板块、新闻证据、LLM 主题发现、资金观察、候选龙头筛选、精细分析和历史保存。
- 通过 `theme_models.py` 定义 `ThemeEvidence`、`ThemeSignal`、`LeaderCandidate`、`ThemeRadarResult`。
- 通过 `prompts/theme_discovery.py` 构造主题发现 prompt，并解析严格 JSON。
- 通过 `capital_flow.py` 对当前可用资金字段做统一归一。
- 通过 `theme_tracker.py` 跟踪主题状态。
- 通过 `theme_backtester.py` 提供最小回测框架。
- `main.py` 已新增 `--theme-radar`、`--theme-no-llm-detail`、`--theme-backtest` 等 CLI 入口。

核验结果显示：测试能通过，CLI 冒烟能生成报告，但报告可信度约束还不够严格，尤其在板块数据缺失、主题无法映射板块、资金验证不足时，仍可能输出过高分数或过高置信度。

本次优化目标：让热点主题雷达报告的分数、置信度、状态和数据可用性保持一致，避免“高分但无板块验证”“高置信度但关联板块待确认”等矛盾输出。

## 2. 当前验证结论

已执行验证：

```bash
.venv/Scripts/python.exe -m pytest test_theme_radar.py test_theme_prompt_parser.py test_theme_tracker.py test_theme_backtester.py
.venv/Scripts/python.exe main.py --theme-radar --theme-no-llm-detail --dry-run --no-notify
```

结果：

- 主题相关单元测试全部通过。
- CLI 冒烟运行成功，生成 `reports/theme_radar_YYYYMMDD.md` 和 `data/theme_radar/theme_radar_YYYY-MM-DD.json`。
- 当 AkShare 板块接口失败时，系统仍能基于新闻生成主题报告，但候选龙头为空。

这说明主流程可用，但降级策略需要更严格。

## 3. 问题清单与修复优先级

| 优先级 | 问题 | 影响 | 推荐修复位置 |
| --- | --- | --- | --- |
| P0 | 主题分数超过 100 | 报告热度分失真，难以比较 | `theme_models.py`、`theme_radar.py` |
| P0 | 板块映射失败仍可高置信度 | 主题可信度与证据不一致 | `theme_radar.py` |
| P0 | 板块/资金数据缺失时仍输出强主题状态 | 容易把新闻观察误判为市场确认热点 | `theme_radar.py`、`theme_tracker.py` |
| P1 | 市场主题搜索复用股票搜索模板 | Query 被“股票 最新消息”污染 | `search_service.py`、`theme_radar.py` |
| P1 | `--theme-include-concepts` 无法关闭 | CLI 参数语义错误 | `main.py` |
| P1 | `ThemeRadar.analyzer` 语义混淆 | 后续维护容易误传对象 | `theme_radar.py`、`main.py` |
| P2 | 回测只读取已有 forward returns | 不是真正自动行情回测 | `theme_backtester.py` |

## 4. P0 修复方案

### 4.1 主题分数统一与封顶

#### 问题

当前报告中可能出现超过 100 的热度分，例如 `125.5`。原因是：

- `ThemeSignal.total_score` 累加 `news_score + capital_score + market_score + persistence_score`，没有限制上限。
- `ThemeSignal.heat_score` 与 `total_score` 语义重复，但报告使用的是 `total_score`。

#### 修复目标

所有主题对外展示分数必须稳定在 `0-100` 区间。

#### 推荐方案

统一采用以下定义：

```text
total_score = clamp(heat_score, 0, 100)
```

并在构建 `ThemeSignal` 时明确：

```text
heat_score = news_score + capital_score + market_score + persistence_score + leader_quality_bonus - risk_penalty
```

若短期不引入 `leader_quality_bonus` 和 `risk_penalty`，则先保持：

```text
heat_score = news_score + capital_score + market_score + persistence_score
```

但必须封顶：

```python
heat_score = max(0.0, min(100.0, heat_score))
```

#### 建议修改

在 `theme_models.py` 中：

- 保留 `heat_score` 作为主题总热度分。
- 修改 `total_score`：优先返回 `heat_score`，并 clamp 到 0-100。

示例：

```python
@property
def total_score(self) -> float:
    return round(max(0.0, min(100.0, float(self.heat_score or 0.0))), 2)
```

在 `theme_radar.py` 中：

- `_build_theme_signals()` 计算 `heat_score` 后也 clamp。
- 报告中的“热度分”继续用 `theme.total_score`。

#### 验收标准

- 报告中所有主题热度分不超过 100。
- `ThemeSignal.to_dict()` 中 `total_score` 不超过 100。
- 新增测试覆盖：输入各项分数合计超过 100 时，最终 `total_score == 100`。

### 4.2 板块映射失败降级

#### 问题

LLM 可能输出新闻主题，但 `related_sectors` 无法匹配当前热门板块。当前实现只追加风险“主题与现有板块映射待确认”，但仍可能保留“高”置信度。

#### 修复目标

没有板块映射的主题不得标记为高置信度，也不得进入高热度强验证分层。

#### 推荐规则

当 `requested_sectors` 非空但 `related_sectors` 为空时：

```text
confidence = min(confidence, 中)
status = 待确认
heat_score <= 64
capital_score = min(capital_score, 6)
market_score = min(market_score, 6)
追加风险：主题与现有板块映射待确认
追加降级原因：缺少可验证板块映射
```

当 `requested_sectors` 本身为空时：

```text
confidence = min(confidence, 中)
status = 待确认
heat_score <= 59
追加风险：LLM 未提供可验证关联板块
```

#### 建议修改

在 `ThemeRadar._build_theme_signals()` 中增加统一降级函数，例如：

```python
def _apply_theme_validation_rules(self, raw, related_sectors, sectors_available):
    ...
```

或者在构建 `ThemeSignal` 前直接处理：

```python
confidence = str(raw.get("confidence") or "中")
downgrade_reasons = []

if not related_sectors:
    confidence = self._cap_confidence(confidence, "中")
    risks.append("主题与现有板块映射待确认")
    downgrade_reasons.append("缺少可验证板块映射")
    capital_score = min(capital_score, 6.0)
    market_score = min(market_score, 6.0)
```

#### 验收标准

- 当 LLM 输出的 `related_sectors` 全部不在热门板块列表中时，主题置信度最高为“中”。
- 该主题状态为“待确认”。
- 报告风险点中包含映射失败原因。
- 新增测试覆盖高置信度主题映射失败后的自动降级。

### 4.3 板块/资金数据缺失时的报告降级

#### 问题

当板块接口失败时，系统仍能基于新闻生成主题，但这类主题缺少行情和资金验证。当前报告仍可能输出“新发酵”状态和较高热度。

#### 修复目标

区分“新闻主题观察”和“市场验证热点”。无板块/资金数据时，不应输出强验证结论。

#### 推荐规则

当 `sectors` 为空：

```text
全局 data_quality.sector_data_available = false
所有主题：
  status = 待确认
  confidence 最高为 中
  capital_score = 0 或中性低分
  market_score = 0 或中性低分
  heat_score 上限 59
报告市场环境区增加提示：板块行情获取失败，本报告仅为新闻主题观察
候选龙头排序为空时，明确说明：未生成候选龙头，因为缺少板块成分股/行情验证
```

当 `capital_map` 为空但 `sectors` 不为空：

```text
资金验证缺失，主题可以输出，但 confidence 最高为 中
capital_observation = 资金数据缺失，按中性偏保守处理
capital_score <= 8
```

#### 建议修改

在 `ThemeRadar.run()` 中生成数据质量上下文：

```python
data_quality = {
    "sector_data_available": bool(sectors),
    "capital_data_available": bool(capital_map),
    "news_data_available": bool(evidence),
}
```

可将其加入 `ThemeRadarResult`，或者先加入 `market_environment["data_quality"]`。

在 `format_report()` 的市场环境区展示：

```markdown
- 数据质量：板块行情缺失 / 资金数据缺失 / 新闻证据可用
- 降级说明：板块行情获取失败，本报告仅作为新闻主题观察
```

#### 验收标准

- 模拟 `get_hot_sectors()` 返回空列表时，报告不出现高置信度主题。
- 报告明确提示板块数据缺失。
- 候选龙头为空时，有明确原因说明。
- 新增测试覆盖无板块数据降级路径。

## 5. P1 修复方案

### 5.1 增加通用市场主题搜索接口

#### 问题

当前主题雷达调用：

```python
search_service.search_stock_news("market", "A股热点板块 近7日 政策 产业 资金", max_results=5)
```

但 `search_stock_news()` 会按股票新闻模板拼接 query，导致主题搜索被追加“股票 最新消息”等无关词。

#### 修复目标

主题雷达应使用专门的市场/主题搜索接口，不复用股票搜索模板。

#### 建议新增接口

在 `search_service.py` 增加：

```python
def search_market_news(self, query: str, max_results: int = 5) -> SearchResponse:
    """搜索市场热点、政策、产业和资金主题新闻。"""
    for provider in self._providers:
        if not provider.is_available:
            continue
        response = provider.search(query, max_results)
        if response.success and response.results:
            return response
    return SearchResponse(...)
```

在 `theme_radar.py` 中改为：

```python
if hasattr(self.search_service, "search_market_news"):
    response = self.search_service.search_market_news(query, max_results=5)
else:
    response = self.search_service.search_stock_news("market", query, max_results=5)
```

保留 fallback 是为了兼容测试 fake 对象。

#### 验收标准

- CLI 日志中的 query 不再出现无关的 `market 股票 最新消息`。
- `search_stock_news()` 原有个股分析行为不变。
- 新增测试覆盖 `ThemeRadar` 优先调用 `search_market_news()`。

### 5.2 修正概念板块 CLI 参数

#### 问题

当前参数：

```python
parser.add_argument(
    '--theme-include-concepts',
    action='store_true',
    default=True,
)
```

由于默认值已经是 True，`store_true` 无法关闭概念板块。

#### 推荐方案

保留默认包含概念板块，新增关闭参数：

```python
parser.add_argument(
    '--theme-no-concepts',
    action='store_true',
    help='热点主题雷达不包含概念板块'
)
```

调用处改为：

```python
include_concepts=not args.theme_no_concepts
```

可保留 `--theme-include-concepts` 作为兼容参数，但帮助文案应说明“已默认启用”。

#### 验收标准

- 默认运行包含概念板块。
- 加 `--theme-no-concepts` 后 `include_concepts=False`。
- 参数帮助文本不矛盾。

### 5.3 拆分 `llm_analyzer` 与 `detail_analyzer`

#### 问题

`ThemeRadar.__init__()` 中的 `analyzer` 同时可能被理解为：

- 用于主题发现的 LLM 调用器。
- 有 `analyze_stock()` 的精细分析器。

当前主流程通过 `detail_analyzer` 避免了实际错误，但命名仍容易误导。

#### 推荐方案

将构造参数调整为：

```python
def __init__(
    ...,
    llm_analyzer: Any = None,
    detail_analyzer: Optional[Callable[[str], Any]] = None,
    ...,
):
    self.llm_analyzer = llm_analyzer
    self.detail_analyzer = detail_analyzer
```

兼容旧参数可短期保留：

```python
if llm_analyzer is None and analyzer is not None:
    llm_analyzer = analyzer
```

后续 `_discover_theme_dicts()` 使用 `self.llm_analyzer`，`analyze_stock()` 只使用 `self.detail_analyzer`。

#### 验收标准

- `ThemeRadar` 内部 LLM 调用和精细分析调用职责清晰。
- `main.py` 传参改为 `llm_analyzer=self.analyzer`。
- 现有测试不需要大改，或者只更新参数名。

## 6. P2 增强方案

### 6.1 回测自动补算 forward returns

#### 当前状态

`ThemeBacktester` 当前只读取历史 JSON 中已有的：

- `sector_forward_returns`
- `leader_forward_returns`
- `forward_returns`

如果历史记录没有这些字段，回测收益默认为 0。

#### 推荐增强

新增行情补算能力：

```python
class ThemeBacktester:
    def __init__(self, sector_fetcher=None, daily_fetcher=None, horizons=DEFAULT_HORIZONS):
        ...
```

计算逻辑：

1. 对主题：优先取第一个 `related_sectors`，使用 `get_sector_daily_data()` 获取板块日线。
2. 对龙头：使用 `daily_fetcher.get_daily_data(code)` 获取个股日线。
3. 根据 `generated_at` 对齐交易日，计算 1/3/5/10 日 forward return。
4. 如果行情不可用，保留原有读取字段逻辑。

#### 验收标准

- 历史 JSON 没有 forward returns 时，也能在有行情数据的情况下生成非零回测结果。
- 行情不可用时不报错，报告明确样本数据不足。
- 回测报告区分“真实行情补算”和“历史字段读取”。

## 7. 推荐实施顺序

1. 修复主题分数封顶和 `total_score` 语义。
2. 增加板块映射失败降级规则。
3. 增加无板块/无资金数据的全局降级和报告提示。
4. 新增 `search_market_news()` 并让主题雷达优先使用。
5. 修正 `--theme-no-concepts` CLI。
6. 拆分 `llm_analyzer` 与 `detail_analyzer` 命名。
7. 增强回测自动补算 forward returns。

其中 1-3 属于 P0，应优先完成；否则报告可能继续输出“高分但无验证”的结果。

## 8. 测试计划

### 8.1 单元测试新增建议

新增或扩展 `test_theme_radar.py`：

1. `test_theme_score_is_capped_at_100`
   - 构造分数合计超过 100 的主题。
   - 断言 `total_score == 100`。

2. `test_unmapped_high_confidence_theme_is_downgraded`
   - LLM 输出 `confidence=高`，但 `related_sectors` 不在热门板块中。
   - 断言置信度降为“中”，状态为“待确认”，风险包含映射失败。

3. `test_no_sector_data_marks_report_as_news_observation`
   - `get_hot_sectors()` 返回空。
   - 断言报告包含“板块行情获取失败”或等价提示。
   - 断言无高置信度主题。

4. `test_theme_radar_uses_market_news_search_when_available`
   - fake `SearchService` 同时提供 `search_market_news()` 和 `search_stock_news()`。
   - 断言优先调用 `search_market_news()`。

5. `test_theme_no_concepts_cli_argument`
   - 可通过解析参数或较小集成测试验证 `--theme-no-concepts` 生效。

### 8.2 回归测试

继续执行：

```bash
.venv/Scripts/python.exe -m pytest test_theme_radar.py test_theme_prompt_parser.py test_theme_tracker.py test_theme_backtester.py
```

如果改动 `search_service.py` 和 `main.py`，建议额外跑：

```bash
.venv/Scripts/python.exe -m pytest test_stock_screener.py test_backtester.py test_analyzer_hard_rules.py
```

### 8.3 CLI 验证

建议执行：

```bash
.venv/Scripts/python.exe main.py --theme-radar --theme-no-llm-detail --dry-run --no-notify
.venv/Scripts/python.exe main.py --theme-radar --theme-no-concepts --theme-no-llm-detail --dry-run --no-notify
.venv/Scripts/python.exe main.py --theme-backtest --no-notify
```

人工检查：

- 热度分是否全部在 0-100。
- 无板块映射主题是否被降级。
- 板块数据缺失时是否明确提示“仅新闻观察”。
- Query 日志是否不再出现股票模板污染。
- 候选龙头为空时是否给出原因，而不是留下空表。

## 9. 验收标准

完成本轮优化后，应满足：

1. 报告不存在超过 100 的主题热度分。
2. 没有可验证板块映射的主题不能是高置信度。
3. 板块行情缺失时，报告明确降级为新闻主题观察。
4. 资金数据缺失时，主题不能被描述为“新闻与资金共振”。
5. 主题搜索使用市场/主题搜索接口，不复用股票搜索模板。
6. CLI 可以关闭概念板块。
7. `ThemeRadar` 构造参数职责清晰。
8. 所有主题相关测试通过。
9. CLI 冒烟能生成报告，且报告中的分数、置信度、状态、候选龙头数量相互一致。

## 10. 后续注意事项

- 不要为了让报告“看起来丰富”而在板块数据缺失时输出强结论。
- LLM 主题发现只负责归纳证据，不负责确认行情强度。
- 主题置信度必须同时参考新闻证据、板块映射、资金验证和市场环境。
- 任何高置信度主题都应能回答三个问题：为什么热、哪个板块验证、哪个龙头承接。
- 如果只能回答“为什么热”，但不能回答“哪个板块验证”和“哪个龙头承接”，就应是观察主题而不是交易候选主题。
