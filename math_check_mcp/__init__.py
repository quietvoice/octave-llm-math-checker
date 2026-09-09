"""Deterministic math-check MCP server (RIGHT / WRONG)."""

from typing import Any

__all__ = ["CheckResult", "check_math", "compare_values", "eval_math"]
__version__ = "0.1.0"


def __getattr__(name: str) -> Any:
    if name in __all__:
        from . import checker

        return getattr(checker, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
