from types import SimpleNamespace

from math_check_mcp.x402_gate import (
    MCP_PAYMENT_META_KEY,
    PaymentGuard,
    X402Settings,
    extract_payment_from_context,
    is_valid_mock_payment,
    payment_required_payload,
    payment_required_result,
    settings_from_env_and_args,
)


class _Meta:
    def __init__(self, extra):
        self.model_extra = extra

    def model_dump(self, by_alias=True):
        return dict(self.model_extra)


def _ctx(payment=None):
    extra = {}
    if payment is not None:
        extra[MCP_PAYMENT_META_KEY] = payment
    meta = _Meta(extra)
    return SimpleNamespace(request_context=SimpleNamespace(meta=meta))


def test_extract_payment():
    payload = {"x402Version": 2, "payload": {"mock": True}}
    assert extract_payment_from_context(_ctx(payload)) == payload
    assert extract_payment_from_context(_ctx()) is None
    assert extract_payment_from_context(None) is None


def test_mock_payment_validation():
    ok, _ = is_valid_mock_payment({"x402Version": 2, "payload": {"mock": True}})
    assert ok
    ok, reason = is_valid_mock_payment({"x402Version": 2})
    assert not ok
    assert "mock" in reason
    ok, _ = is_valid_mock_payment("nope")
    assert not ok


def test_guard_disabled_allows():
    guard = PaymentGuard(X402Settings(enabled=False))
    assert guard.require(_ctx(), "math_check") is None


def test_guard_requires_payment():
    guard = PaymentGuard(X402Settings(enabled=True, mode="mock"))
    result = guard.require(_ctx(), "math_check")
    assert result is not None
    assert result.isError
    body = result.structuredContent
    assert body["x402Version"] == 2
    assert body["accepts"][0]["scheme"] == "exact"
    assert "math_check" in body["resource"]["url"]


def test_guard_accepts_mock_payload():
    guard = PaymentGuard(X402Settings(enabled=True, mode="mock"))
    payment = {"x402Version": 2, "payload": {"mock": True}}
    assert guard.require(_ctx(payment), "math_check") is None
    meta = guard.settlement_meta(_ctx(payment))
    assert meta["x402/payment-response"]["success"] is True
    assert meta["x402/payment-response"]["mode"] == "mock"


def test_guard_rejects_garbage_payment():
    guard = PaymentGuard(X402Settings(enabled=True, mode="mock"))
    result = guard.require(_ctx({"hello": "world"}), "math_eval")
    assert result is not None
    assert result.isError
    assert "x402Version" in result.structuredContent["error"] or "x402Version" in result.content[0].text


def test_payment_required_json_roundtrip():
    settings = X402Settings(enabled=True)
    payload = payment_required_payload(settings, "math_check")
    result = payment_required_result(settings, "math_check")
    assert result.structuredContent == payload
    assert result.content[0].text


def test_settings_from_args():
    settings = settings_from_env_and_args(
        enabled=True,
        live=False,
        pay_to="0xabc",
        price="$0.05",
    )
    assert settings.enabled
    assert settings.mode == "mock"
    assert settings.pay_to == "0xabc"
    assert settings.price == "$0.05"
