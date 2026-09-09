from decimal import Decimal

import pytest

from math_check_mcp.checker import check_math, compare_values, eval_math, normalize_claim


def test_nine_point_nine_greater_than_nine_point_eleven():
    result = check_math("9.9 > 9.11")
    assert result.verdict == "RIGHT"
    assert "RIGHT" in result.format_display()


def test_nine_point_eleven_greater_than_nine_point_nine_is_wrong():
    result = check_math("9.11 > 9.9")
    assert result.verdict == "WRONG"
    assert result.display == "WRONG"


def test_english_phrase_matches_decimal_truth():
    assert check_math("9.9 is greater than 9.11").verdict == "RIGHT"
    assert check_math("9.11 is greater than 9.9").verdict == "WRONG"
    assert check_math("2+2 is equal to 4").verdict == "RIGHT"


def test_equation_right_and_wrong():
    assert check_math("2+2=4").verdict == "RIGHT"
    assert check_math("2+2=5").verdict == "WRONG"
    assert check_math("2+2==4").verdict == "RIGHT"


def test_expected_value():
    assert check_math("2+2", expected="4").verdict == "RIGHT"
    assert check_math("2+2", expected="5").verdict == "WRONG"


def test_bare_expression_is_unknown():
    result = check_math("2+2")
    assert result.verdict == "UNKNOWN"
    assert result.value == Decimal("4")


def test_functions_and_constants():
    assert check_math("sqrt(9) == 3").verdict == "RIGHT"
    assert check_math("sin(0) = 0").verdict == "RIGHT"
    assert check_math("abs(-3) = 3").verdict == "RIGHT"


def test_chained_comparison():
    assert check_math("1 < 2 < 3").verdict == "RIGHT"
    assert check_math("1 < 2 < 2").verdict == "WRONG"


def test_fullwidth_and_caret_power():
    assert check_math("２＋２＝４").verdict == "RIGHT"
    assert check_math("2^3 = 8").verdict == "RIGHT"


def test_european_comma_decimal():
    assert check_math("9,9 > 9,11").verdict == "RIGHT"


def test_reject_attribute_and_name():
    assert check_math("__import__('os')").verdict == "UNKNOWN"
    assert check_math("open('x')").verdict == "UNKNOWN"


def test_eval_math_decimal_literals():
    assert eval_math("9.9") == Decimal("9.9")
    assert eval_math("9.11") == Decimal("9.11")
    assert eval_math("9.9") > eval_math("9.11")


def test_compare_values():
    assert compare_values("9.9", "9.11", ">").verdict == "RIGHT"
    assert compare_values("9.11", "9.9", ">").verdict == "WRONG"
    assert compare_values("1+1", "2", "==").verdict == "RIGHT"


def test_empty_and_bad_operator():
    assert check_math("").verdict == "UNKNOWN"
    assert compare_values("1", "2", "??").verdict == "UNKNOWN"


def test_normalize_phrase():
    assert ">" in normalize_claim("9.9 is greater than 9.11")


def test_division_by_zero_unknown():
    assert check_math("1/0 = 1").verdict == "UNKNOWN"


def test_disallowed_syntax_raises_via_check():
    assert check_math("lambda: 1").verdict == "UNKNOWN"


@pytest.mark.parametrize(
    "claim,verdict",
    [
        ("10 >= 10", "RIGHT"),
        ("10 > 10", "WRONG"),
        ("pi > 3", "RIGHT"),
        ("min(3, 1) == 1", "RIGHT"),
        ("round(3.7) == 4", "RIGHT"),
    ],
)
def test_assorted_claims(claim, verdict):
    assert check_math(claim).verdict == verdict
