# TradingAgents-Astock

## 项目概述
基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)（65K Stars）的 A 股深度特化 fork。多 Agent 投研框架，7 个 Analyst 角色通过 Bull/Bear 辩论 + 三方风险辩论生成投资报告。

- **仓库**: https://github.com/simonlin1212/TradingAgents-astock
- **协议**: Apache 2.0
- **Python**: >=3.10
- **当前版本**: 0.2.22

## 架构

### 数据层（v0.2.5 全部直连 HTTP，零第三方数据库依赖）
| 来源 | 协议 | 数据 |
|------|------|------|
| mootdx | TCP 7709 | OHLCV K线、财务快照、F10 文本 |
| 腾讯财经 | HTTP (qt.gtimg.cn) | PE/PB/市值/换手率 |
| 东方财富 datacenter | HTTP (datacenter-web) | 龙虎榜、限售解禁、板块行情 |
| 东方财富 push2/push2his | HTTP (push2.eastmoney) | 实时行情、个股信息、板块列表、资金流(分钟+日级) |
| 东方财富 np-weblist | HTTP | 滚动新闻 |
| 新浪财经 | HTTP (money.finance.sina) | K线历史、财报三表 |
| 同花顺 10jqka | HTTP | EPS 一致预期、热股题材 |
| 财联社 cls.cn | HTTP | 全球财经快讯 |
| 百度股市通 | HTTP (gushitong.baidu) | 概念板块归属（资金流已迁移至东财push2） |

### Agent 角色（7 个）
原版 4 个（市场/情绪/新闻/基本面）+ A 股特化 3 个（政策分析师/游资追踪/解禁监控）

### 关键路径
- `tradingagents/dataflows/a_stock.py` — A 股数据 vendor，所有数据获取入口
- `tradingagents/dataflows/utils.py` — `safe_ticker_component` 路径安全校验 + 中文 ticker 自动解析
- `tradingagents/agents/` — 7 个 Analyst + Bull/Bear 辩论逻辑
- `web/` — Streamlit Web UI
- `cli/` — CLI 入口

### 中文股票名解析链路
用户/LLM 输入 → `safe_ticker_component` 检测中文 → `resolve_ticker()` → `_build_name_code_map()`（mootdx 全市场映射，缓存）→ 返回 6 位代码

## 已知问题与注意事项

### 依赖冲突（v0.2.6 已缓解）
mootdx 锁死 httpx==0.25.2，与 langchain-google-genai 的 httpx>=0.28.1 冲突。v0.2.6 将 google-genai 移至可选依赖 `[google]`，`pip install -e .` 不再冲突。需要 Google 模型时 `pip install -e ".[google]"`。

### akshare 已移除（v0.2.5）
v0.2.5 起完全移除 akshare 依赖，所有数据通过直连 HTTP API 获取。

### 百度 PAE 资金流接口已下线（v0.2.7 已修复）
`fundsortlist` 和 `fundflow` 两个接口返回空（2026-05-19 确认）。v0.2.7 已替换为东财 push2 资金流 API。同时修复了 `RPT_ORGANIZATION_BUSSINESS`（改用席位筛选机构）和东财全球资讯 `req_trace` 参数。

### 东财接口防封限流（v0.2.11 新增，移植自 a-stock-data v3.2）
`a_stock.py` 里所有指向 `eastmoney.com` 的请求（push2 / push2his / datacenter-web / search-api / np-weblist 共 7 个调用点）统一走节流入口 `_em_get()`：模块级时间戳串行限流（默认间隔 `EM_MIN_INTERVAL=1.0s`，可用同名环境变量覆盖）+ 0.1~0.5s 随机抖动 + 复用 `requests.Session`（Keep-Alive）+ 默认 UA。多 Agent 跑批量分析不再触发东财临时封 IP。**仅东财限流**——mootdx(TCP) / 腾讯 / 新浪 / 同花顺 / 财联社 / 百度 等非东财源不受影响。批量场景可设 `EM_MIN_INTERVAL=1.5~2` 进一步降速。新增东财端点时务必走 `_em_get` 而非裸 `requests.get`。

### 关键财务数据缺失（v0.2.19 已修复）
`get_fundamentals` / 三表 / `get_profit_forecast` 曾因三个 bug 静默丢数据（各源 try/except 吞错只留 warning）：(1) mootdx `client.finance()` 字段为拼音缩写（`jinglirun`/`zhuyingshouru`/`meigujingzichan`...），旧 `field_map` 用 `eps`/`roe` 英文名取不到，已改拼音字段并推算 `EPS=jinglirun/zongguben`、`ROE=jinglirun/jingzichan*100`；(2) 新浪财报实际结构为 `result.data.report_list[日期]["data"]`，旧代码误用 `result.data.lrb` key 致三表恒空，已重写解析；(3) pandas 3.0 `read_html` 不再接受裸 HTML 字符串（当文件路径 open），同花顺 EPS 崩溃，已改 `pd.read_html(io.StringIO(r.text))`。回归测试见 `tests/test_astock_fundamentals_fix.py`，详见 `issues/006-fundamentals-data-missing.md`。主力资金 `get_fund_flow`（东财 push2）接口本身可用，无需改动。

### 概念板块/股东数据接口迁移（v0.2.20 已修复）
`get_concept_blocks`（百度 PAE `getrelatedblock` 返回 403 下线）迁移至东财 F10 `CoreConception/PageAjax`（ssbk 所属板块 + hxtc 核心题材）；`get_insider_transactions`（mootdx F10 仅返回"最新提示"栏目，通达信 TCP F10 无股东研究）迁移至东财 `RPT_F10_EH_HOLDERS`（按 END_DATE 降序取最新一期十大股东持股变化）。注意：东财 ssbk 不含板块当日涨幅（百度 PAE 原有），仅返回板块归属。`get_industry_comparison`（东财 push2 clist）代码无 bug，偶发缺失是东财连接/LLM 未调用，无需改代码。回归测试见 `tests/test_astock_interface_fix.py`，详见 `issues/007-interface-migration.md`。

### 门控矛盾 + push2 IDC 封禁 + prompt 假缺失（v0.2.22 已修复）
服务器跑 601689 门控暴露"基本面硬检查 [C] 3 处缺失 vs LLM 复审判 A"矛盾。三层修复：(1) `quality_gate.py` 硬检查不再因 `[数据缺失]` 数量 ≥3 机械判 C（改判 B，关键性交 LLM 判断）；`_build_review_prompt` 把硬检查结果喂给 LLM 复审，评级标准明确"非必采项缺失不影响 A 级"+ 要求与硬检查不一致需说明；消除两层矛盾。(2) `fundamentals_analyst.py` 股权质押/减持计划预披露/关联交易（系统无接口）从硬要求改为"系统未采集"说明，消除 3 处设计性缺失；`hot_money_tracker.py` 加标注规范，龙虎榜未上榜等正常空结果不标 `[数据缺失]`。(3) `a_stock.py` `_EM_SESSION` 读 `EM_HTTP_PROXY` 环境变量设代理——东财 push2.eastmoney.com 整域名对阿里云 IDC IP 封禁（建连后 RemoteDisconnected），资金流 fflow/行业对比 clist 全失败，设代理走非 IDC 出口绕过；不设则直连（本地无影响）。`_em_get` 重试对 ProxyError 自动兜底。回归测试 `tests/test_astock_v0222_fix.py`（7 例），详见 `issues/009-push2-idc-block.md`。部署：服务器 `.env` 加 `EM_HTTP_PROXY`，`update-server.sh --env`。

### 数据质量三修复 + Week5 过时快照勘误（v0.2.21 已修复）
v0.2.20 部署后门控暴露股价不一致/行业对比偶发/股东户数与董监高交易缺失。三项修复：(1) `get_fundamentals` 股价对齐——`curr_date` 早于今日时 price 改用该日 K 线收盘价（复用 `get_stock_data` 含新浪 fallback），消除与技术分析基准日的时差（实测 300308 由实时 1169.31 对齐到 07-14 收盘 1184.05）；新增私有 helper `_get_close_on_date`/`_resolve_price`。(2) `_em_get` 加偶发重试——连接异常（RemoteDisconnected/Timeout）或 5xx 时指数退避重试最多 3 次，4xx 不重试，缓解行业对比/资金流偶发失败。(3) `get_insider_transactions` 增强三段——十大股东（RPT_F10_EH_HOLDERS）+ 股东户数变化（F10 `ShareholderResearch/PageAjax` gdrs：HOLDER_TOTAL_NUM/变化比例/户均流通股/筹码集中度）+ 董监高持股变动（F10 `CompanyManagement/PageAjax` cgbd：高管/职务/变动股数/均价/变动方式）。另：DEV_LOG Week 5「14/14 OK」勘误为过时快照（akshare+旧mootdx+pandas2.x，v0.2.5 重写后未复跑），详见 `issues/008-week5-quality-gate-stale-snapshot.md`。回归测试见 `tests/test_astock_v0221_fix.py`（8 例）。

### 模型兼容性
deepseek-v4-flash 等模型在 tool call 时可能返回中文股票名而非 6 位代码。`safe_ticker_component` 已加兜底自动转码，但不同模型表现仍有差异。

### 待处理 PR
- PR #18（hejingchi）：start_date 功能 + 主题切换 + Windows 字体。不建议直接 merge（与 v0.2.6 冲突），start_date 功能值得后续自行实现。

## Issue 归档
所有 GitHub Issue 的详细记录在 `issues/` 文件夹中，包含问题描述、根因分析、修复方案和当前状态。

## 开发规范
- 改动前先跑 `python -m pytest tests/ -v` 确保不破坏现有测试
- `safe_ticker_component` 是安全边界，任何绕过路径校验的改动必须慎重评估
- 数据层新增接口遵循 `tradingagents/dataflows/interface.py` 的 vendor 路由模式
- Web UI 改动在 `web/` 目录，用 `streamlit run web/launch.py` 本地测试

## 相关项目
- [a-stock-data](https://github.com/simonlin1212/a-stock-data) — A 股 MCP 数据服务（Claude Code 用的 skill）
- 上游 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) — 原版框架
