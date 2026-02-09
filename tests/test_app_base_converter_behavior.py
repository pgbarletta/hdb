from hdb.app import format_source_text


def test_source_format_preserves_binary_leading_zeros() -> None:
    assert format_source_text("00000001", 2) == "0000_0001"


def test_source_format_preserves_hex_leading_zeros_and_uppercases() -> None:
    assert format_source_text("00000f", 16) == "00_000F"


def test_source_format_preserves_decimal_leading_zeros() -> None:
    assert format_source_text("0001234", 10) == "0_001_234"
