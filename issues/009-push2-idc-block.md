# Issue #009: 门控 C vs A 矛盾 + 东财 push2 IDC 封禁致资金流/行业对比缺失

**状态**: ✅ 已修复（v0.2.22，2026-07-15）
**发现**: 服务器跑 601689 拓普集团分析，数据质量门控结果"基本面分析师 [C] 3 处数据缺失"但 LLM 复审数据质量审核报告评级 A，前后矛盾。游资追踪师同样 [C] 3 处缺失。

---

## 一、矛盾根因（门控设计缺陷）

`tradingagents/agents/quality_gate.py` 两层评级标准不一致且不互通：

| 层 | 逻辑 | 基本面判定 |
|---|------|-----------|
| Layer1 硬检查（代码） | `report.count("[数据缺失") >= 3` 机械计数判 C（行 51/59），不看缺失项是否关键、是否在必采清单 | 3 处 -> **C** |
| Layer2 LLM 复审 | prompt **不含硬检查结果**（行 78-79 只喂报告原文），LLM 独立语义判断 | 必采 8 项全覆盖，3 处是非必采项 -> **A** |

两层结果都原样写进 `data_quality_summary`（行 161-163）并列展示，无调和机制 -> 用户看到 C 和 A 并存，矛盾。

**本质**：硬检查把"非关键项缺失"和"关键数据失败"混为一谈（都计 1 处），LLM 又不知道硬检查说了啥。

---

## 二、6 处 `[数据缺失]` 真伪核实

### 基本面 3 处 -- 全是"设计性缺失"，必采清单实际全覆盖

| 缺失项 | 在必采清单? | 系统有接口? | 性质 |
|--------|:----------:|:----------:|------|
| 股权质押比例 | ❌ | ❌ | `fundamentals_analyst.py:37` prompt 列为"特殊风险关注"，但工具列表（行 21-28）没给获取工具 |
| 大股东减持计划 | ❌ | ❌ | 同上（`get_insider_transactions` 只在游资追踪师挂载） |
| 关联交易规模 | ❌ | ❌ | 同上 |

-> LLM 无工具可用只能标 `[数据缺失]`。**必采 8 项（PE/PB/营收/净利润/ROE/资产负债率/现金流/EPS）报告里全有**，LLM 给 A 合理，硬检查判 C 是误判。

### 游资追踪 3 处 -- 1 真缺失 + 1 误标 + 1 重复

| 缺失项 | 在必采清单? | 系统有接口? | 性质 |
|--------|:----------:|:----------:|------|
| 当日分钟级主力资金流 | ✅ 第 3 项 | ✅ `get_fund_flow`（push2） | **真缺失**（push2 被封） |
| 近 30 日未上龙虎榜 | ❌ | ✅ `get_dragon_tiger_board`（datacenter） | **假缺失**（接口正常返回"未上榜"，LLM 误标） |
| 分钟级接口暂不可用 | 同首处 | ✅ | 重复标注同一真缺失 |

---

## 三、真缺失根因 -- 东财 push2 封阿里云 IDC IP（环境问题，非代码 bug）

服务器实测铁证（阿里云 ECS，Asia/Shanghai 时区）：

```
容器内 get_fund_flow(601689) -> RemoteDisconnected('Remote end closed connection without response')
curl push2.eastmoney.com (UA/Referer/Origin/Cookie 各种 headers) -> HTTP=000 全失败
curl push2his.eastmoney.com -> HTTP=000 全失败
curl 82/19/90.push2.eastmoney.com (数字节点) -> HTTP=000 全失败
curl push2.eastmoney.com HTTP(非HTTPS) -> HTTP=000（非 SNI 层封禁）
curl datacenter-web.eastmoney.com -> HTTP=200 正常（未被封）
curl push2.dfcfw.com / hqsouth.eastmoney.com -> 302 IIS（非行情 API）
```

- **被封**：`push2.eastmoney.com` 整域名对阿里云 IDC IP 持续封禁（允许 TCP/TLS 握手，应用层立即 RemoteDisconnected）。受影响：**资金流 fflow、行业对比 clist、实时行情 get**
- **不受影响**：`datacenter-web`（龙虎榜/股东/解禁）、mootdx TCP + 新浪（K 线）、腾讯 qt.gtimg.cn（PE/PB）
- **v0.2.21 的 `_em_get` 重试对此无效**：重试 3 次都被服务端断开，是持续封禁非偶发抖动
- **本地开发无此问题**：本机 IP 非 IDC，push2 直连可用（仅本机 Windows 系统代理致 ProxyError，与服务器无关）

### 资金流回退源实测（全部不可用）

| 候选源 | 实测结果 |
|--------|---------|
| 东财 push2/push2his | 整域名 IP 封禁 |
| 东财 datacenter（RPT_CAPITALFLOW） | 无此 reportName（"字段不能为空"） |
| 腾讯 proxy.finance.qq.com / web.ifzq.gtimg.cn 资金流 | `Call to undefined method` / `Can't load controller` |
| 新浪 ssl_qsfx_zjlrqs（个股专用） | 已下线（Input error） |
| 新浪 ssl_bkzj_ssggzj（市场排行） | 可达但不可靠（5000 条不含 601689） |

-> **结论：阿里云 IDC 上个股资金流无可靠免费 API 替代源。** 采用 HTTP 代理恢复 push2（用户决策）。

---

## 四、修复方案（v0.2.22，三层）

### Layer 1: 数据层 - push2 HTTP 代理支持
- `a_stock.py` `_EM_SESSION` 初始化读 `EM_HTTP_PROXY` 环境变量，设了则 `_EM_SESSION.proxies = {"http": url, "https": url}`
- 向后兼容：不设则直连（本地开发无影响）
- `_em_get` 重试对 `ProxyError`（RequestException 子类）自动兜底
- `.env.example` / `.env.enterprise.example` 加 `EM_HTTP_PROXY` 注释

### Layer 2: 门控层 - 消除 C vs A 矛盾
- `_hard_check_report`：移除 `missing_count >= 3 -> C`，有缺失统一判 B（待 LLM 判断关键性）
- `_build_review_prompt`：新增 `hard_results` 参数，把硬检查结果喂给 LLM；评级标准明确"非必采项缺失不影响 A 级"+ 要求与硬检查不一致需说明
- `quality_gate_node` summary 说明"硬检查为客观事实，LLM 复审为最终评级"

### Layer 3: Prompt 层 - 消除假缺失
- `fundamentals_analyst.py:37`：股权质押/减持计划/关联交易从硬要求改为"系统未采集"说明
- `hot_money_tracker.py`：必采清单后加标注规范，龙虎榜未上榜等正常空结果不标 `[数据缺失]`

### 测试
- `tests/test_astock_v0222_fix.py`（7 例）：代理设置/不设、硬检查不判 C、A/F 判级、review prompt 含硬检查、签名校验
- 全量 157 passed（150+7），无回归

---

## 五、部署验证
1. commit + push `feat/aliyun-cloud-deploy`
2. `bash scripts/update-server.sh` 部署（代码挂载，restart 生效）
3. **用户自备代理**后：服务器 `.env` 加 `EM_HTTP_PROXY=<URL>` -> `bash scripts/update-server.sh --env`
4. 验证：容器内 `get_fund_flow("601689","2026-07-15")` 拿到主力净流入；`get_industry_comparison` 不再"获取失败"；重跑 601689 门控自洽（无 C vs A 矛盾）；基本面无 3 处设计性缺失；游资龙虎榜不标缺失

---

## 六、教训
1. **门控多层标准须互通**：硬检查（客观事实）与 LLM 复审（语义判断）不能各自为政，须把硬检查结果喂给 LLM 收口，否则必然矛盾。
2. **机械计数不能替代语义判断**：`[数据缺失]` 数量 ≠ 数据质量，缺失项是否在必采清单/是否关键才是关键，这需 LLM 判断。
3. **prompt 与工具必须匹配**：prompt 要求的数据项必须有对应工具，否则 LLM 只能标缺失（设计性缺失）。
4. **IDC 部署的数据源可用性须在目标环境实测**：本地跑通 ≠ 服务器跑通，东财 push2 对 IDC IP 封禁是典型，须用代理或换源。datacenter/腾讯/新浪等非 push2 源不受影响。
5. **正常空结果 ≠ 数据缺失**："龙虎榜未上榜"是正常业务结果，LLM 不应标缺失，prompt 须明确区分。
