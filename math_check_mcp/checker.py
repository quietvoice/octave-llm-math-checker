"""Deterministic math claim checker.

Evaluates comparisons and equations with a sandboxed AST walker. Numeric
literals are parsed as Decimal from source text so traps like 9.9 vs 9.11
are judged correctly (9.9 is greater). An LLM is never used as the judge.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

MAX_EXPR_LEN = 2000
MAX_AST_NODES = 250
DECIMAL_PREC = 50
FLOAT_REL_TOL = 1e-12
FLOAT_ABS_TOL = 1e-15

_FULLWIDTH_DIGITS = str.maketrans(
    {
        "０": "0",
        "１": "1",
        "２": "2",
        "３": "3",
        "４": "4",
        "５": "5",
        "６": "6",
        "７": "7",
        "８": "8",
        "９": "9",
        "．": ".",
        "－": "-",
        "＋": "+",
        "＝": "=",
        "＊": "*",
        "／": "/",
        "（": "(",
        "）": ")",
    }
)

_PHRASE_OPS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"^\s*(.+?)\s+is\s+greater\s+than\s+or\s+equal\s+to\s+(.+?)\s*$", re.I),
        ">=",
    ),
    (
        re.compile(r"^\s*(.+?)\s+is\s+less\s+than\s+or\s+equal\s+to\s+(.+?)\s*$", re.I),
        "<=",
    ),
    (re.compile(r"^\s*(.+?)\s+is\s+greater\s+than\s+(.+?)\s*$", re.I), ">"),
    (re.compile(r"^\s*(.+?)\s+is\s+less\s+than\s+(.+?)\s*$", re.I), "<"),
    (re.compile(r"^\s*(.+?)\s+is\s+not\s+equal\s+to\s+(.+?)\s*$", re.I), "!="),
    (re.compile(r"^\s*(.+?)\s+is\s+equal\s+to\s+(.+?)\s*$", re.I), "=="),
    (re.compile(r"^\s*(.+?)\s+equals\s+(.+?)\s*$", re.I), "=="),
    (re.compile(r"^\s*(.+?)\s+is\s+not\s+(.+?)\s*$", re.I), "!="),
]

_BIN_OPS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_CMP_OPS: dict[type[ast.cmpop], Any] = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

_MATH_FUNCS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "pow": pow,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": math.factorial,
    "degrees": math.degrees,
    "radians": math.radians,
    "hypot": math.hypot,
}

_CONSTS: dict[str, Any] = {
    "pi": Decimal(str(math.pi)),
    "e": Decimal(str(math.e)),
    "tau": Decimal(str(math.tau)),
    "true": True,
    "false": False,
    "True": True,
    "False": False,
}

_KEEP_DECIMAL_FUNCS = {"abs", "round", "min", "max", "pow"}


@dataclass(frozen=True)
class CheckResult:
    """Structured verdict for a math claim or expression."""

    verdict: str
    display: str
    claim: str
    normalized: str
    value: Any
    detail: str
    engine: str = "decimal-ast"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["value"] = _jsonable(self.value)
        return data

    def format_display(self) -> str:
        return (
            f"{self.verdict}\n"
            f"\n"
            f"claim: {self.claim}\n"
            f"normalized: {self.normalized}\n"
            f"{self.detail}\n"
            f"engine: {self.engine}"
        )


def check_math(claim: str, expected: str | None = None) -> CheckResult:
    """Judge a math claim as RIGHT, WRONG, or UNKNOWN.

    Accepts equations (``2+2=4``), comparisons (``9.9 > 9.11``), English
    phrases (``9.9 is greater than 9.11``), or an expression plus ``expected``.
    """
    if claim is None or not str(claim).strip():
        return CheckResult(
            verdict="UNKNOWN",
            display="UNKNOWN",
            claim="" if claim is None else str(claim),
            normalized="",
            value=None,
            detail="empty input",
        )

    raw = str(claim)
    try:
        normalized = normalize_claim(raw)
        value = eval_math(normalized)
    except Exception as exc:
        return CheckResult(
            verdict="UNKNOWN",
            display="UNKNOWN",
            claim=raw,
            normalized="",
            value=None,
            detail=f"could not evaluate: {exc}",
        )

    if expected is not None and str(expected).strip() != "":
        try:
            expected_value = eval_math(normalize_claim(str(expected)))
        except Exception as exc:
            return CheckResult(
                verdict="UNKNOWN",
                display="UNKNOWN",
                claim=raw,
                normalized=normalized,
                value=value,
                detail=f"could not evaluate expected: {exc}",
            )
        ok = _values_equal(value, expected_value)
        verdict = "RIGHT" if ok else "WRONG"
        return CheckResult(
            verdict=verdict,
            display=verdict,
            claim=raw,
            normalized=f"{normalized} == {expected}",
            value=ok,
            detail=(
                f"expression={_fmt(value)}; expected={_fmt(expected_value)}; "
                f"match={ok}"
            ),
        )

    if isinstance(value, bool):
        verdict = "RIGHT" if value else "WRONG"
        return CheckResult(
            verdict=verdict,
            display=verdict,
            claim=raw,
            normalized=normalized,
            value=value,
            detail=f"evaluated to {value}",
        )

    return CheckResult(
        verdict="UNKNOWN",
        display="UNKNOWN",
        claim=raw,
        normalized=normalized,
        value=value,
        detail=(
            f"evaluated to {_fmt(value)} (not a true/false claim; "
            "pass an equation, comparison, or expected=)"
        ),
    )


def compare_values(left: str, right: str, op: str = ">") -> CheckResult:
    """Compare two expressions with ``op`` and return RIGHT/WRONG."""
    op = op.strip()
    allowed = {">", "<", ">=", "<=", "==", "!=", "="}
    if op not in allowed:
        return CheckResult(
            verdict="UNKNOWN",
            display="UNKNOWN",
            claim=f"{left} {op} {right}",
            normalized="",
            value=None,
            detail=f"unsupported comparison operator: {op!r}",
        )
    if op == "=":
        op = "=="
    return check_math(f"({left}) {op} ({right})")


def eval_math(expression: str) -> Any:
    """Evaluate a sanitized math expression. Returns Decimal, bool, or float."""
    src = _prepare_expression(expression)
    if len(src) > MAX_EXPR_LEN:
        raise ValueError(f"expression longer than {MAX_EXPR_LEN} characters")
    tree = ast.parse(src, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
        raise ValueError("expression is too complex")
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PREC
        return _SafeEval(src).visit(tree)


def normalize_claim(text: str) -> str:
    """Normalize locale digits and English comparison phrases to an expression."""
    s = str(text).strip().translate(_FULLWIDTH_DIGITS)
    s = (
        s.replace("×", "*")
        .replace("÷", "/")
        .replace("−", "-")
        .replace("≦", "<=")
        .replace("≧", ">=")
        .replace("≠", "!=")
        .replace("≤", "<=")
        .replace("≥", ">=")
    )
    s = _maybe_european_decimal(s)
    for pattern, op in _PHRASE_OPS:
        match = pattern.match(s)
        if match:
            return f"({match.group(1)}) {op} ({match.group(2)})"
    return s


def _prepare_expression(expression: str) -> str:
    s = normalize_claim(expression)
    s = s.replace("^", "**")
    s = _rewrite_bare_equals(s)
    return s


def _rewrite_bare_equals(s: str) -> str:
    """Turn assignment-style ``=`` into ``==`` without touching ``<=``, ``!=``, etc."""
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        nxt = s[i + 1] if i + 1 < n else ""
        if ch in "<>=!" and nxt == "=":
            out.append(ch)
            out.append("=")
            i += 2
            continue
        if ch == "=":
            out.append("==")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _maybe_european_decimal(s: str) -> str:
    """If the text uses comma decimals and no period, treat comma as decimal."""
    if "." in s or "," not in s:
        return s
    if re.search(r"\d,\d", s) and not re.search(r",\s", s):
        return s.replace(",", ".")
    return s


class _SafeEval(ast.NodeVisitor):
    def __init__(self, source: str) -> None:
        self.source = source

    def visit(self, node: ast.AST) -> Any:  # type: ignore[override]
        method = getattr(self, "visit_" + type(node).__name__, None)
        if method is None:
            raise ValueError(f"disallowed syntax: {type(node).__name__}")
        return method(node)

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, bool) or node.value is None:
            return node.value
        if isinstance(node.value, (int, float)):
            segment = ast.get_source_segment(self.source, node)
            if segment:
                try:
                    return Decimal(segment.replace("_", ""))
                except InvalidOperation:
                    pass
            return Decimal(str(node.value))
        raise ValueError(f"disallowed literal: {node.value!r}")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.Not):
            return not bool(operand)
        raise ValueError("disallowed unary operator")

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError("disallowed operator")
        left = self.visit(node.left)
        right = self.visit(node.right)
        if type(node.op) is ast.Pow:
            try:
                return left**right
            except (InvalidOperation, OverflowError, ValueError):
                return float(left) ** float(right)
        if type(node.op) is ast.Div and right == 0:
            raise ZeroDivisionError("division by zero")
        return op(left, right)

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for op_node, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            op_type = type(op_node)
            if op_type in (ast.Eq, ast.NotEq):
                equal = _values_equal(left, right)
                ok = equal if op_type is ast.Eq else not equal
            else:
                fn = _CMP_OPS.get(op_type)
                if fn is None:
                    raise ValueError("disallowed comparison")
                ok = bool(fn(left, right))
            if not ok:
                return False
            left = right
        return True

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        if isinstance(node.op, ast.And):
            result = True
            for value in node.values:
                result = result and bool(self.visit(value))
            return result
        if isinstance(node.op, ast.Or):
            result = False
            for value in node.values:
                result = result or bool(self.visit(value))
            return result
        raise ValueError("disallowed boolean operator")

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name) or node.keywords:
            raise ValueError("only simple function calls are allowed")
        name = node.func.id
        func = _MATH_FUNCS.get(name)
        if func is None:
            raise ValueError(f"function not allowed: {name}")
        args = [self.visit(arg) for arg in node.args]
        if name not in _KEEP_DECIMAL_FUNCS:
            args = [_to_float(a) for a in args]
        elif name == "pow" and len(args) >= 2:
            try:
                return args[0] ** args[1]
            except (InvalidOperation, OverflowError, ValueError):
                args = [_to_float(a) for a in args]
        result = func(*args)
        if isinstance(result, (int, float)) and not isinstance(result, bool):
            try:
                return Decimal(str(result))
            except InvalidOperation:
                return result
        return result

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ValueError(f"name not allowed: {node.id}")

    def visit_Tuple(self, node: ast.Tuple) -> Any:
        return tuple(self.visit(elt) for elt in node.elts)


def _to_float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool):
        return float(value)
    return float(value)


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) and isinstance(right, bool):
        return left is right
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    if isinstance(left, Decimal) and isinstance(right, Decimal):
        return left == right
    try:
        return math.isclose(
            float(left), float(right), rel_tol=FLOAT_REL_TOL, abs_tol=FLOAT_ABS_TOL
        )
    except (TypeError, ValueError, OverflowError):
        return left == right


def _fmt(value: Any) -> str:
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _fmt(value)
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    return value


def main() -> None:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Check a math claim as RIGHT or WRONG")
    parser.add_argument("claim", help='Claim to check, e.g. "9.9 > 9.11" or "2+2=4"')
    parser.add_argument("--expected", default=None, help="Optional expected value")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
    args = parser.parse_args()
    result = check_math(args.claim, expected=args.expected)
    if args.json:
        json.dump(result.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(result.format_display() + "\n")
    if result.verdict == "WRONG":
        raise SystemExit(2)
    if result.verdict == "UNKNOWN":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
