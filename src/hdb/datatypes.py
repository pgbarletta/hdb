from __future__ import annotations

import ctypes
import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import numpy as np


@dataclass(frozen=True)
class IntegerTypeSpec:
    name: str
    bits: int
    signed: bool


@dataclass(frozen=True)
class FloatTypeSpec:
    name: str
    bits: int
    exponent_bits: int
    mantissa_bits: int
    numpy_dtype: Any


def _clean_decimal_input(text: str) -> str:
    return text.strip().replace("_", "").replace(" ", "")


def _int_specs() -> dict[str, IntegerTypeSpec]:
    specs: dict[str, IntegerTypeSpec] = {}

    fixed_width: tuple[tuple[str, int, bool], ...] = (
        ("uint8_t", 8, False),
        ("int8_t", 8, True),
        ("uint16_t", 16, False),
        ("int16_t", 16, True),
        ("uint32_t", 32, False),
        ("int32_t", 32, True),
        ("uint64_t", 64, False),
        ("int64_t", 64, True),
    )
    for name, bits, signed in fixed_width:
        specs[name] = IntegerTypeSpec(name=name, bits=bits, signed=signed)

    short_bits = ctypes.sizeof(ctypes.c_short) * 8
    int_bits_size = ctypes.sizeof(ctypes.c_int) * 8
    long_bits = ctypes.sizeof(ctypes.c_long) * 8
    long_long_bits = ctypes.sizeof(ctypes.c_longlong) * 8

    cpp_native: tuple[tuple[str, int, bool], ...] = (
        ("short", short_bits, True),
        ("unsigned short", short_bits, False),
        ("int", int_bits_size, True),
        ("unsigned int", int_bits_size, False),
        ("long", long_bits, True),
        ("unsigned long", long_bits, False),
        ("long long", long_long_bits, True),
        ("unsigned long long", long_long_bits, False),
    )
    for name, bits, signed in cpp_native:
        specs[name] = IntegerTypeSpec(name=name, bits=bits, signed=signed)

    return specs


INT_TYPE_SPECS = _int_specs()


FLOAT_TYPE_SPECS: dict[str, FloatTypeSpec] = {
    "half": FloatTypeSpec(
        name="half",
        bits=16,
        exponent_bits=5,
        mantissa_bits=10,
        numpy_dtype=np.float16,
    ),
    "single": FloatTypeSpec(
        name="single",
        bits=32,
        exponent_bits=8,
        mantissa_bits=23,
        numpy_dtype=np.float32,
    ),
    "double": FloatTypeSpec(
        name="double",
        bits=64,
        exponent_bits=11,
        mantissa_bits=52,
        numpy_dtype=np.float64,
    ),
}


def parse_decimal_input(text: str) -> Decimal:
    cleaned = _clean_decimal_input(text)
    if cleaned in {"", "+", "-"}:
        return Decimal(0)

    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal input: {text!r}") from exc


def int_wrap_and_flags(value: int, spec: IntegerTypeSpec) -> tuple[int, bool, bool]:
    modulus = 1 << spec.bits
    unsigned_wrapped = value % modulus

    overflow = False
    underflow = False
    if spec.signed:
        min_value = -(1 << (spec.bits - 1))
        max_value = (1 << (spec.bits - 1)) - 1
        overflow = value > max_value
        underflow = value < min_value
        if unsigned_wrapped >= (1 << (spec.bits - 1)):
            wrapped = unsigned_wrapped - modulus
        else:
            wrapped = unsigned_wrapped
    else:
        min_value = 0
        max_value = modulus - 1
        overflow = value > max_value
        underflow = value < min_value
        wrapped = unsigned_wrapped

    return wrapped, overflow, underflow


def int_bits(value: int, bits: int) -> str:
    mask = (1 << bits) - 1
    return format(value & mask, f"0{bits}b")


def _decimal_to_float(value: Decimal) -> float:
    if value.is_nan():
        return math.nan
    if value == Decimal("Infinity"):
        return math.inf
    if value == Decimal("-Infinity"):
        return -math.inf
    try:
        return float(value)
    except OverflowError:
        return math.inf if value >= 0 else -math.inf


def _uint_dtype_for_bits(bits: int) -> Any:
    if bits == 16:
        return np.uint16
    if bits == 32:
        return np.uint32
    if bits == 64:
        return np.uint64
    raise ValueError(f"Unsupported float width: {bits}")


def _float_fields_from_raw(raw: int, spec: FloatTypeSpec) -> dict[str, Any]:
    bit_text = format(raw, f"0{spec.bits}b")
    sign_bits = bit_text[:1]
    exponent_bits = bit_text[1 : 1 + spec.exponent_bits]
    mantissa_bits = bit_text[1 + spec.exponent_bits :]

    exponent_raw = int(exponent_bits, 2)
    mantissa_raw = int(mantissa_bits, 2)
    exponent_all_ones = (1 << spec.exponent_bits) - 1

    if exponent_raw == exponent_all_ones and mantissa_raw != 0:
        classification = "NaN"
    elif exponent_raw == exponent_all_ones:
        classification = "+inf" if sign_bits == "0" else "-inf"
    elif exponent_raw == 0 and mantissa_raw == 0:
        classification = "+0" if sign_bits == "0" else "-0"
    elif exponent_raw == 0:
        classification = "subnormal"
    else:
        classification = "normal"

    np_raw = np.array([raw], dtype=_uint_dtype_for_bits(spec.bits))
    quantized = float(np_raw.view(spec.numpy_dtype)[0])

    return {
        "quantized": quantized,
        "bit_text": bit_text,
        "sign_bits": sign_bits,
        "exponent_bits": exponent_bits,
        "mantissa_bits": mantissa_bits,
        "exponent_raw": exponent_raw,
        "mantissa_raw": mantissa_raw,
        "classification": classification,
    }


def float_bits_and_fields(value: Decimal, spec: FloatTypeSpec) -> dict[str, Any]:
    py_float = _decimal_to_float(value)
    np_value = np.array([py_float], dtype=spec.numpy_dtype)
    raw = int(np_value.view(_uint_dtype_for_bits(spec.bits))[0])
    return _float_fields_from_raw(raw, spec)


def float_fields_from_bit_text(bit_text: str, spec: FloatTypeSpec) -> dict[str, Any]:
    cleaned = bit_text.strip().replace("_", "").replace(" ", "")
    if len(cleaned) != spec.bits:
        raise ValueError(
            f"Expected {spec.bits} bits for {spec.name}; got {len(cleaned)}."
        )
    if any(ch not in {"0", "1"} for ch in cleaned):
        raise ValueError(f"Bit text for {spec.name} must contain only 0/1.")
    return _float_fields_from_raw(int(cleaned, 2), spec)


def _format_decimal(value: Decimal) -> str:
    if value.is_nan():
        return "nan"
    if value == 0:
        return "0"
    text = format(value, ".12g")
    return text


def format_quantized(value: float) -> str:
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "+inf" if value > 0 else "-inf"
    if value == 0.0 and math.copysign(1.0, value) < 0:
        return "-0.0"
    return format(value, ".17g")


def format_ulp_size(ulp_size: float | None) -> str:
    if ulp_size is None:
        return "n/a"
    if ulp_size == 0.0:
        return "0"
    return format(ulp_size, ".12g")


def float_ulp_size(quantized: float, spec: FloatTypeSpec) -> float | None:
    if not math.isfinite(quantized):
        return None

    np_value = np.array([quantized], dtype=spec.numpy_dtype)
    up = np.nextafter(np_value, np.array([math.inf], dtype=spec.numpy_dtype), dtype=spec.numpy_dtype)[0]
    down = np.nextafter(np_value, np.array([-math.inf], dtype=spec.numpy_dtype), dtype=spec.numpy_dtype)[0]

    candidates = [
        abs(float(np.float64(up) - np.float64(np_value[0]))),
        abs(float(np.float64(np_value[0]) - np.float64(down))),
    ]
    non_zero = [candidate for candidate in candidates if candidate > 0.0]
    if not non_zero:
        return 0.0
    return min(non_zero)


def float_error_metrics(
    input_value: Decimal,
    quantized: float,
    spec: FloatTypeSpec,
) -> tuple[str, str]:
    input_float = _decimal_to_float(input_value)
    if math.isnan(input_float) or math.isnan(quantized):
        return "n/a", "n/a"

    if math.isinf(input_float) or math.isinf(quantized):
        same_inf = (
            math.isinf(input_float)
            and math.isinf(quantized)
            and math.copysign(1.0, input_float) == math.copysign(1.0, quantized)
        )
        if same_inf:
            return "0", "0"
        return "n/a", "n/a"

    quantized_decimal = Decimal.from_float(float(quantized))
    abs_error = abs(input_value - quantized_decimal)
    abs_text = _format_decimal(abs_error)
    if abs_error == 0:
        return "0", "0"

    ulp = float_ulp_size(quantized, spec)
    if ulp is None or ulp == 0:
        return abs_text, "n/a"

    ulp_error = abs_error / Decimal(str(ulp))
    ulp_text = _format_decimal(ulp_error)
    return abs_text, ulp_text


def format_float_forward_calc(
    input_value: Decimal,
    fields: dict[str, Any],
    spec: FloatTypeSpec,
) -> str:
    return (
        f"{input_value} -> {spec.name}: "
        f"{fields['sign_bits']} | {fields['exponent_bits']} | {fields['mantissa_bits']}"
    )


def format_float_reverse_calc(fields: dict[str, Any], spec: FloatTypeSpec) -> str:
    sign = int(fields["sign_bits"])
    exponent_raw = int(fields["exponent_raw"])
    mantissa_raw = int(fields["mantissa_raw"])
    bias = (1 << (spec.exponent_bits - 1)) - 1

    classification = fields["classification"]
    if classification == "NaN":
        return "Exponent all 1s with non-zero mantissa -> NaN"
    if classification in {"+inf", "-inf"}:
        return "Exponent all 1s with zero mantissa -> infinity"
    if classification in {"+0", "-0"}:
        return f"(-1)^{sign} * 0 -> {classification}"

    if classification == "subnormal":
        return (
            f"(-1)^{sign} * ({mantissa_raw} / 2^{spec.mantissa_bits}) "
            f"* 2^(1-{bias})"
        )

    return (
        f"(-1)^{sign} * (1 + {mantissa_raw}/2^{spec.mantissa_bits}) "
        f"* 2^({exponent_raw}-{bias})"
    )


def format_ulp_error_formula(
    input_text: str,
    quantized_text: str,
    abs_error: str,
    ulp_size: float | None,
    ulp_error: str,
) -> str:
    if abs_error == "n/a" or ulp_error == "n/a" or ulp_size is None:
        return (
            "ULP error = |input - quantized| / ULP size = "
            f"|{input_text} - {quantized_text}| / n/a"
        )

    if ulp_size == 0.0:
        ulp_size_text = "0"
    else:
        ulp_size_text = format(ulp_size, ".12g")

    return (
        "ULP error = |input - quantized| / ULP size = "
        f"|{input_text} - {quantized_text}| / {ulp_size_text} = "
        f"{abs_error} / {ulp_size_text} = {ulp_error}"
    )


def build_float_panel_display_data(
    input_value: Decimal,
    spec: FloatTypeSpec,
) -> dict[str, Any]:
    fields = float_bits_and_fields(input_value, spec)
    quantized = float(fields["quantized"])
    quantized_text = format_quantized(quantized)
    ulp_size = float_ulp_size(quantized, spec)
    abs_error, ulp_error = float_error_metrics(input_value, quantized, spec)

    return {
        "quantized_text": quantized_text,
        "classification": str(fields["classification"]),
        "forward_calc": format_float_forward_calc(input_value, fields, spec),
        "reverse_calc": format_float_reverse_calc(fields, spec),
        "abs_error": abs_error,
        "ulp_size": format_ulp_size(ulp_size),
        "ulp_error": ulp_error,
        "ulp_formula": format_ulp_error_formula(
            str(input_value),
            quantized_text,
            abs_error,
            ulp_size,
            ulp_error,
        ),
        "bit_text": str(fields["bit_text"]),
        "role_boundaries": (1, 1 + spec.exponent_bits),
    }


def build_float_panel_display_data_from_bits(
    input_value: Decimal,
    spec: FloatTypeSpec,
    bit_text: str,
) -> dict[str, Any]:
    fields = float_fields_from_bit_text(bit_text, spec)
    quantized = float(fields["quantized"])
    quantized_text = format_quantized(quantized)
    ulp_size = float_ulp_size(quantized, spec)
    abs_error, ulp_error = float_error_metrics(input_value, quantized, spec)

    return {
        "quantized_text": quantized_text,
        "classification": str(fields["classification"]),
        "forward_calc": format_float_forward_calc(input_value, fields, spec),
        "reverse_calc": format_float_reverse_calc(fields, spec),
        "abs_error": abs_error,
        "ulp_size": format_ulp_size(ulp_size),
        "ulp_error": ulp_error,
        "ulp_formula": format_ulp_error_formula(
            str(input_value),
            quantized_text,
            abs_error,
            ulp_size,
            ulp_error,
        ),
        "bit_text": str(fields["bit_text"]),
        "role_boundaries": (1, 1 + spec.exponent_bits),
    }


def build_all_float_panel_display_data(
    input_value: Decimal,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for name in ("half", "single", "double"):
        results[name] = build_float_panel_display_data(input_value, FLOAT_TYPE_SPECS[name])
    return results
