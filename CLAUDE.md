# TradingAgents-Astock

## 项目概述
基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)（65K Stars）的 A 股深度特化 fork。多 Agent 投研框架，7 个 Analyst 角色通过 Bull/Bear 辩论 + 三方风险辩论生成投资报告。

- **仓库**: https://github.com/joycoding2000/TradingAgents-astock
- **协议**: Apache 2.0
- **Python**: >=3.10
- **当前版本**: 0.2.25

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
`a_stock.py` 里所有指向 `eastmoney.com` 的请求（push2 / push2his / datacenter-web / search-api / np-weblist 共 7 个调用点）统一走节流入口 `_em_get()`：模块级时间戳串行限流（默认间隔 `EM_MIN_INTERVAL=1.0s`，可用同名环境变量覆盖）+ 0.1~0.5s 随机抖动 + 复用 `requests.Session`（Keep-Alive）+ 默认 UA。多 Agent 跑批量分析不再触发东财临时封 IP。**仅东财限流**——mootdx(TCP) / 腾讯 / 新浪 / 同花顺 / 财联社 / 百度 等非东财源不受影响。批量场景可设 `EM_MIN_INTERVAL=1.5~2` 进一步降速。⚠️ **铁律**：新增东财端点**必须**走 `_em_get()`，**禁止**裸调 `_requests.get()`——v0.2.22 发现 3 处 emweb F10 违规（`ShareholderResearch`/`CompanyManagement`/`CoreConception` 裸调）累积并发导致阿里云 IP 被东财封禁，已修复。验证：`grep -B3 '_requests\.get' a_stock.py | grep eastmoney` 应无输出。

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

## 开发铁律与已知陷阱

### 🔴 铁律（违反必导致功能崩坏）

**1. 所有 `load_dotenv()` 必须设 `override=True`**
`load_dotenv()` 默认 `override=False`，不覆盖已存在环境变量。容器/系统已设同名变量时 `.env` 值被静默忽略。`web/app.py` 已设；新调用点必须同样设。改 `.env` 后必须 `update-server.sh --env`（`restart` 不重读）。

**2. 禁止引入 pyfpdf（与 fpdf2 名称冲突）**
`pyfpdf`（废弃 1.x）和 `fpdf2`（当前 2.x）都以 `fpdf` 名称导入——共存时谁后装谁生效，致中文 PDF 崩溃 `UnicodeEncodeError: latin-1`。`pip list | grep fpdf` 应只有 `fpdf2>=2.8.6`。

**3. 可选依赖导入必须在函数级守卫，不能模块级**
`from fpdf import FPDF` 在模块顶层，一旦 fpdf 损坏 → `web/app.py` import 链崩溃，整个应用起不来。所有非关键依赖的导入须用 try/except 在函数内守卫，失败只降级该功能不拖垮全应用（v0.2.17 #72）。

**4. 所有 `open()` 必须显式 `encoding="utf-8"`**
经历两轮修复（v0.2.2 `PYTHONUTF8` 无效 → v0.2.4 每处显式传）。Windows cp1252 默认致 `UnicodeEncodeError`。任何新文件 I/O 必须遵守，不得依赖进程级/环境变量设置。

**5. 东财 `eastmoney.com` 请求必须走 `_em_get()`**
裸调 `_requests.get()` 不走限流/代理，多 Agent 并发触发东财临时封 IP。违规致 v0.2.22 阿里云被封。详见 memory `em-all-via-em-get`，验证命令见该 memory。

**6. 数据源 try/except 不得静默吞错**
`a_stock.py` 大量 `try/except` 只写 `logger.warning` 不上抛，调用方无法区分"拿到数据"与"静默失败返回空"。issues/006 三个 bug 共享此根因。新增数据源端点必须：① 明确返回值语义（空 vs 失败）；② 关键接口失败需上抛或返回哨兵值让调用方感知。

### 🟠 提示词与工具

**7. 提示词中的函数描述参数名必须与实现完全一致**
LLM 工具误用的首要根因是提示词描述错。v0.2.18 5 个分析师写 `get_news(query, ...)` 实为 `ticker` → 模型传概念词当股票代码。新增/修改工具时参数名必须与实现精确一致，提示词预防 > 工具层容错。

**7. 提示词不得将无 API 接口的数据项列为"必采"**
`fundamentals_analyst.py` 曾要求股权质押/减持/关联交易但系统全无接口（已改"系统未采集"）。标记为"必采"的数据项必须有对应的工具/接口。正常空结果（"龙虎榜未上榜"）不标 `[数据缺失]`。

**8. 工具输入验证必须返回可恢复 ToolMessage，不能抛异常**
LangGraph 依赖 ToolMessage 自我纠正。抛异常中断整个 graph。`resolve_ticker` 报错从"找不到"改为"ticker 只接受 6 位代码或完整名称，行业/概念/板块名无效"→ LLM 读到后可自我纠正（v0.2.17 #76）。

**9. 改 prompt 必须用真实 A 股案例验证**
LLM 行为不可预测——prompt 看似正确但输出可能意外。改 prompt 后必须在实际分析中跑一次（任一股票），验证 LLM 行为与预期一致（DEV_LOG 协作约定）。

### 🏗 架构约束

**新增分析师必须改 6 个文件，漏一个 graph 断**
文件清单：① analyst body（`tradingagents/agents/analysts/xxx.py`）② `agent_states.py`（加字段）③ `agents/__init__.py`（注册）④ `graph/conditional_logic.py`（路由）⑤ `graph/trading_graph.py`（ToolNode）⑥ `graph/setup.py`（节点注册）。缺任一个 LangGraph 静默跳过该 analyst、无报错（DEV_LOG Week 2）。

**新分析师报告不自动流入下游，需手动补 5 个 agent**
Bull/Bear Researcher 和 3 个 Risk Debater 只消费原版 4 报告字段。新增的 `policy_report`/`hot_money_report`/`lockup_report` 需在 5 个下游 prompt 里手工加 `state.get("xxx_report", "")`。不加则新分析师产出在辩论层被静默忽略（CHANGES_FROM_UPSTREAM）。

### 🟠 Web UI

**10. Streamlit CSS 禁止 `display:none` `stHeader`/`stToolbar`**
侧边栏展开按钮嵌在工具栏内部。隐藏整个顶栏致展开按钮也消失——侧边栏收起后再也调不出来（刷新/重启无效）。只能透明化顶栏、精准隐藏内部元素（v0.2.8 #36）。

**11. Docker 运行镜像必须安装中文字体**
`python:3.12-slim` 无中文字体 → PDF 导出崩溃。Dockerfile 运行阶段须 `apt-get install fonts-noto-cjk`（v0.2.12 #48）。

### 🟡 已知限制（勿重复排查）

**12. MiniMax thinking mode + structured-output 冲突**
Research Manager/Trader/PM 报 `400 - Thinking mode does not support this tool_choice`。代码已降级为 free-text 重试，功能可用但日志有噪音。切其他模型（如 DeepSeek）可消除。

### 🟡 数据层约束

**13. 历史日分析必须用历史收盘价，不能用实时价**
`_resolve_price`：`curr_date` < 今日时取该日 K 线收盘价（mootdx+新浪 fallback）。实时价与历史价偏差可达几十元（300308: 1169 vs 1184）。新增价格相关数据接入点必须检查此规则。

**14. mootdx BESTIP 空串 → 三级 fallback**
mootdx 0.11.x `BESTIP.HQ` 可能空串致客户端崩溃。禁止依赖 bestip 自动探测，必须用 `_get_mootdx_client()`（三级：bestip 测速 → 裸 factory → 明确报错）。

**15. 数据层改动后必须重跑质量回归**
`test_data_quality.py` 是 v0.2.5 前的一次性快照，v0.2.5 移除 akshare 重写后从未复跑，5 个 bug 潜伏 2 个月才暴露（issues/008）。改动数据源、升级依赖、新增接口后必须跑全量数据层测试验证——"跑通一次"不代表"现在还通"。

**16. 一个源端点下线 → 扫该源所有端点**
v0.2.7 百度 PAE `fundflow`/`fundsortlist` 下线，只修了 `get_fund_flow`。同源的概念板块 `getrelatedblock` 仍用旧端点，2 个月后才在 v0.2.20 发现（issues/007）。任何 vendor 端点不可用时，必须 grep 全项目该 vendor 域名的所有调用点一并评估。

## 相关项目
- [a-stock-data](https://github.com/simonlin1212/a-stock-data) — A 股 MCP 数据服务（Claude Code 用的 skill）
- 上游 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) — 原版框架
