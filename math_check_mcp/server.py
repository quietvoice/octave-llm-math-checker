"""Math-check MCP server.

Tools:
  math_check    — judge a claim as RIGHT or WRONG
  math_eval     — evaluate an expression
  math_compare  — compare two values with an operator
  x402_status   — whether the optional x402 paywall is on (always free)

Usage:
  python -m math_check_mcp
  python -m math_check_mcp --x402
  python -m math_check_mcp --x402 --x402-live --x402-pay-to 0x...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, TextContent

from .checker import check_math, compare_values, eval_math
from .x402_gate import PaymentGuard, X402Settings, settings_from_env_and_args

SERVER_NAME = "math-check-mcp"
SERVER_INSTRUCTIONS = (
    "Deterministic math verifier. Call math_check with a claim such as "
    "'9.9 > 9.11' or '2+2=4'. The server returns RIGHT or WRONG using "
    "Decimal/AST evaluation — not another language model."
)


def _ok_result(
    text: str,
    structured: dict[str, Any],
    meta: dict[str, Any] | None = None,
) -> CallToolResult:
    kwargs: dict[str, Any] = {
        "content": [TextContent(type="text", text=text)],
        "structuredContent": structured,
        "isError": False,
    }
    if meta:
        kwargs["_meta"] = meta
    return CallToolResult(**kwargs)


def _err_result(message: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=message)],
        structuredContent={"verdict": "UNKNOWN", "error": message},
        isError=True,
    )


def create_server(guard: PaymentGuard | None = None) -> FastMCP:
    """Build the FastMCP server. ``guard`` is optional (defaults to x402 off)."""
    guard = guard or PaymentGuard(X402Settings(enabled=False))
    mcp = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)

    def _ctx() -> Context | None:
        try:
            return mcp.get_context()
        except Exception:
            return None

    @mcp.tool()
    @guard.decorate
    async def math_check(claim: str, expected: str | None = None) -> CallToolResult:
        """Check a math claim and return RIGHT or WRONG.

        Accepts equations (2+2=4), comparisons (9.9 > 9.11), or English
        phrases (9.9 is greater than 9.11). Optional expected compares the
        evaluated claim to that value.
        """
        ctx = None if guard.settings.live else _ctx()
        blocked = guard.require(ctx, "math_check")
        if blocked is not None:
            return blocked
        result = check_math(claim, expected=expected)
        return _ok_result(
            result.format_display(),
            result.to_dict(),
            guard.settlement_meta(ctx),
        )

    @mcp.tool()
    @guard.decorate
    async def math_eval(expression: str) -> CallToolResult:
        """Evaluate a math expression and return the numeric or boolean result."""
        ctx = None if guard.settings.live else _ctx()
        blocked = guard.require(ctx, "math_eval")
        if blocked is not None:
            return blocked
        try:
            value = eval_math(expression)
        except Exception as exc:
            return _err_result(f"could not evaluate: {exc}")
        from .checker import _fmt, _jsonable

        structured = {
            "expression": expression,
            "value": _jsonable(value),
            "type": type(value).__name__,
        }
        text = f"{_fmt(value)}\n\nexpression: {expression}"
        return _ok_result(text, structured, guard.settlement_meta(ctx))

    @mcp.tool()
    @guard.decorate
    async def math_compare(left: str, right: str, op: str = ">") -> CallToolResult:
        """Compare two expressions (default op is '>'). Returns RIGHT or WRONG."""
        ctx = None if guard.settings.live else _ctx()
        blocked = guard.require(ctx, "math_compare")
        if blocked is not None:
            return blocked
        result = compare_values(left, right, op=op)
        return _ok_result(
            result.format_display(),
            result.to_dict(),
            guard.settlement_meta(ctx),
        )

    @mcp.tool()
    async def x402_status() -> str:
        """Report whether the x402 payment flag is enabled (always free)."""
        return json.dumps(guard.status_dict(), indent=2)

    return mcp


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="math-check-mcp",
        description="MCP server that checks math claims as RIGHT or WRONG",
    )
    parser.add_argument(
        "--x402",
        action="store_true",
        help="Require x402 payment on math tools (mock settlement unless --x402-live)",
    )
    parser.add_argument(
        "--x402-live",
        action="store_true",
        help="Settle via the official x402 facilitator (requires x402 extra + pay-to)",
    )
    parser.add_argument(
        "--x402-pay-to",
        default=os.environ.get("X402_PAY_TO"),
        help="Receiver address (or set X402_PAY_TO)",
    )
    parser.add_argument(
        "--x402-network",
        default=os.environ.get("X402_NETWORK", "eip155:84532"),
        help="CAIP-2 network (default: Base Sepolia eip155:84532)",
    )
    parser.add_argument(
        "--x402-price",
        default=os.environ.get("X402_PRICE", "$0.01"),
        help='Human price string for live mode, e.g. "$0.01"',
    )
    parser.add_argument(
        "--x402-amount",
        default=os.environ.get("X402_AMOUNT", "10000"),
        help="Atomic amount advertised in mock accepts (default 10000 = $0.01 USDC)",
    )
    parser.add_argument(
        "--x402-asset",
        default=os.environ.get("X402_ASSET"),
        help="Token address (default: Base Sepolia USDC)",
    )
    parser.add_argument(
        "--x402-facilitator-url",
        default=os.environ.get("X402_FACILITATOR_URL"),
        help="Facilitator base URL for live mode",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for HTTP transports")
    parser.add_argument("--port", type=int, default=4022, help="Bind port for HTTP transports")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.x402_live and not args.x402:
        print("--x402-live requires --x402", file=sys.stderr)
        raise SystemExit(2)
    if args.x402_live and not args.x402_pay_to:
        print(
            "--x402-live requires --x402-pay-to or X402_PAY_TO (receiver address)",
            file=sys.stderr,
        )
        raise SystemExit(2)

    settings = settings_from_env_and_args(
        enabled=args.x402,
        live=args.x402_live,
        pay_to=args.x402_pay_to,
        network=args.x402_network,
        price=args.x402_price,
        amount=args.x402_amount,
        asset=args.x402_asset,
        facilitator_url=args.x402_facilitator_url,
    )
    guard = PaymentGuard(settings)
    mcp = create_server(guard)

    if args.x402:
        print(
            f"x402 {settings.mode} mode: paid tools require _meta['x402/payment'] "
            f"({settings.price} on {settings.network}, payTo={settings.pay_to})",
            file=sys.stderr,
        )

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
