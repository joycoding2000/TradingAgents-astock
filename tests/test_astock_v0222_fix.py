"""东财代理 + 门控矛盾修正 + prompt 假缺失回归测试。

覆盖：
1. 静态和巨量 IP 动态代理正确设置 _EM_SESSION.proxies
2. _hard_check_report 不再因 [数据缺失] 数量 >=3 判 C（改为 B，待 LLM 判断）
3. _build_review_prompt 把硬检查结果喂给 LLM（prompt 含硬检查段 + 必采关键判断指引）
"""
import importlib


class _ProxyResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_em_http_proxy_sets_session_proxies(monkeypatch):
    """设了 EM_HTTP_PROXY 时 _EM_SESSION.proxies 正确设置。"""
    from tradingagents.dataflows import a_stock

    monkeypatch.setenv("EM_HTTP_PROXY", "http://proxy.example.com:8080")
    importlib.reload(a_stock)
    try:
        assert a_stock._EM_SESSION.proxies.get("http") == "http://proxy.example.com:8080"
        assert a_stock._EM_SESSION.proxies.get("https") == "http://proxy.example.com:8080"
    finally:
        monkeypatch.delenv("EM_HTTP_PROXY", raising=False)
        importlib.reload(a_stock)


def test_em_http_proxy_unset_means_no_proxy(monkeypatch):
    """不设 EM_HTTP_PROXY 时 _EM_SESSION.proxies 为空（本地开发直连）。"""
    from tradingagents.dataflows import a_stock

    monkeypatch.delenv("EM_HTTP_PROXY", raising=False)
    importlib.reload(a_stock)
    try:
        assert not a_stock._EM_SESSION.proxies
    finally:
        importlib.reload(a_stock)


def test_juliangip_dynamic_proxy_is_fetched_and_cached(monkeypatch):
    """未设静态代理时，巨量 IP 代理首次请求获取，后续请求复用。"""
    from tradingagents.dataflows import a_stock

    monkeypatch.delenv("EM_HTTP_PROXY", raising=False)
    monkeypatch.setenv("JULIANGIP_API_URL", "http://proxy-api.invalid/signed")
    importlib.reload(a_stock)
    calls = {"count": 0}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        return _ProxyResponse({"code": 200, "data": {"proxy_list": ["1.2.3.4:8080"]}})

    monkeypatch.setattr(a_stock._requests, "get", fake_get)
    try:
        assert a_stock._refresh_em_dynamic_proxy() is True
        assert a_stock._refresh_em_dynamic_proxy() is True
        assert calls["count"] == 1
        assert a_stock._EM_SESSION.proxies == {
            "http": "http://1.2.3.4:8080",
            "https": "http://1.2.3.4:8080",
        }
    finally:
        monkeypatch.delenv("JULIANGIP_API_URL", raising=False)
        importlib.reload(a_stock)


def test_static_proxy_takes_priority_over_juliangip(monkeypatch):
    """配置静态 EM_HTTP_PROXY 时，绝不请求或覆盖动态代理。"""
    from tradingagents.dataflows import a_stock

    monkeypatch.setenv("EM_HTTP_PROXY", "http://fixed.example.com:8080")
    monkeypatch.setenv("JULIANGIP_API_URL", "http://proxy-api.invalid/signed")
    importlib.reload(a_stock)
    try:
        assert a_stock._refresh_em_dynamic_proxy() is True
        assert a_stock._EM_SESSION.proxies["http"] == "http://fixed.example.com:8080"
    finally:
        monkeypatch.delenv("EM_HTTP_PROXY", raising=False)
        monkeypatch.delenv("JULIANGIP_API_URL", raising=False)
        importlib.reload(a_stock)


def test_juliangip_rejects_invalid_proxy_response():
    """错误页或异常字段不能进入 requests 代理配置。"""
    import pytest
    from tradingagents.dataflows import a_stock

    with pytest.raises(ValueError, match="合法 IPv4"):
        a_stock._parse_juliangip_proxy({"code": 200, "data": {"proxy_list": ["bad"]}})


def test_em_get_refuses_direct_connection_when_dynamic_proxy_is_unavailable(monkeypatch):
    """配置动态代理后取代理失败，不能绕回 IDC 直连。"""
    import pytest
    from tradingagents.dataflows import a_stock

    monkeypatch.delenv("EM_HTTP_PROXY", raising=False)
    monkeypatch.setenv("JULIANGIP_API_URL", "http://proxy-api.invalid/signed")
    importlib.reload(a_stock)
    called = {"session": False}

    monkeypatch.setattr(a_stock, "_refresh_em_dynamic_proxy", lambda: False)
    monkeypatch.setattr(
        a_stock._EM_SESSION,
        "get",
        lambda *args, **kwargs: called.__setitem__("session", True),
    )
    try:
        with pytest.raises(a_stock._requests.exceptions.ProxyError):
            a_stock._em_get("https://push2.eastmoney.com/api/qt/stock/get")
        assert called["session"] is False
    finally:
        monkeypatch.delenv("JULIANGIP_API_URL", raising=False)
        importlib.reload(a_stock)


def test_hard_check_no_longer_c_for_3_missing():
    """3 处 [数据缺失] + 有表格 + 够长 -> B（非 C），交给 LLM 判断关键性。"""
    from tradingagents.agents.quality_gate import _hard_check_report

    body = "| 指标 | 值 |\n|---|---|\n| PE | 30 |\n" + "充足分析内容 " * 30
    report = body + "\n[数据缺失: 股权质押] [数据缺失: 减持计划] [数据缺失: 关联交易]"
    grade, detail = _hard_check_report("fundamentals", report)
    assert grade == "B", f"3 处非必采缺失应判 B（待 LLM 判断），实际 {grade}"
    assert "3 处数据缺失" in detail


def test_hard_check_a_when_complete():
    """无缺失 + 有表格 + 够长 -> A。"""
    from tradingagents.agents.quality_gate import _hard_check_report

    report = "| 指标 | 值 |\n|---|---|\n| PE | 30 |\n" + "充足分析内容 " * 30
    grade, _ = _hard_check_report("fundamentals", report)
    assert grade == "A"


def test_hard_check_f_when_empty():
    """空报告 -> F。"""
    from tradingagents.agents.quality_gate import _hard_check_report

    grade, detail = _hard_check_report("fundamentals", "")
    assert grade == "F"
    assert "空" in detail


def test_review_prompt_includes_hard_results():
    """_build_review_prompt 把硬检查结果喂给 LLM。"""
    from tradingagents.agents.quality_gate import (
        _build_review_prompt,
        REPORT_FIELDS,
    )

    reports = {field: "示例报告内容 " * 30 for field in REPORT_FIELDS.values()}
    hard_results = {k: ("B", "3 处数据缺失（关键性待 LLM 判断）") for k in REPORT_FIELDS}
    prompt = _build_review_prompt(reports, hard_results, "2026-07-15", "601689")

    assert "硬检查结果" in prompt
    assert "基本面分析师" in prompt
    assert "[B]" in prompt
    assert "必采关键" in prompt  # 评级标准强调必采关键项判断
    assert "601689" in prompt
    assert "2026-07-15" in prompt


def test_review_prompt_arity_hard_results_required():
    """_build_review_prompt 签名要求 hard_results（v0.2.22 新增参数）。"""
    import inspect
    from tradingagents.agents.quality_gate import _build_review_prompt

    sig = inspect.signature(_build_review_prompt)
    assert "hard_results" in sig.parameters
