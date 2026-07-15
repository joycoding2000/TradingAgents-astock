"""回归测试：v0.2.21 数据质量三修复（股价对齐 / _em_get 重试 / insider 三段）。

- _resolve_price: curr_date 早于今日时用历史收盘价（与技术分析对齐），否则实时价
- _em_get: 连接异常 / 5xx 指数退避重试
- get_insider_transactions: 十大股东 + 股东户数变化(gdrs) + 董监高持股变动(cgbd)
"""
import pandas as pd  # noqa: F401  (保持与同目录测试一致的 import 习惯)


class _FakeResp:
    def __init__(self, payload, status_code=200):
        self._p = payload
        self.status_code = status_code

    def json(self):
        return self._p


# ---------------------------------------------------------------------------
# 修复1：股价对齐 _resolve_price
# ---------------------------------------------------------------------------


def test_resolve_price_uses_historical_close_on_past_date(monkeypatch):
    """curr_date 早于今日 -> 返回该日收盘价（与技术分析基准日对齐）。"""
    from tradingagents.dataflows import a_stock

    monkeypatch.setattr(a_stock, "_get_close_on_date", lambda code, d: 1184.05)
    price, src = a_stock._resolve_price("300308", "2020-01-01", 1169.31)
    assert price == 1184.05
    assert "close on 2020-01-01" in src


def test_resolve_price_uses_realtime_when_no_curr_date(monkeypatch):
    """无 curr_date -> 返回实时价，且不调用历史收盘。"""
    from tradingagents.dataflows import a_stock

    called = {"n": 0}

    def _no_call(code, d):
        called["n"] += 1
        return None

    monkeypatch.setattr(a_stock, "_get_close_on_date", _no_call)
    price, src = a_stock._resolve_price("300308", None, 1169.31)
    assert price == 1169.31
    assert src == "realtime"
    assert called["n"] == 0


def test_resolve_price_falls_back_to_realtime_when_close_missing(monkeypatch):
    """curr_date 给定但历史收盘取不到 -> 回退实时价。"""
    from tradingagents.dataflows import a_stock

    monkeypatch.setattr(a_stock, "_get_close_on_date", lambda code, d: None)
    price, src = a_stock._resolve_price("300308", "2020-01-01", 1169.31)
    assert price == 1169.31
    assert src == "realtime"


# ---------------------------------------------------------------------------
# 修复2：_em_get 偶发重试
# ---------------------------------------------------------------------------


def test_em_get_retries_on_connection_error(monkeypatch):
    """_em_get: 连接异常时重试，最终成功返回。"""
    from tradingagents.dataflows import a_stock

    monkeypatch.setattr(a_stock.time, "sleep", lambda *a, **k: None)
    calls = {"n": 0}

    def _flaky_get(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise a_stock._requests.exceptions.ConnectionError("boom")
        return _FakeResp({"ok": True})

    monkeypatch.setattr(a_stock._EM_SESSION, "get", _flaky_get)
    resp = a_stock._em_get("http://x", retries=3)
    assert resp.json() == {"ok": True}
    assert calls["n"] == 3


def test_em_get_retries_on_5xx(monkeypatch):
    """_em_get: 5xx 响应时重试，最终 200 返回。"""
    from tradingagents.dataflows import a_stock

    monkeypatch.setattr(a_stock.time, "sleep", lambda *a, **k: None)
    calls = {"n": 0}

    def _flaky_get(*a, **k):
        calls["n"] += 1
        if calls["n"] < 2:
            return _FakeResp({}, status_code=503)
        return _FakeResp({"ok": True}, status_code=200)

    monkeypatch.setattr(a_stock._EM_SESSION, "get", _flaky_get)
    resp = a_stock._em_get("http://x", retries=3)
    assert resp.json() == {"ok": True}
    assert calls["n"] == 2


def test_em_get_does_not_retry_on_4xx(monkeypatch):
    """_em_get: 4xx 直接返回，不重试（接口本身问题交给调用方）。"""
    from tradingagents.dataflows import a_stock

    monkeypatch.setattr(a_stock.time, "sleep", lambda *a, **k: None)
    calls = {"n": 0}

    def _once(*a, **k):
        calls["n"] += 1
        return _FakeResp({}, status_code=404)

    monkeypatch.setattr(a_stock._EM_SESSION, "get", _once)
    resp = a_stock._em_get("http://x", retries=3)
    assert resp.status_code == 404
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# 修复3：get_insider_transactions 三段齐全
# ---------------------------------------------------------------------------


def test_get_insider_transactions_three_sections(monkeypatch):
    """insider: 十大股东 + 股东户数变化 + 董监高持股变动 三段齐全。"""
    from tradingagents.dataflows import a_stock

    holders = [
        {"END_DATE": "2026-03-31 00:00:00", "HOLDER_NAME": "控股股东A",
         "HOLD_NUM": 121440135, "HOLD_NUM_RATIO": 10.93,
         "HOLD_NUM_CHANGE": "不变", "IS_HOLDORG": "1"},
    ]
    monkeypatch.setattr(a_stock, "_eastmoney_datacenter",
                        lambda *a, **k: holders)

    def _fake_get(url, *a, **k):
        if "ShareholderResearch" in url:
            return _FakeResp({"gdrs": [
                {"END_DATE": "2026-03-31 00:00:00", "HOLDER_TOTAL_NUM": 154418,
                 "TOTAL_NUM_RATIO": -15.78, "AVG_FREE_SHARES": 7159,
                 "HOLD_FOCUS": "非常分散"},
            ]})
        if "CompanyManagement" in url:
            return _FakeResp({"cgbd": [
                {"END_DATE": "2025-11-24 00:00:00", "EXECUTIVE_NAME": "刘洋",
                 "POSITION": "董事,高管", "CHANGE_NUM": -40000,
                 "AVERAGE_PRICE": 451.22, "CHANGE_AFTER_HOLDNUM": 2167600,
                 "TRADE_WAY": "竞价卖出"},
            ]})
        return _FakeResp({})

    monkeypatch.setattr(a_stock._requests, "get", _fake_get)

    out = a_stock.get_insider_transactions("300308")
    assert "十大股东" in out
    assert "控股股东A" in out
    assert "股东户数变化" in out
    assert "154418" in out
    assert "非常分散" in out
    assert "董监高持股变动" in out
    assert "刘洋" in out
    assert "竞价卖出" in out


def test_get_insider_transactions_holders_only_when_pages_empty(monkeypatch):
    """insider: gdrs/cgbd 返回空时，仅十大股东段也能正常输出。"""
    from tradingagents.dataflows import a_stock

    holders = [
        {"END_DATE": "2026-03-31 00:00:00", "HOLDER_NAME": "控股股东A",
         "HOLD_NUM": 100, "HOLD_NUM_RATIO": 5.0,
         "HOLD_NUM_CHANGE": "不变", "IS_HOLDORG": "1"},
    ]
    monkeypatch.setattr(a_stock, "_eastmoney_datacenter",
                        lambda *a, **k: holders)
    monkeypatch.setattr(a_stock._requests, "get",
                        lambda *a, **k: _FakeResp({}))

    out = a_stock.get_insider_transactions("300308")
    assert "十大股东" in out
    assert "控股股东A" in out
    assert "股东户数变化" not in out
    assert "董监高持股变动" not in out
