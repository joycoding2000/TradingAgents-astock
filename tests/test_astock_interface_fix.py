"""回归测试：v0.2.20 接口迁移修复（concept_blocks / insider_transactions）。

- get_concept_blocks: 百度 PAE getrelatedblock(403) -> 东财 F10 CoreConception
- get_insider_transactions: mootdx F10(仅"最新提示") -> 东财 RPT_F10_EH_HOLDERS
"""
import pandas as pd  # noqa: F401  (保持与同目录测试一致的 import 习惯)


class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def test_get_concept_blocks_uses_eastmoney_f10(monkeypatch):
    """concept_blocks: 百度PAE 403 -> 东财 F10 CoreConception ssbk/hxtc。"""
    from tradingagents.dataflows import a_stock

    fake = {
        "ssbk": [
            {"BOARD_NAME": "通信设备", "BOARD_RANK": 2},
            {"BOARD_NAME": "山东板块", "BOARD_RANK": 4},
            {"BOARD_NAME": "CPO概念", "BOARD_RANK": 24},
            {"BOARD_NAME": "算力概念", "BOARD_RANK": 23},
        ],
        "hxtc": [
            {"IS_POINT": "1", "KEY_CLASSIF": "核心竞争力",
             "MAINPOINT_CONTENT": "光模块龙头"},
            {"IS_POINT": "0", "KEY_CLASSIF": "经营范围",
             "MAINPOINT_CONTENT": "should be ignored"},
        ],
    }
    monkeypatch.setattr(a_stock._requests, "get", lambda *a, **k: _FakeResp(fake))

    out = a_stock.get_concept_blocks("300308")
    assert "CPO概念" in out
    assert "算力概念" in out
    assert "Concept tags:" in out
    assert "核心竞争力" in out          # hxtc 核心题材
    assert "光模块龙头" in out
    assert "should be ignored" not in out  # IS_POINT=0 被过滤


def test_get_insider_transactions_uses_eastmoney_holders(monkeypatch):
    """insider: mootdx F10 无股东 -> 东财 RPT_F10_EH_HOLDERS 最新一期十大股东。"""
    from tradingagents.dataflows import a_stock

    fake_data = [
        {"END_DATE": "2026-03-31 00:00:00", "HOLDER_NAME": "控股股东A",
         "HOLD_NUM": 121440135, "HOLD_NUM_RATIO": 10.93,
         "HOLD_NUM_CHANGE": "不变", "IS_HOLDORG": "1"},
        {"END_DATE": "2026-03-31 00:00:00", "HOLDER_NAME": "王伟修",
         "HOLD_NUM": 69731451, "HOLD_NUM_RATIO": 6.28,
         "HOLD_NUM_CHANGE": "不变", "IS_HOLDORG": "0"},
        {"END_DATE": "2025-12-31 00:00:00", "HOLDER_NAME": "旧期股东B",
         "HOLD_NUM": 100, "HOLD_NUM_RATIO": 1,
         "HOLD_NUM_CHANGE": "不变", "IS_HOLDORG": "1"},
    ]
    monkeypatch.setattr(a_stock, "_eastmoney_datacenter",
                        lambda *a, **k: fake_data)
    monkeypatch.setattr(a_stock._requests, "get",
                        lambda *a, **k: _FakeResp({}))

    out = a_stock.get_insider_transactions("300308")
    assert "2026-03-31" in out          # 最新一期
    assert "控股股东A" in out
    assert "王伟修" in out
    assert "个人" in out                # IS_HOLDORG=0 -> 个人
    assert "旧期股东B" not in out       # 旧期被过滤
