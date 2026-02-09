from decimal import Decimal

from hdb.datatypes import (
    FLOAT_TYPE_SPECS,
    float_bits_and_fields,
    format_float_forward_calc,
    format_float_reverse_calc,
    format_ulp_error_formula,
)
from hdb.visualizer import FloatResultPanel


def test_float_forward_format_includes_field_boundaries() -> None:
    spec = FLOAT_TYPE_SPECS["single"]
    fields = float_bits_and_fields(Decimal("3.5"), spec)

    text = format_float_forward_calc(Decimal("3.5"), fields, spec)
    assert "single" in text
    assert "|" in text


def test_float_reverse_format_special_and_normal_paths() -> None:
    spec = FLOAT_TYPE_SPECS["double"]

    normal_fields = float_bits_and_fields(Decimal("1.5"), spec)
    normal_text = format_float_reverse_calc(normal_fields, spec)
    assert "(-1)^" in normal_text

    inf_fields = float_bits_and_fields(Decimal("1e9999"), spec)
    inf_text = format_float_reverse_calc(inf_fields, spec)
    assert "infinity" in inf_text


def test_ulp_error_formula_format() -> None:
    text = format_ulp_error_formula("1.003125", "1", "0.003125", 0.0078125, "0.4")
    assert "ULP error = |input - quantized| / ULP size" in text
    assert "|1.003125 - 1|" in text
    assert "= 0.003125 / 0.0078125 = 0.4" in text


def test_float_bit_sanitize_pads_to_fixed_width() -> None:
    assert FloatResultPanel._sanitize_bits("101", 5) == "10100"
    assert FloatResultPanel._sanitize_bits("", 4) == "0000"


def test_float_bit_sanitize_filters_and_truncates() -> None:
    assert FloatResultPanel._sanitize_bits("10a1b0", 4) == "1010"


def test_float_bit_insert_at_end_shifts_left() -> None:
    assert FloatResultPanel._insert_at_end_with_left_shift("10110", "0") == "01100"
    assert FloatResultPanel._insert_at_end_with_left_shift("0", "1") == "1"


def test_float_bit_index_tokens() -> None:
    assert FloatResultPanel._bit_index_tokens(5) == [" 4", " 3", " 2", " 1", " 0"]
    assert FloatResultPanel._bit_index_tokens(8) == [
        " 7",
        " 6",
        " 5",
        " 4",
        " 3",
        " 2",
        " 1",
        " 0",
    ]
    assert FloatResultPanel._bit_index_tokens(12) == [
        "11",
        "10",
        " 9",
        " 8",
        " 7",
        " 6",
        " 5",
        " 4",
        " 3",
        " 2",
        " 1",
        " 0",
    ]


def test_float_factor_decimal_format() -> None:
    assert FloatResultPanel._format_factor_decimal(Decimal("0")) == "0"
    assert FloatResultPanel._format_factor_decimal(Decimal("1.5")) == "1.5"
