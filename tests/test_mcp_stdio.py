"""End-to-end MCP stdio tests against the real server process."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client

ROOT = Path(__file__).resolve().parents[1]


def _server_params(*extra_args: str) -> StdioServerParameters:
    env = get_default_environment()
    env["PYTHONPATH"] = str(ROOT) + (
        (":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else ""
    )
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "math_check_mcp", *extra_args],
        env=env,
        cwd=str(ROOT),
    )


def _text(result) -> str:
    return "".join(block.text for block in result.content if getattr(block, "text", None))


@pytest.mark.asyncio
async def test_stdio_math_check_right_and_wrong():
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            assert {"math_check", "math_eval", "math_compare", "x402_status"} <= tools

            right = await session.call_tool("math_check", {"claim": "9.9 > 9.11"})
            assert not right.isError
            assert right.structuredContent["verdict"] == "RIGHT"
            assert _text(right).startswith("RIGHT")

            wrong = await session.call_tool("math_check", {"claim": "9.11 > 9.9"})
            assert not wrong.isError
            assert wrong.structuredContent["verdict"] == "WRONG"
            assert _text(wrong).startswith("WRONG")

            eq = await session.call_tool("math_check", {"claim": "2+2=4"})
            assert eq.structuredContent["verdict"] == "RIGHT"

            ev = await session.call_tool("math_eval", {"expression": "3*7"})
            assert ev.structuredContent["value"] == "21"

            cmp_ = await session.call_tool(
                "math_compare", {"left": "9.9", "right": "9.11", "op": ">"}
            )
            assert cmp_.structuredContent["verdict"] == "RIGHT"


@pytest.mark.asyncio
async def test_stdio_x402_flag_requires_then_accepts_mock_payment():
    async with stdio_client(_server_params("--x402")) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            status = await session.call_tool("x402_status", {})
            status_body = json.loads(_text(status))
            assert status_body["x402_enabled"] is True
            assert status_body["mode"] == "mock"

            unpaid = await session.call_tool("math_check", {"claim": "1+1=2"})
            assert unpaid.isError
            assert unpaid.structuredContent["x402Version"] == 2
            assert unpaid.structuredContent["accepts"][0]["scheme"] == "exact"

            paid = await session.call_tool(
                "math_check",
                {"claim": "1+1=2"},
                meta={
                    "x402/payment": {
                        "x402Version": 2,
                        "payload": {"mock": True},
                    }
                },
            )
            assert not paid.isError
            assert paid.structuredContent["verdict"] == "RIGHT"
            assert _text(paid).startswith("RIGHT")
            assert paid.meta["x402/payment-response"]["success"] is True
