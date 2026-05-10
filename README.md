# A股热点主题与自选股智能分析系统

本项目默认运行“热点主题/板块/龙头/精细分析”主链路，也保留自选股日报模式：抓取行情数据、计算技术指标、搜索新闻情报、调用 OpenAI 标准/兼容 LLM 生成分析报告，并通过企业微信、飞书、Telegram、邮件或自定义 Webhook 推送。

## 核心流程

默认主链路：

1. 获取大盘环境和热门行业/概念板块。
2. 汇总板块、新闻和资金证据，调用 LLM 做热点主题发现。
3. 对热门板块成分股做规则层筛选和候选龙头排序。
4. 对 Top N 候选龙头复用个股精细分析链路。
5. 保存主题雷达报告、主题历史，并按配置推送。

自选股日报模式：

1. 从 `.env` 读取股票列表、LLM、搜索、通知和数据源配置。
2. 按优先级抓取日线行情并写入 SQLite。
3. 计算均线、成交量、量比、筹码等分析指标。
4. 使用 Tavily 或 SerpAPI 搜索近期新闻。
5. 调用 OpenAI 标准/兼容接口生成个股分析和大盘复盘。
6. 按配置推送报告或写入飞书云文档。

## 策略文档

- [金融策略逻辑与优化路线](docs/strategy_logic_and_optimization.md)：沉淀当前趋势交易、风控过滤、LLM 决策仪表盘逻辑，以及后续回测、点位、盈亏比、仓位和数据源优化方向。

## 最小运行配置

复制 `.env.example` 为 `.env`，至少填写：

```env
STOCK_LIST=600519,300750,002594
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

第三方 OpenAI 兼容服务也可使用同一套变量，例如 DeepSeek、通义千问、Moonshot、智谱 GLM 等，只要提供标准 `/v1` Chat Completions 接口即可。

## Key 清单

### 必需

- `OPENAI_API_KEY`：OpenAI 或兼容服务 API Key。
- `OPENAI_BASE_URL`：OpenAI 标准 `/v1` 接口地址。
- `OPENAI_MODEL`：要调用的模型名。

### 推荐

- `STOCK_LIST`：自选股日报模式要分析的股票代码，逗号分隔。
- `TAVILY_API_KEYS`：新闻搜索主源，推荐配置。
- `TUSHARE_TOKEN`：A 股行情备用数据源，推荐配置。

### 可选

- `SERPAPI_API_KEYS`：新闻搜索备用源。
- `WECHAT_WEBHOOK_URL`：企业微信机器人推送。
- `FEISHU_WEBHOOK_URL`：飞书机器人推送。
- `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`：Telegram 推送。
- `EMAIL_SENDER`、`EMAIL_PASSWORD`、`EMAIL_RECEIVERS`：邮件推送。
- `CUSTOM_WEBHOOK_URLS`：钉钉、Slack、Discord、Bark 或自建 Webhook。
- `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_FOLDER_TOKEN`：飞书云文档写入。

## 推荐 A 股信息获取途径

- 行情、指数、板块：AkShare 作为主源，免费且覆盖面广。
- 稳定备用行情：Tushare，建议配置 token，后续也适合扩展财务、公告和基础资料。
- 免费兜底行情：Baostock。
- 最后兜底：yfinance，A 股数据可能延迟或不完整。
- 新闻情报：Tavily 主源，SerpAPI 备用。
- 后续增强：接入巨潮资讯/CNINFO，用于公告、减持、业绩预告、监管函等风险排查。

## 常用命令

```bash
# 查看配置、数据库等基础状态
python test_env.py

# 测试数据获取
python test_env.py --fetch

# 测试 OpenAI 兼容 LLM 调用
python test_env.py --llm

# 运行默认主链路：热点主题/板块/龙头/精细分析
python main.py

# 自选股日报，不发送通知
python main.py --watchlist --no-notify

# 仅分析指定股票，不发送通知
python main.py --stocks 600519 --no-notify --no-market-review

# dry-run 运行指定股票
python main.py --dry-run --stocks 600519 --no-notify

# 仅生成大盘复盘
python main.py --market-review

# 启动定时任务
python main.py --schedule
```

## 定时任务

`.env` 中可配置：

```env
SCHEDULE_ENABLED=false
SCHEDULE_TIME=18:00
MARKET_REVIEW_ENABLED=true
```

GitHub Actions 也可以通过仓库 Secrets 配置同名变量后定时运行。

## 数据与日志

- SQLite 数据库默认路径：`./data/stock_analysis.db`
- 日志目录默认路径：`./logs`
- 可通过 `.env` 中的 `DATABASE_PATH`、`LOG_DIR`、`LOG_LEVEL` 调整。
