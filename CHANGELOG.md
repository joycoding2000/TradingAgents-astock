# Changelog

## [0.2.29] - 2026-07-20

### 新增
- **全局 YAML 配置系统**：新增 `config.yaml.example` 模板，所有可调参数带中文注释说明。
  `tradingagents/dataflows/config.py` 新增三层优先级（环境变量 > config.yaml > 默认值）。
  支持 `TRADINGAGENTS_*` 环境变量覆盖，无需改代码即可调整辩论轮数、分析模式等参数。

### 改进
- **去除入口硬编码**：`web/app.py`、`cli/main.py`、`main.py` 统一走 `get_config()`，不再手动
  重构 `data_vendors`/`max_debate_rounds`/`checkpoint_enabled` 等硬编码值。
- **配置优先级文档化**：`config.yaml.example` 每项参数均附带取值范围、建议值和原理说明。

### 依赖
- 新增 `pyyaml>=6.0`。

## [0.2.28] - 2026-07-20

### 新增
- **可配置 Alpha 基准（reflection 层）**：`DEFAULT_CONFIG` 新增 `benchmark_ticker` 和 `benchmark_map`。
- **股票名称简拼输入**：Web 输入支持 6 位代码、中文名称和拼音首字母。新增 `pypinyin` 依赖。

### 改进
- **Web 键盘直输**：进入分析页后股票输入框自动获得焦点。
- **通俗中文结论**：结果页优先展示最终风控决策，英文标题和术语转成通俗中文。
- **市场分析师性能优化**：`get_stock_data` 新增 `indicators` 参数，`indicators="all"` 一次性返回 OHLCV + 常用技术指标。市场分析师从 10+ 次工具调用降至 1 次。
- **中文评级解析**：`parse_rating()` 新增中文评级映射（买入/增持/持有/减持/卖出），消除中文模式下抬头信号与正文评级矛盾。

### 修复
- **CLS 新闻端点下线**：财联社接口 `nodeapi/telegraphList` 返回 404，迁移至 `api/cache?name=telegraph`。
- **别名幻觉**：市场分析师 prompt 增加「禁止为股票编造别名/曾用名」约束。
- **政策分析师必采项松弛**：宏观/监管/地方政策 3 项从「必采」改为「尽力采集」。详见 `PLAN_v0.3.0_implementation.md`。
- **`@tool` 缺 `indicators` 参数**：`core_stock_tools.py` 补上参数，使性能优化真正生效。

### 移除
- 市场分析师工具列表中移除 `get_indicators`（已被 `get_stock_data(indicators="all")` 取代）。

投资研究员对 300131 报告审查

  整体评分：B+（80/100）

  ┌────────────┬───────┬────────────────────────────────────────┐
  │    维度    │ 评分  │                关键发现                │
  ├────────────┼───────┼────────────────────────────────────────┤
  │ 数据完整性 │ 18/20 │ 7 分析师覆盖完整，数据成功率 95%       │
  ├────────────┼───────┼────────────────────────────────────────┤
  │ 分析深度   │ 16/20 │ 技术/资金/基本面核心判断到位           │
  ├────────────┼───────┼────────────────────────────────────────┤
  │ 逻辑严密性 │ 15/20 │ 研究经理裁决逻辑严密，但有操作建议矛盾 │
  ├────────────┼───────┼────────────────────────────────────────┤
  │ 可操作性   │ 16/20 │ 有明确价格区间，但建议与前提矛盾       │
  ├────────────┼───────┼────────────────────────────────────────┤
  │ 风险覆盖   │ 15/20 │ 覆盖商誉/主力出货等核心风险，有遗漏    │
  └────────────┴───────┴────────────────────────────────────────┘

## [0.2.27] - 2026-07-18

### Added

- **全链路耗时台账**：记录图节点、每轮模型调用、每个数据工具和持久化步骤的起止时间、耗时及状态；结果 JSON 同步保存汇总、P50/P95、阶段耗时和缓存命中数，不记录提示词、工具正文、代理地址或异常详情。
- **单次分析请求复用**：相同工具及完整参数在同一分析内只请求一次，成功和正常空结果可复用；失败及输入无效不缓存。缓存命中继续进入数据台账并明确标记，不跨股票、日期或运行复用实时数据。
- **快速分析模式**：Web 可选择完整分析或快速分析。快速模式保留技术、新闻、基本面及完整质量门控/决策链，并在网页、历史记录、Markdown、PDF 和下游证据约束中明确标识覆盖范围较少。

### Changed

- **七位分析师并行采集**：七条分支使用独立消息通道并行运行，全部汇合后才进入质量门控；工具台账和性能台账使用状态归并器合并，东财 `_em_get()` 的串行限流、动态代理、重试与数据缺失语义保持不变。
- **通俗耗时展示**：结果页可查看各阶段耗时、模型调用次数及本次复用数据次数，并说明并行阶段耗时不能直接相加。

## [0.2.26] - 2026-07-18

### Changed

- **数据门控改为分领域降级**：只有基础行情失败、两个及以上主要研究领域完全不可用、或完全没有工具台账时才判“低”。资金流向、行业对比等分项接口失败时判“中”，其余成功数据继续参与综合分析。
- **缺什么就不能判断什么**：台账为每个失败工具生成确定性的结论边界。例如资金流缺失时禁止判断主力抢筹/出逃，行业对比缺失时禁止判断行业强弱/排名/板块轮动；禁止用新闻或市场常识冒充直接数据。
- **约束贯穿全部决策节点**：结论边界传入多空研究、研究经理、交易员、三方风险分析和最终组合经理，并持久化到结果 JSON。中可信度报告在网页、Markdown 和 PDF 中继续展示综合结论，同时明确列出不能判断的内容。
- **版本展示不再滞后**：Web 侧边栏从统一版本常量读取当前版本，并由测试校验其与项目发布版本一致，避免升级后仍显示旧版本号。

## [0.2.25] - 2026-07-18

### Fixed

- **数据不完整时不再给交易指令**：关键数据工具最终失败时，网页、Markdown 和 PDF 统一显示“数据不完整”，只展示数据状态；内部原始报告保留在日志中用于排查，但不会向用户展示买卖、价位或投入比例建议，也不会写入后续分析的经验记忆。
- **最终结论一致性**：历史报告只解析最终风控决策的五档评级，不再把研究阶段的 Hold 覆盖最终 Sell；网页标题支持“偏向买入/偏向卖出”。
- **东财关键数据可用性**：东财请求在整个请求/重试周期内串行限流；429、5xx 和关键列表为空均视为失败并进入台账，动态代理失败时最多受控轮换一次且关闭旧连接池，避免旧代理连接复用。
- **面向用户的中文输出**：工具台账的失败项不再泄露内部英文函数名；报告与导出中的固定英文数据标题和常见术语改为中文。

## [0.2.24] - 2026-07-18

### Fixed

- 数据台账按“工具名 + 参数摘要”区分请求：只有同一请求的重试成功才会覆盖之前失败；不同分析师的同名工具调用不再相互掩盖，任何关键请求最终失败都会限制结论可信度。
- Web 的数据质量页改用通俗中文数据名称，不再向用户展示内部工具英文标识。

## [0.2.23] - 2026-07-18

### Added

- 数据工具调用台账：记录每次工具调用的成功、正常空结果、失败或输入无效状态；不保存底层错误正文。
- 数据质量门控读取台账并按工具最终状态汇总，关键工具失败或未调用任何数据工具时将结论可信度限制为“低”。
- 最终结论在低可信度时由代码强制加注“数据不全”提示；台账、门控摘要和可信度状态一并持久化到结果 JSON。

All notable changes to TradingAgents are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Breaking changes within the 0.x line are called out explicitly.

## [Unreleased]

### 计划
- 政策分析师数据覆盖增强（见 `PLAN_v0.3.0_implementation.md`）

## [0.2.22] - 2026-07-15

门控 C vs A 矛盾修正 + push2 IDC 封禁代理支持 + prompt 假缺失消除。无破坏性变更、无新依赖。

### 修复
- **门控矛盾（quality_gate.py）**：硬检查不再因 `[数据缺失]` 数量 ≥3 机械判 C（改为 B，待 LLM 判断关键性）；`_build_review_prompt` 把硬检查结果喂给 LLM 复审，评级标准明确"非必采项缺失不影响 A 级"+ 要求与硬检查不一致需说明；summary 说明两层关系。消除"基本面硬检查 C vs LLM 复审 A"矛盾。
- **prompt 假缺失**：`fundamentals_analyst.py` 股权质押/减持计划预披露/关联交易（系统无接口）从硬要求改为"系统未采集"说明，消除 3 处设计性缺失；`hot_money_tracker.py` 必采清单后加标注规范，明确"龙虎榜近30日未上榜"等正常空结果不标 `[数据缺失]`，消除误标。

### 新增
- **push2 HTTP 代理（a_stock.py）**：`_EM_SESSION` 读 `EM_HTTP_PROXY` 环境变量设置 proxies。东财 push2.eastmoney.com 整域名对阿里云等 IDC IP 封禁（建连后 RemoteDisconnected），致资金流 fflow、行业对比 clist 全失败；设代理走非 IDC 出口绕过。不设则直连（本地开发无影响）。`_em_get` 重试对 ProxyError 自动兜底。

### 部署
- 服务器 `.env` 加 `EM_HTTP_PROXY=<代理URL>`，`bash scripts/update-server.sh --env` 部署。代理需自备（国内住宅 IP 最佳）。无代理时资金流仍缺，但门控+prompt 修正独立生效。

## [0.2.21] - 2026-07-15

数据质量门控三修复 + Week 5 过时快照勘误。无破坏性变更、无新依赖。

### 修复
- **基本面/解禁报告股价与技术分析不一致**：`get_fundamentals` 的股价原取腾讯实时价，分析基准日为历史日时与 `get_stock_data` 的历史收盘价产生时差（如 300308 实时 1169.31 vs 07-14 收盘 1184.05）。新增 `_resolve_price`/`_get_close_on_date`，当 `curr_date` 早于今日时改用该日 K 线收盘价（复用 `get_stock_data` 的 mootdx+新浪 fallback），Forward PE 计算同步对齐。
- **东财接口偶发 `RemoteDisconnected` 致行业对比/资金流缺失**：`_em_get` 原无重试，连接异常即失败。现对连接异常（RemoteDisconnected/Timeout/ConnectionError）或 5xx 响应按指数退避重试最多 3 次，4xx 直接返回不重试。
- **解禁报告股东户数变化/董监高交易记录缺失**：`get_insider_transactions` 原仅返回十大股东。增强为三段：十大股东（datacenter `RPT_F10_EH_HOLDERS`）+ 股东户数变化（F10 `ShareholderResearch/PageAjax` 的 `gdrs`：股东户数/变化比例/户均流通股/筹码集中度，近 4 期）+ 董监高持股变动（F10 `CompanyManagement/PageAjax` 的 `cgbd`：高管/职务/变动股数/均价/变动方式，近 10 条）。

### 文档
- DEV_LOG Week 5「14/14 接口全部 OK」补勘误：该记录是 akshare+旧 mootdx+pandas 2.x 旧实现快照，v0.2.5 移除 akshare 重写后未复跑回归，导致 5 个 bug 潜伏 2 个月。详见 `issues/008-week5-quality-gate-stale-snapshot.md`。

### 测试
- 新增 `tests/test_astock_v0221_fix.py` 8 例（股价对齐 3 + _em_get 重试 3 + insider 三段 2）；旧 `test_get_insider_transactions` 补 `_requests.get` mock 避免联网。全量 150 passed。

## [0.2.20] - 2026-07-15

概念板块/股东数据接口迁移（v0.2.19 部署后门控暴露的 2 个失效接口）。

### 修复
- **`get_concept_blocks` 百度 PAE 403**：`getrelatedblock` 端点下线，迁移至东财 F10 `CoreConception/PageAjax`（ssbk 所属板块 + hxtc 核心题材）。注：东财 ssbk 不含板块当日涨幅（百度原有），仅返回板块归属。
- **`get_insider_transactions` mootdx F10 失效**：mootdx 0.11.x 的 F10 栏目目录对个股仅暴露"最新提示"，`F10(name="股东研究")` 拿不到股东数据。迁移至东财 datacenter `RPT_F10_EH_HOLDERS`（按 END_DATE 降序取最新一期十大股东）。

### 测试
- 新增 `tests/test_astock_interface_fix.py` 2 例；全量 142 passed。详见 `issues/007-interface-migration.md`。

## [0.2.19] - 2026-07-15

关键财务数据缺失 3 bug 修复（用户报告"关键财务、主力资金数据缺失"）。

### 修复
- **`get_fundamentals` mootdx 字段取不到**：mootdx `client.finance()` 返回拼音缩写字段（`jinglirun`/`zhuyingshouru`/`meigujingzichan`...），旧 `field_map` 用 `eps`/`roe` 英文名取不到。改拼音字段并推算 `EPS=jinglirun/zongguben`、`ROE=jinglirun/jingzichan*100`。
- **新浪财报三表恒空**：v0.2.5 移除 akshare 后自写新浪 API 解析，误用 `result.data.lrb` key，实际结构为 `result.data.report_list[日期]["data"]`。重写解析，构造行=报告期/列=项目名 DataFrame。
- **同花顺 EPS 崩溃**：pandas 3.0 `read_html` 不再接受裸 HTML 字符串（当文件路径 open），改 `pd.read_html(io.StringIO(r.text))`。

### 测试
- 新增 `tests/test_astock_fundamentals_fix.py` 5 例；全量 140 passed。详见 `issues/006-fundamentals-data-missing.md`。

## [0.2.18] — 2026-07-10

合并社区 PR #75（致谢 @wangyuxun6699），与 v0.2.17 的 #76 修复同属一类问题：LLM 工具调用把非股票标识当 `ticker` 传入。

### 合并社区 PR
- **#75 新闻工具校验 ticker 防概念词中断分析（@wangyuxun6699）**：运行 000629 分析时部分 Agent 把概念词「钒电池」当 `ticker` 传给 `get_news`，底层解析抛 ValueError 中断分析。三层修复：① `get_news` / `get_insider_transactions` 增加 6 位代码校验，误传时**返回可恢复的错误提示**（不抛异常、不中断 LangGraph）；② 修正 5 个分析师提示词里误导性的 `get_news(query, ...)` 描述 → `get_news(ticker, ...)`（**这是模型传概念词的提示词层根因**）；③ 强化 `instrument_context`，明确「参数名为 ticker 时只传目标股票代码」。
- 与 v0.2.17 的 `resolve_ticker` 报错改进形成互补防线：提示词预防 → 工具层校验软着陆 → 解析层报错可自纠。

### 测试
- PR 新增 `tests/test_news_data_tools.py` 3 项（概念词拦截不进 vendor 层 / 合法 6 位码正常路由）通过。
- 全量回归：Python 3.12 干净 venv 下 `pytest tests/` **135 passed + 44 subtests**（仅 test_google_api_key 因未装可选依赖 `[google]` 跳过）。

## [0.2.17] — 2026-07-10

两个健壮性修复，无破坏性变更、无新依赖。

### 修复
- **fpdf 包损坏导致 Web UI 启动即崩（#72）**：`web/pdf_export.py` 顶部的 `from fpdf import FPDF` 一旦失败（fpdf2 卸载不干净留下 namespace 残包、或 pyfpdf 1.x 没有 `fpdf.enums`），`web/app.py` 在 import 链上直接崩溃、整个应用起不来。现改为守卫式导入：fpdf 坏了只禁用 PDF 导出（Markdown 导出照常），点击 PDF 按钮时给出确切修复命令 `pip uninstall -y fpdf fpdf2 && pip install "fpdf2>=2.8.0"`。
- **LLM 把行业名当股票代码时报错信息不可自纠（#76）**：弱模型做工具调用时偶尔把行业/概念名（如 002174 游族网络所属行业「游戏」）当 `ticker` 传入，旧报错「找不到股票 '游戏'，请检查名称是否正确」让用户困惑（自己输入的明明是 002174）、也无法引导模型纠正。新报错写明「ticker 只接受 6 位代码或完整股票名称，行业/概念/板块名无效」，模型读到 ToolMessage 后可在下一次调用自我纠正。

### 测试
- 实测模拟损坏 fpdf（`sys.modules` 注入空 namespace 包，复现 #72 同款 `cannot import name 'FPDF' from 'fpdf' (unknown location)`）：`web.pdf_export` import 成功、`generate_markdown` 正常出稿、`generate_pdf` 抛带修复指引的 `PDFExportError`。
- `resolve_ticker` 回归：`002174`/`600519.SH`/`贵州茅台` 正常解析；`游戏` 触发新报错文案。
- `tests/test_pdf_export.py` + `test_safe_ticker_component.py` + `test_stock_display.py` + `test_web_history.py` + `test_astock_sina_supplement.py` 共 25 项通过（2 项 pdf 字体用例在本机因 fpdf2 2.8.4 < 2.8.6 环境原因失败，HEAD 上同样失败，与本次改动无关）。

## [0.2.16] — 2026-06-28

本版采纳一个社区贡献的批量样例脚本 + 文档补充，无核心代码改动。

### 采纳社区贡献
- **`examples/run_cases.py` 升级（采纳 #68 @zcc2xj）**：旧版批量脚本只把 `final_trade_decision` 手写进简易 `.md`。新版复用 CLI 的 `save_report_to_disk()`，每只标的输出与 CLI **完全一致**的 `complete_report.md`（分析师 / 研究 / 交易 / 风险 / 组合五个分区子目录 + 合并报告），并落一份字段齐全的 `summary.json`（10 个顶层报告 + Bull/Bear 辩论 + 三方风险辩论历史）。解决 #68「example 脚本如何拿到 CLI 那样的 complete_report.md」。

### 文档
- **README 常见问题新增 httpx 依赖冲突说明（#70）**：澄清 **litellm / mcp 不是本项目依赖**（用户报错里这两条来自其环境的其它包）；核心安装 `pip install -e .` 默认不冲突，仅装 `[google]` 用 Gemini 时 mootdx（`httpx<0.26`）与 google-genai（`httpx>=0.28`）互斥。给出解法：mootdx 走 TCP、运行时不调 httpx（实测 0.11.7 在 httpx 0.28.1 下取数正常，可放心升 httpx）/ 分 venv / 用国内直连模型不装 `[google]`。
- README 常见问题新增「不进 CLI 怎么批量跑、拿完整报告」条目，指向 `examples/run_cases.py`。

### 测试
- `examples/run_cases.py` py_compile 语法通过；静态核对 `save_report_to_disk(final_state, ticker, save_path)` 签名匹配、`complete_report.md` 路径返回值正确（`cli/main.py:738-739`），脚本引用的 10 个顶层 state 字段 + debate 子状态字段全部匹配 `agent_states.py` 真实定义（含 policy/hot_money/lockup 三个 A 股特化字段）。端到端运行需用户自备 LLM key。
- httpx 解法复用 a-stock-data 同源实测：净 venv 装 mootdx 0.11.7 后 `--no-deps` 升 httpx 0.28.1，`bars()` 取日线 / 1 分钟均正常。

## [0.2.15] — 2026-06-20

本版合并 4 个社区 PR + 一批针对性修复，主线集中在「数据可靠性 + 模型可用性 + 全新安装体验」。

### 合并社区 PR（致谢贡献者）
- **#64（@wikinl）**：A 股日 K 数据滞后时未触发新浪补齐 → 修复（mootdx 返回非空但最新日期早于目标日时强制走新浪补最新交易日，并把 `15:00:00` 时间戳压到自然日，避免被 `Date <= cutoff` 误过滤）。直接缓解 #60「数据缺失」。
- **#57（@zhanghang02）**：Web 支持中断续跑 + 侧边栏暂停/停止控制（LangGraph checkpoint resume）。缓解 #27「页面刷新丢数据」。
- **#56（@zhanghang02）**：中文 PDF 字体发现 + 排版稳定性增强（`fc-match`/WQY 优先、字体环境变量覆盖、TTC 字面选择）。
- **#55（@zhanghang02）**：报告标的统一显示为「代码 + 名称」。合并时解决与 #57 在 `web/runner.py` 的冲突（#57 的 `finalize_graph_run` 已含 `graph.ticker`/`_log_state`，仅保留归一化调用挪到落盘前）。

### 修复
- **mootdx 0.11.x 全新安装 BESTIP 空串崩溃 → 中文股票名解析失败（#46/#66 根因之一）**：`_get_mootdx_client()` 升级为健壮版——TCP 探测内置可用通达信服务器列表，用显式 `server=(ip,port)` 绕过 `BESTIP.HQ` 空串 bug，三级 fallback（bestip 测速 → 裸 factory → 明确报错）。`_build_name_code_map()` 改走该 client 并加 try/except，解析失败时给出「请重试或直接输入 6 位代码」而非冒泡成风马牛不相及的报错。实测 mootdx 0.11.7：10/10 服务器可达，`贵州茅台→600519`、`宁德时代→300750` 正常。
- **`.env` 未优先于残留环境变量（#66）**：`web/app.py` 的 `load_dotenv` 改为 `override=True`，让 `.env` 的值优先；并注明启动后改 `.env` 需重启 Web 服务。
- **fpdf2 版本下限过低导致 #56 在旧版崩溃**：`collection_font_number`（TTC 字面选择）是 fpdf2 **2.8.6**（2026-02-18）才引入的参数，旧约束 `fpdf2>=2.8.0` 下用户若缓存 2.8.0~2.8.5 会在中文 PDF 导出时抛 `TypeError` → 收紧为 `fpdf2>=2.8.6`，错排提示同步更新。

### 新增
- **OpenRouter 进入 Web 侧栏模型选择器（摘自 #32，缓解 #45/#62）**：`factory`/`_PROVIDER_CONFIG` 早已支持 OpenRouter，但侧栏 `_PROVIDERS` 未列 → 补上「OpenRouter（聚合）」一项，选中后填 `vendor/model` 形式的模型 ID（如 `deepseek/deepseek-chat`）即可。凭证池/profile 体系（#32 其余部分）超出「加个模型」范围，另行评估。

### 文档
- README「快速开始」明确「装完即可用、无需 Docker」（直接 `streamlit run web/app.py` 或 `tradingagents`），缓解 #46 安装说明困惑。

### 测试
- 4 个 PR 自带测试在隔离环境实测：`test_stock_display`(11)/`test_progress_pause`(4)/`test_web_history`(3)/`test_astock_sina_supplement`(2) 全通过（PDF 测试在 Python 3.9 + 旧 fpdf2 环境因版本特性跳过，真实 ≥3.10 + fpdf2≥2.8.6 环境正常）。
- mootdx 健壮 client + 中文名解析在 mootdx 0.11.7 真实环境实测通过。

## [0.2.14] — 2026-06-18

### 修复

- **Docker 命名卷权限崩溃（#46，感谢 @tyraanTao 等报告）**：`docker compose up` 后容器内进程以
  `appuser` 运行，但 `docker-compose.yml` 的命名卷 `tradingagents_data` 挂到
  `/home/appuser/.tradingagents` 时，由于镜像里没有预建该目录，Docker 把挂载点建成了
  `root:root`，导致应用写缓存被拒：`[Errno 13] Permission denied: /home/appuser/.tradingagents/cache`。
  Dockerfile 现在在 `USER appuser` 之后**预建** `/home/appuser/.tradingagents`（含 `cache` /
  `logs` / `memory` 三个子目录）——Docker 对空命名卷会继承镜像挂载点目录的属主，于是卷归属 appuser，
  容器可正常写入。
  - 升级：`git pull` 后 `docker compose build --no-cache` 重建镜像；旧数据卷可先
    `docker run --rm -v tradingagents_data:/d alpine chown -R 1000:1000 /d` 修正属主，
    或 `docker volume rm tradingagents_data` 后重建。

### 说明

- 仅 Dockerfile 改动（预建数据目录），Python 代码 / 数据层 / Agent 逻辑零改动。
- 同批排查的 #59（PDF `latin-1` 崩溃）与 #66（`OPENAI_API_KEY` 报错）经复现确认已分别在
  v0.2.12 修复（`_ensure_fpdf2()` 守卫 + Markdown 兜底 / 各供应商独立 Key 提示），升级即可，无需改动。

## [0.2.13] — 2026-06-04

### Security

- **CLI 路径穿越加固（#51，感谢 @mituxunzhi 报告并给出修复方向）**：CLI 是唯一未对 ticker 做
  路径组件校验的入口（Web UI / `a_stock.py` / `checkpointer.py` / `stockstats_utils.py` 早已统一走
  `safe_ticker_component`）。ticker 会被拼进 `results_dir / <ticker> / <date>` 和报告保存路径，
  形如 `../../tmp/evil` 的输入可写到目标目录之外。三处加固：
  - `cli/utils.py:normalize_ticker_symbol()` — 现在委托 `safe_ticker_component()` 校验（拒绝
    `/`、`..`、`~`、`\0`、绝对路径、纯点等），并返回校验/解析后的安全值（中文名自动解析为 6 位代码）；
  - `cli/main.py:get_ticker()` — 输入后即校验，非法则提示并**重新询问**（而非崩溃），返回安全值；
  - `cli/main.py` 报告保存 — 保存路径先 `.resolve()`，若落在当前目录之外则**提示并要求确认**，
    拒绝则取消保存。
  - 实测：`../../tmp/evil`、`/etc/passwd`、`~/secret`、`a/../../b`、`\x00evil`、`.` 等 11 个穿越载荷
    全部被拒；`SPY` / `600519` / `0700.HK` / `^GSPC` / `BRK.B` 等正常代码全部通过且保留交易所后缀。

### 说明

- 纯 CLI 入口安全加固，复用既有 `safe_ticker_component` 校验器，数据层 / Agent 逻辑零改动。

## [0.2.12] — 2026-06-03

### Fixed

- **PDF 导出中文崩溃（#54）**：项目依赖 `fpdf2`，但它和早已废弃的 `pyfpdf`（1.x）**都以 `fpdf`
  名称导入**，二者共存时谁后装谁生效。用户环境里若残留 pyfpdf，导出中文报告会在库内部抛出晦涩的
  `UnicodeEncodeError: 'latin-1' codec can't encode`（pyfpdf 用 latin-1 编码每一页）。
  `web/pdf_export.py` 新增 `_ensure_fpdf2()`：导出前检测 fpdf 版本，若是旧库则抛出**可操作**的中文
  提示（`pip uninstall -y fpdf && pip install "fpdf2>=2.8.0"`），不再让 PDF 渲染到一半崩溃。
- **Docker 内无法导出 PDF（#48）**：运行镜像基于 `python:3.12-slim`，不含任何中文字体，
  `_find_cjk_font()` 返回 None → 抛「未找到中文字体」。Dockerfile 运行阶段新增
  `apt-get install fonts-noto-cjk`，容器内 PDF 导出开箱即用。
- **DeepSeek/通义/智谱等报 `OPENAI_API_KEY must be set`（#42）**：这些 OpenAI 兼容供应商各自需要
  **专属环境变量**（DeepSeek=`DEEPSEEK_API_KEY`、通义=`DASHSCOPE_API_KEY`、智谱=`ZHIPU_API_KEY`、
  MiniMax=`MINIMAX_API_KEY` 等），但 key 缺失时 ChatOpenAI 只会抛出令人误解的 `OPENAI_API_KEY` 错误。
  `openai_client.py` 现在在缺 key 时**明确指出该供应商对应的环境变量名**；Web 侧边栏 help 文案也补齐了
  每个供应商的 key 变量对照，避免用户设错。

### 说明

- 三项均为环境/配置类问题的健壮性修复，数据层与 Agent 逻辑无改动。PDF 修复经 fpdf2 实测生成
  中文报告通过 + 旧库检测单测通过；#42 经 api_key 解析分支单测全用例通过。

## [0.2.11] — 2026-05-30

### Changed

- **东财接口统一限流防封（移植自 a-stock-data v3.2）**：数据层 `a_stock.py` 里所有指向
  `eastmoney.com` 的请求（push2 / push2his / datacenter-web / search-api / np-weblist
  共 7 个调用点）统一收口到新的节流入口 `_em_get()`，多 Agent 投研跑批量分析时不再触发
  临时封 IP（社区实测东财风控：每秒 >5 / 并发 ≥10 / 1 分钟 ≥200 / 5 分钟 ≥300 触发封禁，
  多位用户反馈过）。具体：
  - 模块级 last-call 时间戳 + 最小间隔 `EM_MIN_INTERVAL`（默认 1.0s，可用同名环境变量覆盖）
    + 0.1~0.5s 随机抖动，串行限流，QPS ≤ 1；
  - 复用 `requests.Session`（Keep-Alive）+ 默认 UA；各端点保留自己的 Referer/Origin header；
  - **仅东财接口限流**——mootdx(TCP) / 腾讯 / 新浪 / 同花顺 / 财联社 / 百度 等非东财源
    不受影响（实测不封 IP）。批量场景可设 `EM_MIN_INTERVAL=1.5~2` 进一步降速。

### Tested

- 实测 4 次连续 `_em_get` 请求东财 push2（600519 = 贵州茅台），HTTP 200 返回真实数据；
  相邻调用间隔 1.47 / 1.18 / 1.42s 均 ≥1.0s，限流生效。
- `get_industry_comparison` / `get_fund_flow` / `get_dragon_tiger_board` 三个东财公共函数
  端到端跑通（走同一已验证的 `_em_get` 通道）；`py_compile` 通过；grep 复核：7 个 `_em_get`
  调用点 + 0 个残留 `_req.` + 8 个非东财源（mootdx/腾讯/新浪/同花顺/财联社/百度）未被误伤。

---

## [0.2.10] — 2026-05-30

### Added

- **Web UI 支持第三方 / 代理 API 网关（#35）**：侧边栏新增「API Base URL」输入框，
  也可在 `.env` 设 `BACKEND_URL`。方便国内用户通过中转网关访问 Claude / OpenAI 等模型
  （API Key 仍从 `.env` 读取，如 `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`）。
  侧边栏输入优先于环境变量，留空则用所选供应商官方地址。

---

## [0.2.9] — 2026-05-30

### Added

- **Markdown 报告导出**：分析结果页新增「下载 Markdown」按钮。MD 导出零字体依赖、
  跨平台永远可用，是 PDF 之外的稳妥兜底（#17 多位用户请求）。

### Fixed

- **PDF 中文字体跨平台崩溃（#22 / #30 / #31）**：原 `_FONT_CANDIDATES` 只列了
  macOS/Linux 字体，Windows 用户找不到中文字体 → fpdf 回退 Helvetica → 渲染中文时
  抛 `FPDFUnicodeEncodingException` / `Character "股" ... outside the range`。
  现改为**按操作系统排序的字体候选**（Windows 微软雅黑/黑体/宋体、macOS 苹方、
  Linux Noto/文泉驿）+ 递归扫描字体目录兜底。
- **PDF 失败拖垮整个结果页**：`generate_pdf` 原先在结果页渲染时被 eager 调用，一旦
  报错整页崩成 traceback，用户连分析结果都看不到。现改为 **try/except 包裹 + 懒生成**，
  PDF 失败只禁用 PDF 按钮并提示改用 Markdown，分析报告照常显示。
- **长串中文表格/段落渲染报错（#31）**：`multi_cell` 遇到无空格的长中文串抛
  `Not enough horizontal space to render a single character`。已为内容 `multi_cell`
  加 `wrapmode="CHAR"` 并复位左边距，中文按字符正确换行。
- **缺字体时优雅降级**：系统无任何中文字体时，`generate_pdf` 抛出清晰中文报错
  （指引安装字体或改用 Markdown），不再是深层 fpdf traceback。

### Tested

- Streamlit 1.50 环境用 fpdf2 2.8.4 实测：含中文标题、表格、列表、200 字无空格长串的
  报告成功生成 7 页 PDF（目视确认中文渲染无乱码、长串正确换行）；Markdown 导出正常；
  无字体路径正确抛 RuntimeError。

---

## [0.2.8] — 2026-05-30

### Fixed

- **Web UI 侧边栏收起后无法展开（#36）**：为录视频清爽化界面的自定义 CSS 把整个
  顶栏 `stHeader` 和工具栏 `stToolbar` 都 `display:none` 掉了。但 Streamlit ≥1.36 的
  「展开侧边栏」按钮 `stExpandSidebarButton` 正好嵌在工具栏内部，于是侧边栏一旦收起
  ——无论是手动点收起箭头，还是**页面缩放 / 窄屏时 Streamlit 自动收起**——展开按钮
  跟着被隐藏，再也调不出来，刷新、重启都没用。原先那行兜底的 `collapsedControl`
  选择器是旧版 DOM，在 1.45+ 已不存在，等于没写。
  修复：不再整个隐藏顶栏/工具栏，改为**保留二者、将 header 透明化、只精准隐藏
  Deploy 按钮 / 主菜单 / 状态条 / 装饰条**，侧边栏展开按钮恢复可见可点，录屏依旧干净。
  已用 Streamlit 1.50 + headless Chrome 在收起/展开两种状态下实测验证。

---

## [0.2.7] — 2026-05-19

### Fixed

- **百度 PAE 资金流下线**：`fundflow` + `fundsortlist` 接口已返回空，
  `get_fund_flow()` 全部替换为东财 push2 资金流 API（分钟级 + 日级 20 天）
- **龙虎榜机构动向**：`RPT_ORGANIZATION_BUSSINESS` 报表配置已下线，
  改用 BUY/SELL 席位明细筛选 `OPERATEDEPT_CODE="0"`（机构专用席位）
- **东财全球资讯**：新增必填参数 `req_trace`（UUID），否则返回 403

---

## [0.2.6] — 2026-05-19

### Fixed

- **依赖冲突**：`langchain-google-genai` 移至可选依赖组 `[google]`，
  消除与 mootdx 的 httpx 版本冲突。`pip install -e .` 开箱即用，
  需要 Google Gemini 时 `pip install -e ".[google]"`。
- **WebUI 模型写死 minimax**：侧边栏新增 LLM 供应商和模型选择器，
  支持 9 个供应商（MiniMax/DeepSeek/Qwen/GLM/OpenAI/Anthropic/Google/xAI/Ollama），
  默认仍为 MiniMax 但用户可自由切换。
- **阶段分析内容消失**：进度面板现在展示所有已完成阶段的报告（按时间倒序），
  不再只显示最新的一个。最新阶段自动展开，历史阶段可点击展开。

### Changed

- `.env.example` 补充 `MINIMAX_API_KEY=` 条目
- README 快速开始增加 Google 可选依赖安装说明
- README Web UI 功能列表更新

## [0.2.5] — 2026-05-17

### Breaking Changes

- **移除 akshare 依赖** — `akshare>=1.18.0` 从 `pyproject.toml` 中删除。
  所有原 akshare 调用已替换为直接 HTTP API（东财 datacenter、新浪财经、
  同花顺 10jqka、财联社 cls.cn、百度股市通）。

### Changed

- `tradingagents/dataflows/a_stock.py` 全面重构数据获取层：
  - `get_stock_data()` → 新浪 JSON K线 API + push2.eastmoney 实时行情
  - `get_stock_info()` → push2.eastmoney 个股基本信息
  - `get_stock_news()` → 东财 np-weblist 滚动新闻（已有，无变化）
  - `get_financial_data()` → 新浪财经财报三表 API
  - `get_market_news()` → 财联社 cls.cn 快讯 + 东财 np-weblist
  - `get_analyst_forecast()` → 同花顺 10jqka EPS 一致预期
  - `get_dragon_tiger_board()` → 东财 datacenter RPT_DAILYBILLBOARD
  - `get_restricted_release()` → 东财 datacenter RPT_LIFT_STAGE
  - `get_industry_overview()` → push2.eastmoney 板块行情
- 新增内部 helper：`_eastmoney_datacenter()`、`_ths_eps_forecast()`、`_sina_kline_fallback()`
- 所有函数签名和返回格式保持不变，对上层 Agent 透明

### Fixed

- 彻底消除 akshare + pandas 3.0 + pyarrow 的 `ArrowInvalid` 崩溃问题
- 消除 akshare 与 mootdx 的 httpx 版本冲突

## [0.2.4] — 2026-04-25

### Added

- **Structured-output decision agents.** Research Manager, Trader, and Portfolio
  Manager now use `llm.with_structured_output(Schema)` on their primary call
  and return typed Pydantic instances. Each provider's native structured-output
  mode is used (`json_schema` for OpenAI / xAI, `response_schema` for Gemini,
  tool-use for Anthropic, function-calling for OpenAI-compatible providers).
  Render helpers preserve the existing markdown shape so memory log, CLI
  display, and saved reports keep working unchanged. (#434)
- **LangGraph checkpoint resume** — opt-in via `--checkpoint`. State is saved
  after each node so crashed or interrupted runs resume from the last
  successful step. Per-ticker SQLite databases under
  `~/.tradingagents/cache/checkpoints/`. `--clear-checkpoints` resets them. (#594)
- **Persistent decision log** replacing the per-agent BM25 memory. Decisions
  are stored automatically at the end of `propagate()`; the next same-ticker
  run resolves prior pending entries with realised return, alpha vs SPY, and
  a one-paragraph reflection. Override path with `TRADINGAGENTS_MEMORY_LOG_PATH`.
  Optional `memory_log_max_entries` config caps resolved entries; pending
  entries are never pruned. (#578, #563, #564, #579)
- **DeepSeek, Qwen (Alibaba DashScope), GLM (Zhipu), and Azure OpenAI**
  providers, plus dynamic OpenRouter model selection.
- **Docker support** — multi-stage build with separate dev and runtime images.
- **`scripts/smoke_structured_output.py`** — diagnostic that exercises the
  three structured-output agents against any provider so contributors can
  verify their setup with one command.
- **5-tier rating scale** (Buy / Overweight / Hold / Underweight / Sell) used
  consistently by Research Manager, Portfolio Manager, signal processor, and
  the memory log; Trader keeps 3-tier (Buy / Hold / Sell) since transaction
  direction is naturally ternary.
- **Pytest fixtures** — lazy LLM client imports plus placeholder API keys so
  the test suite runs cleanly without credentials. (#588)

### Changed

- **`backend_url` default is now `None`** rather than the OpenAI URL. Each
  provider client falls back to its native default. The previous default
  leaked the OpenAI URL into non-OpenAI clients (e.g. Gemini), producing
  malformed request URLs for Python users who switched providers without
  overriding `backend_url`. The CLI flow is unaffected.
- All file I/O passes explicit `encoding="utf-8"` so Windows users no longer
  hit `UnicodeEncodeError` with the cp1252 default. (#543, #550, #576)
- Cache and log directories moved to `~/.tradingagents/` to resolve Docker
  permission issues. (#519)
- `SignalProcessor` reads the rating from the Portfolio Manager's rendered
  markdown via a deterministic heuristic — no extra LLM call.
- OpenAI structured-output calls default to `method="function_calling"` to
  avoid noisy `PydanticSerializationUnexpectedValue` warnings emitted by
  langchain-openai's Responses-API parse path. Same typed result, no warnings.

### Fixed

- Empty memory no longer triggers fabricated past-lessons in agent prompts;
  the memory-log redesign makes this structurally impossible since only the
  Portfolio Manager consults memory and only when entries exist. (#572)
- Tool-call logging processes every chunk message, not just the last one, and
  memory score normalization handles empty score arrays. (#534, #531)

### Removed

- `FinancialSituationMemory` (the per-agent BM25 system) and the dead
  `reflect_and_remember()` plumbing; subsumed by the persistent decision log.
- Hardcoded Google endpoint that caused 404 when `langchain-google-genai`
  changed its API path. (#493, #496)

### Contributors

Thanks to everyone who shaped this release through code, design, and reports:

- [@claytonbrown](https://github.com/claytonbrown) — checkpoint resume (#594), test fixtures (#588), design feedback on cost tracking (#582) and structured validation (#583)
- [@Bcardo](https://github.com/Bcardo) — memory-log redesign (#579), empty-memory hallucination report (#572), encoding fix proposal (#570)
- [@voidborne-d](https://github.com/voidborne-d) — memory persistence design (#564), portfolio manager state fix (#503)
- [@mannubaveja007](https://github.com/mannubaveja007) — structured-output feature request (#434)
- [@kelder66](https://github.com/kelder66) — RAM-only memory issue (#563)
- [@Gujiassh](https://github.com/Gujiassh) — tool-call logging fix (#534), test stub PR (#533)
- [@iuyup](https://github.com/iuyup) — memory score normalization fix (#531)
- [@kaihg](https://github.com/kaihg) — Google base_url fix (#496)
- [@32ryh98yfe](https://github.com/32ryh98yfe) — Gemini 404 report (#493)
- [@uppb](https://github.com/uppb) — OpenRouter dynamic model selection (#482)
- [@guoz14](https://github.com/guoz14) — OpenRouter limited-model report (#337)
- [@samchenku](https://github.com/samchenku) — indicator name normalization (#490)
- [@JasonOA888](https://github.com/JasonOA888) — y_finance pandas import fix (#488)
- [@tiffanychum](https://github.com/tiffanychum) — stale import cleanup (#499)
- [@zaizou](https://github.com/zaizou) — Docker permission issue (#519)
- [@Stosman123](https://github.com/Stosman123), [@mauropuga](https://github.com/mauropuga), [@hotwind2015](https://github.com/hotwind2015) — Windows encoding bug reports (#543, #550, #576)
- [@nnishad](https://github.com/nnishad), [@atharvajoshi01](https://github.com/atharvajoshi01) — encoding fix proposals (#568, #549)

## [0.2.3] — 2026-03-29

### Added

- **Multi-language output** for analyst reports and final decisions, with a
  CLI selector. Internal agent debate stays in English for reasoning quality. (#472)
- **GPT-5.4 family models** in the default catalog, with deep/quick model split.
- **Unified model catalog** as a single source of truth for CLI options and
  provider validation.

### Changed

- `base_url` is forwarded to Google and Anthropic clients so corporate proxies
  work consistently across providers. (#427)
- Standardised the Google `api_key` parameter to the unified `api_key` form.

### Fixed

- Backtesting fetchers no longer leak look-ahead data when `curr_date` is in
  the middle of a fetched window. (#475)
- Invalid indicator names from the LLM are caught at the tool boundary instead
  of crashing the run. (#429)
- yfinance news fetchers respect the same exponential-backoff retry as price
  fetchers. (#445)

### Contributors

- [@ahmedk20](https://github.com/ahmedk20) — multi-language output (#472)
- [@CadeYu](https://github.com/CadeYu) — model catalog typing (#464)
- [@javierdejesusda](https://github.com/javierdejesusda) — unified Google API key parameter (#453)
- [@voidborne-d](https://github.com/voidborne-d) — yfinance news retry (#445)
- [@kostakost2](https://github.com/kostakost2) — look-ahead bias report (#475)
- [@lu-zhengda](https://github.com/lu-zhengda) — proxy/base_url support request (#427)
- [@VamsiKrishna2021](https://github.com/VamsiKrishna2021) — invalid indicator crash report (#429)

## [0.2.2] — 2026-03-22

### Added

- **Five-tier rating scale** (Buy / Overweight / Hold / Underweight / Sell)
  introduced for the Portfolio Manager.
- **Anthropic effort level** support for Claude models.
- **OpenAI Responses API** path for native OpenAI models.

### Changed

- `risk_manager` renamed to `portfolio_manager` to match the role description
  shown in the CLI display.
- Exchange-qualified tickers (e.g. `7203.T`, `BRK.B`) preserved across all
  agent prompts and tool calls.
- Process-level UTF-8 default attempted for cross-platform consistency
  (note: this approach did not actually take effect; replaced in v0.2.4 with
  explicit per-call `encoding="utf-8"` arguments).

### Fixed

- yfinance rate-limit errors are retried with exponential backoff. (#426)
- HTTP client SSL customisation is supported for environments that need
  custom certificate bundles. (#379)
- Report-section writes handle list-of-string content gracefully.

### Contributors

- [@CadeYu](https://github.com/CadeYu) — exchange-qualified ticker preservation (#413)
- [@yang1002378395-cmyk](https://github.com/yang1002378395-cmyk) — HTTP client SSL customisation (#379)

## [0.2.1] — 2026-03-15

### Security

- Patched `langchain-core` vulnerability (LangGrinch). (#335)
- Removed `chainlit` dependency affected by CVE-2026-22218.

### Added

- `pyproject.toml` build-system configuration; the project now installs via
  modern packaging tooling.

### Removed

- `setup.py` — dependencies consolidated to `pyproject.toml`.

### Fixed

- Risk manager reads the correct fundamental report source. (#341)
- All `open()` calls receive an explicit UTF-8 encoding (initial pass).
- `get_indicators` tool handles comma-separated indicator names from the LLM. (#368)
- `Propagation` initialises every debate-state field so risk debaters never
  see missing keys.
- Stock data parsing tolerates malformed CSVs and NaN values.
- Conditional debate logic respects the configured round count. (#361)

### Contributors

- [@RinZ27](https://github.com/RinZ27) — `langchain-core` security patch (#335)
- [@Ljx-007](https://github.com/Ljx-007) — risk manager fundamental-report fix (#341)
- [@makk9](https://github.com/makk9) — debate-rounds config issue (#361)

## [0.2.0] — 2026-02-04

This is the largest release since the initial public version. The framework
moved from single-provider to a multi-provider architecture and grew several
production-ready surfaces.

### Added

- **Multi-provider LLM support** (OpenAI, Google, Anthropic, xAI, OpenRouter,
  Ollama) via a factory pattern, with provider-specific thinking configurations.
- **Alpha Vantage** integration as a configurable primary data provider, with
  yfinance as a community-stability fallback.
- **Footer statistics** in the CLI: real-time tracking of LLM calls, tool
  calls, and token usage via LangChain callbacks.
- **Post-analysis report saving** — the framework writes per-section markdown
  files (analyst reports, debate transcripts, final decision) when a run
  completes.
- **Announcements panel** — fetches updates from `api.tauric.ai/v1/announcements`
  for the CLI welcome screen.
- **Tool fallbacks** so a single vendor outage does not stop the pipeline.

### Changed

- Risky / Safe risk debaters renamed to **Aggressive / Conservative** for
  consistency with the displayed agent labels.
- Default data vendor switched to balance reliability and quota across
  community deployments.
- Ollama and OpenRouter model lists updated; default endpoints clarified.

### Fixed

- Analyst status tracking and message deduplication in the live display.
- Infinite-loop guard in the agent loop; reflection and logging hardened.
- Various data-vendor implementation bugs and tool-signature mismatches.

### Contributors

This release is the first with substantial outside contributions; many community
PRs from late 2025 also landed here.

- [@luohy15](https://github.com/luohy15) — Alpha Vantage data-vendor integration (#235)
- [@EdwardoSunny](https://github.com/EdwardoSunny) — yfinance fetching optimisations (#245)
- [@Mirza-Samad-Ahmed-Baig](https://github.com/Mirza-Samad-Ahmed-Baig) — infinite-loop guard, reflection, and logging fixes (#89)
- [@ZeroAct](https://github.com/ZeroAct) — saved results path support (#29)
- [@Zhongyi-Lu](https://github.com/Zhongyi-Lu) — `.env` gitignore (#49)
- [@csoboy](https://github.com/csoboy) — local Ollama setup (#53)
- [@chauhang](https://github.com/chauhang) — initial Docker support attempt (#47, later reverted; the merged Docker support shipped in v0.2.4)

## [0.1.1] — 2025-06-07

### Removed

- Static site assets that had been bundled with v0.1.0; the public site now
  lives separately.

## [0.1.0] — 2025-06-05

### Added

- **Initial public release** of the TradingAgents multi-agent trading
  framework: market / sentiment / news / fundamentals analysts; bull and bear
  researchers; trader; aggressive, conservative, and neutral risk debaters;
  portfolio manager. LangGraph orchestration, yfinance data, per-agent
  BM25 memory, single-provider OpenAI integration, interactive CLI.

[0.2.4]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/TauricResearch/TradingAgents/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/TauricResearch/TradingAgents/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/TauricResearch/TradingAgents/releases/tag/v0.1.0
