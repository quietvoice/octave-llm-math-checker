"""Optional x402 payment gate for MCP tool calls.

When enabled, paid tools require an x402 PaymentPayload on
``params._meta["x402/payment"]`` (MCP transport spec).

Modes:
  mock  — spec-shaped PaymentRequired / settlement without a chain
          (default when ``--x402`` is passed). Accepts a payload with
          ``{"x402Version": 2, "payload": {"mock": true}}``.
  live  — official ``x402`` SDK + facilitator verify/settle
          (``--x402 --x402-live``). Requires ``pip install "x402[evm]"``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable

from mcp.types import CallToolResult, TextContent

MCP_PAYMENT_META_KEY = "x402/payment"
MCP_PAYMENT_RESPONSE_META_KEY = "x402/payment-response"

# Base Sepolia USDC (x402 default test asset)
DEFAULT_NETWORK = "eip155:84532"
DEFAULT_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
DEFAULT_AMOUNT = "10000"  # $0.01 at 6 decimals
DEFAULT_PRICE = "$0.01"
DEFAULT_PAY_TO = "0x0000000000000000000000000000000000000000"


@dataclass
class X402Settings:
    enabled: bool = False
    mode: str = "mock"  # mock | live
    pay_to: str = DEFAULT_PAY_TO
    network: str = DEFAULT_NETWORK
    asset: str = DEFAULT_USDC
    amount: str = DEFAULT_AMOUNT
    price: str = DEFAULT_PRICE
    facilitator_url: str | None = None
    max_timeout_seconds: int = 60

    @property
    def live(self) -> bool:
        return self.enabled and self.mode == "live"


def settings_from_env_and_args(
    *,
    enabled: bool,
    live: bool = False,
    pay_to: str | None = None,
    network: str | None = None,
    price: str | None = None,
    amount: str | None = None,
    asset: str | None = None,
    facilitator_url: str | None = None,
) -> X402Settings:
    return X402Settings(
        enabled=enabled,
        mode="live" if live else "mock",
        pay_to=pay_to or os.environ.get("X402_PAY_TO") or DEFAULT_PAY_TO,
        network=network or os.environ.get("X402_NETWORK") or DEFAULT_NETWORK,
        asset=asset or os.environ.get("X402_ASSET") or DEFAULT_USDC,
        amount=amount or os.environ.get("X402_AMOUNT") or DEFAULT_AMOUNT,
        price=price or os.environ.get("X402_PRICE") or DEFAULT_PRICE,
        facilitator_url=facilitator_url or os.environ.get("X402_FACILITATOR_URL"),
    )


def accepts_dict(settings: X402Settings) -> dict[str, Any]:
    return {
        "scheme": "exact",
        "network": settings.network,
        "amount": settings.amount,
        "asset": settings.asset,
        "payTo": settings.pay_to,
        "maxTimeoutSeconds": settings.max_timeout_seconds,
        "extra": {"name": "USDC", "version": "2", "price": settings.price},
    }


def resource_info(tool_name: str) -> dict[str, Any]:
    return {
        "url": f"mcp://tool/{tool_name}",
        "description": f"Paid math-check tool: {tool_name}",
        "mimeType": "application/json",
    }


def payment_required_payload(
    settings: X402Settings,
    tool_name: str,
    error: str = "Payment required to access this resource",
) -> dict[str, Any]:
    return {
        "x402Version": 2,
        "error": error,
        "resource": resource_info(tool_name),
        "accepts": [accepts_dict(settings)],
    }


def payment_required_result(
    settings: X402Settings,
    tool_name: str,
    error: str = "Payment required to access this resource",
) -> CallToolResult:
    payload = payment_required_payload(settings, tool_name, error)
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload,
        isError=True,
    )


def extract_payment_from_context(ctx: Any) -> Any:
    """Read ``_meta['x402/payment']`` from a FastMCP Context, if present."""
    if ctx is None:
        return None
    try:
        request_meta = ctx.request_context.meta
    except (ValueError, AttributeError):
        return None
    if request_meta is None:
        return None
    extra = getattr(request_meta, "model_extra", None) or {}
    if MCP_PAYMENT_META_KEY in extra:
        return extra.get(MCP_PAYMENT_META_KEY)
    dumped = request_meta.model_dump(by_alias=True)
    return dumped.get(MCP_PAYMENT_META_KEY)


def is_valid_mock_payment(payment: Any) -> tuple[bool, str]:
    if not isinstance(payment, dict):
        return False, "Payment payload must be an object"
    version = payment.get("x402Version")
    if version not in (1, 2, "1", "2"):
        return False, "Payment payload missing x402Version"
    inner = payment.get("payload")
    if isinstance(inner, dict) and inner.get("mock") is True:
        return True, ""
    if isinstance(inner, dict) and inner.get("signature") and inner.get("authorization"):
        return True, ""
    return False, (
        "mock x402 requires payload.mock=true "
        '(example: {"x402Version": 2, "payload": {"mock": true}})'
    )


def mock_settlement(payment: dict[str, Any], settings: X402Settings) -> dict[str, Any]:
    authorization = {}
    inner = payment.get("payload")
    if isinstance(inner, dict) and isinstance(inner.get("authorization"), dict):
        authorization = inner["authorization"]
    payer = authorization.get("from") or "mock-payer"
    return {
        "success": True,
        "transaction": "0x" + "m" * 64,
        "network": settings.network,
        "payer": payer,
        "mode": "mock",
    }


class PaymentGuard:
    """Gate paid tools. Disabled unless ``settings.enabled``."""

    def __init__(self, settings: X402Settings) -> None:
        self.settings = settings
        self._live_wrapper: Callable[..., Any] | None = None
        if settings.live:
            self._live_wrapper = self._build_live_wrapper()

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def decorate(self, handler: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap a FastMCP tool. Live mode uses the official x402 decorator."""
        if self.settings.live and self._live_wrapper is not None:
            return self._live_wrapper(handler)
        return handler

    def require(self, ctx: Any, tool_name: str) -> CallToolResult | None:
        """If payment is missing/invalid, return a 402-style tool error.

        Returns None when the call may proceed (x402 off, or mock payment ok).
        Live mode is handled by ``decorate`` and should not call this.
        """
        if not self.settings.enabled or self.settings.live:
            return None
        payment = extract_payment_from_context(ctx)
        if not payment:
            return payment_required_result(self.settings, tool_name)
        ok, reason = is_valid_mock_payment(payment)
        if not ok:
            return payment_required_result(self.settings, tool_name, reason)
        return None

    def settlement_meta(self, ctx: Any) -> dict[str, Any] | None:
        if not self.settings.enabled or self.settings.live:
            return None
        payment = extract_payment_from_context(ctx)
        if not isinstance(payment, dict):
            return None
        return {MCP_PAYMENT_RESPONSE_META_KEY: mock_settlement(payment, self.settings)}

    def status_dict(self) -> dict[str, Any]:
        return {
            "x402_enabled": self.settings.enabled,
            "mode": self.settings.mode if self.settings.enabled else "off",
            "network": self.settings.network,
            "price": self.settings.price,
            "amount": self.settings.amount,
            "asset": self.settings.asset,
            "pay_to": self.settings.pay_to,
            "payment_meta_key": MCP_PAYMENT_META_KEY,
        }

    def _build_live_wrapper(self) -> Callable[..., Any]:
        try:
            from x402.http import HTTPFacilitatorClientSync
            from x402.mcp import create_payment_wrapper
            from x402.mechanisms.evm.exact import ExactEvmServerScheme
            from x402.schemas import ResourceConfig
            from x402.server import x402ResourceServerSync
        except ImportError as exc:
            raise SystemExit(
                "Live x402 requires the official SDK. Install with:\n"
                '  pip install "math-check-mcp[x402]"\n'
                f"Import error: {exc}"
            ) from exc

        from x402.http import FacilitatorConfig

        facilitator_config = (
            FacilitatorConfig(url=self.settings.facilitator_url)
            if self.settings.facilitator_url
            else FacilitatorConfig()
        )
        resource_server = x402ResourceServerSync(HTTPFacilitatorClientSync(facilitator_config))
        resource_server.register(self.settings.network, ExactEvmServerScheme())
        resource_server.initialize()
        accepts = resource_server.build_payment_requirements(
            ResourceConfig(
                scheme="exact",
                network=self.settings.network,
                pay_to=self.settings.pay_to,
                price=self.settings.price,
                extra={"name": "USDC", "version": "2"},
            )
        )
        return create_payment_wrapper(resource_server, accepts=accepts)
