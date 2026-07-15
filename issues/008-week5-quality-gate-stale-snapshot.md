# Issue #8: Week 5 "14/14 OK" 是过时快照--数据层 5 次变更未复跑回归

- **日期**: 2026-07-15
- **状态**: ✅ 已查明根因（v0.2.19/v0.2.20 修复的 5 个 bug 全部在 Week 5 之后引入）
- **类型**: 测试过程缺陷（非单一代码 bug）

## 问题

`DEV_LOG.md` 的 "Week 5 - 数据质量门控实测(2026-05-12)" 记录 "14/14 接口全部 OK"，但 2026-07-15 实跑 300308 中际旭创却暴露 v0.2.19/v0.2.20 共 5 个数据缺失 bug。一份"全部通过"的回归记录解释不了两个月后的全面缺失。

## 根因：Week 5 测的是旧实现快照，之后 5 次变更未复跑

### 铁证：test_data_quality.py 是一次性快照

| 证据 | 值 | 含义 |
|------|----|------|
| `test_data_quality.py` 最后修改 | `2026-05-13`（commit `c567f8a`，v0.2.4） | Week 5 时期，akshare 版 |
| v0.2.5 移除 akshare 重写 | `2026-05-17`（`f3c0fe4`） | 重写在测试之后 4 天 |
| 该文件后续 commit | **仅 `c567f8a` 一条** | 重写后再未更新/运行 |

Week 5 实测时 `_get_financial_report_sina` 的实现是 `import akshare as ak; ak.stock_financial_report_sina(...)`（akshare 库内部解析）。5 天后 v0.2.5 移除 akshare、改自写解析，key 写错（`lrb` vs `report_list`），三表恒空--但 `test_data_quality.py` 自此再未运行，bug 潜伏 2 个月。

### 5 个 bug 的引入时点（全部在 Week 5 之后）

| bug | 修复版本 | 引入时点 | 证据 |
|-----|---------|---------|------|
| 新浪三表 key 错（`lrb` vs `report_list`） | v0.2.19 | v0.2.5（05-17）移除 akshare 重写 | Week5 用 `ak.stock_financial_report_sina()`（akshare 解析正确）；v0.2.5 自写解析 key 错 |
| 同花顺 read_html 崩溃 | v0.2.19 | v0.2.5 自接同花顺 + pandas 升 3.0 | `pd.read_html(裸串)` pandas 2.x 正常、3.0 崩；Week5 时 pandas 2.x |
| mootdx field_map 英文名 | v0.2.19 | 早期就有，被弱判定掩盖 | Week5 判定只看 `length>50`，腾讯 PE/PB 够长即判 OK，mootdx 字段空未暴露 |
| 概念板块 403（百度 PAE `getrelatedblock`） | v0.2.20 | 百度 PAE 05-19 下线 + v0.2.7 漏修 | Week5（05-12）PAE 还在；v0.2.7 只修 `get_fund_flow` 资金流，漏修同源概念板块端点 |
| mootdx F10 股东研究失效 | v0.2.20 | v0.2.15（06-20）mootdx 0.11.x 适配 | Week5 用旧 mootdx，`F10(name="股东研究")` 返回 19969 chars；0.11.x 后栏目目录只剩"最新提示" |

## 四层根因

1. **版本错位（主因）**：Week 5 测 akshare 版，v0.2.5 移除 akshare 重写后**从未复跑** `test_data_quality.py`。新浪三表 key、同花顺 read_html 都是重写时新写的代码，从未被 Week 5 测试覆盖。
2. **外部接口下线 + 漏修**：百度 PAE 05-19 下线，v0.2.7 修了资金流**漏修概念板块**（同源端点），CLAUDE.md 记录不全，概念板块 403 潜伏 2 个月。
3. **依赖升级引入回归 + 适配漏测**：mootdx 0.10.x->0.11.x（v0.2.15）改变 F10 行为；v0.2.15 重点修 `_get_mootdx_client` 防崩，没测 `get_insider_transactions` 的 F10 取数，股东研究静默失效。
4. **测试判定太弱**：`test_data_quality.py` 的 OK 判定是 `length > 50`，不检查字段完整性、关键值非空、数据新鲜度。"14/14 OK"≠数据完整，只代表"没崩 + 够长"。

## 教训

- **回归测试必须在每次数据层变更后复跑**：v0.2.5（移除 akshare）、v0.2.7（替换失效接口）、v0.2.15（mootdx 0.11.x 适配）三次重大变更都未复跑 `test_data_quality.py`，等于"测一次贴合格标签，之后改了 5 次没复检"。
- **判定要看字段不看长度**：`length > 50` 掩盖了字段级静默缺失（mootdx 拼音字段取不到、新浪三表空、field_map 英文名）。应检查关键字段非空 + 数据新鲜度。
- **接口下线要全量排查同源端点**：百度 PAE 资金流下线时，应顺带排查同源的概念板块端点，而非只修报错的那个。
- **依赖升级要回归该依赖相关的所有接口**：mootdx 0.11.x 升级影响 F10，应回归 `get_insider_transactions` 而非只测 `_get_mootdx_client` 连通性。
- **CLAUDE.md 的"已修复"条目要写清边界**：v0.2.7 只记"资金流下线已修复"，没提概念板块端点同源风险，导致后来者误以为百度 PAE 全部处理完毕。

## 改进措施

- `test_data_quality.py` 纳入 `pytest tests/` 或 CI，每次数据层 PR 必跑（标 `@pytest.mark.network`，需联网）。
- 判定从 `length > 50` 升级为：关键字段非空检查（如 `get_fundamentals` 必须含 `Price`/`PE`/`净利润`；`get_balance_sheet` 必须含至少一行数据行）。
- v0.2.19/v0.2.20 已补 `tests/test_astock_fundamentals_fix.py` + `tests/test_astock_interface_fix.py` 共 7 例字段级回归（mock 网络），确保重写逻辑不再静默退化为空。

## 一句话总结

> Week 5 的"14/14 OK"测的是 akshare + 旧 mootdx + pandas 2.x 的旧实现快照；之后 v0.2.5 移除 akshare 重写（引入新浪 key bug + read_html）、v0.2.7 漏修概念板块、pandas 升 3.0、v0.2.15 升级 mootdx 0.11.x（破坏 F10）共 4 次变更改变了数据层，而回归测试自 2026-05-13 后再未运行，加上判定只看长度不看字段--5 个 bug 就这样潜伏 2 个月直到今天。
