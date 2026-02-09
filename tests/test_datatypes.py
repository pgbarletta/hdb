from decimal import Decimal

import numpy as np

from hdb.datatypes import (
    FLOAT_TYPE_SPECS,
    INT_TYPE_SPECS,
    build_all_float_panel_display_data,
    build_float_panel_display_data_from_bits,
    float_bits_and_fields,
    float_error_metrics,
    float_fields_from_bit_text,
    float_ulp_size,
    int_bits,
    int_wrap_and_flags,
    parse_decimal_input,
)


def test_parse_decimal_input_scientific_notation() -> None:
    assert parse_decimal_input("1.25e3") == Decimal("1.25e3")


def test_int8_wrap_overflow() -> None:
    spec = INT_TYPE_SPECS["int8_t"]
    wrapped, overflow, underflow = int_wrap_and_flags(130, spec)
    assert wrapped == -126
    assert overflow is True
    assert underflow is False
    assert int_bits(wrapped, spec.bits) == "10000010"


def test_uint8_wrap_underflow() -> None:
    spec = INT_TYPE_SPECS["uint8_t"]
    wrapped, overflow, underflow = int_wrap_and_flags(-1, spec)
    assert wrapped == 255
    assert overflow is False
    assert underflow is True
    assert int_bits(wrapped, spec.bits) == "11111111"


def test_float_classification_special_values() -> None:
    single = FLOAT_TYPE_SPECS["single"]

    pos_zero = float_bits_and_fields(Decimal("0"), single)
    neg_zero = float_bits_and_fields(Decimal("-0"), single)
    inf_fields = float_bits_and_fields(Decimal("1e9999"), single)

    smallest_subnormal = np.nextafter(np.float32(0.0), np.float32(1.0), dtype=np.float32)
    sub_fields = float_bits_and_fields(Decimal(str(float(smallest_subnormal))), single)

    assert pos_zero["classification"] == "+0"
    assert neg_zero["classification"] == "-0"
    assert inf_fields["classification"] == "+inf"
    assert sub_fields["classification"] == "subnormal"


def test_float_error_metrics_exact_representation_is_zero() -> None:
    double = FLOAT_TYPE_SPECS["double"]
    fields = float_bits_and_fields(Decimal("0.5"), double)
    abs_error, ulp_error = float_error_metrics(Decimal("0.5"), fields["quantized"], double)

    assert abs_error == "0"
    assert ulp_error == "0"


def test_float_ulp_size_constant_for_same_exponent_binade() -> None:
    single = FLOAT_TYPE_SPECS["single"]
    q1 = float(float_bits_and_fields(Decimal("1.25"), single)["quantized"])
    q2 = float(float_bits_and_fields(Decimal("1.75"), single)["quantized"])

    ulp1 = float_ulp_size(q1, single)
    ulp2 = float_ulp_size(q2, single)
    assert ulp1 is not None
    assert ulp2 is not None
    assert ulp1 == ulp2


def test_build_all_float_panel_display_data_shape() -> None:
    data = build_all_float_panel_display_data(Decimal("1.003125"))
    assert set(data.keys()) == {"half", "single", "double"}

    for panel in data.values():
        assert "quantized_text" in panel
        assert "classification" in panel
        assert "forward_calc" in panel
        assert "reverse_calc" in panel
        assert "abs_error" in panel
        assert "ulp_size" in panel
        assert "ulp_error" in panel
        assert "ulp_formula" in panel
        assert "bit_text" in panel
        assert "role_boundaries" in panel


def test_float_fields_from_bit_text_preserves_pattern() -> None:
    single = FLOAT_TYPE_SPECS["single"]
    fields = float_fields_from_bit_text("00111111100000000000000000000000", single)
    assert fields["classification"] == "normal"
    assert fields["bit_text"] == "00111111100000000000000000000000"
    assert fields["quantized"] == 1.0


def test_build_float_panel_display_data_from_bits_uses_input_for_errors() -> None:
    half = FLOAT_TYPE_SPECS["half"]
    panel = build_float_panel_display_data_from_bits(
        Decimal("0.1"),
        half,
        "0011110000000000",  # +1.0 in binary16
    )
    assert panel["quantized_text"] == "1"
    assert panel["abs_error"] != "0"
