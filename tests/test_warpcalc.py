import pytest

from hdb.datatypes import (
    WARP_WIDTHS,
    bits_invert,
    cuda_thread_info,
    warp_apply_op,
    warp_width_label,
)


def test_warp_widths_order() -> None:
    assert WARP_WIDTHS == (4, 5, 8, 16, 32)


def test_warp_width_label() -> None:
    assert warp_width_label(5) == "WARP(5)"
    assert warp_width_label(4) == "4"
    assert warp_width_label(8) == "8"
    assert warp_width_label(16) == "16"
    assert warp_width_label(32) == "32"


def test_warp_and_or_xor_basic() -> None:
    assert warp_apply_op(0b1100, 0b1010, "AND", 4) == (0b1000, False)
    assert warp_apply_op(0b1100, 0b1010, "OR", 4) == (0b1110, False)
    assert warp_apply_op(0b1100, 0b1010, "XOR", 4) == (0b0110, False)


def test_warp_ops_mask_out_of_range_operands() -> None:
    # width 4: operands masked to low 4 bits before the op.
    assert warp_apply_op(0b1_0000, 0b1111, "AND", 4) == (0b0000, False)
    assert warp_apply_op(0b1_0001, 0b0010, "OR", 4) == (0b0011, False)


def test_warp_or_result_wraps_to_width() -> None:
    # Result is re-masked to width even though inputs would set higher bits.
    result, dropped = warp_apply_op(0xFF, 0xF0, "OR", 4)
    assert result == 0b1111
    assert dropped is False


def test_warp_ops_various_widths() -> None:
    assert warp_apply_op(0b10101, 0b01110, "XOR", 5) == (0b11011, False)
    assert warp_apply_op(0xAB, 0x0F, "AND", 8) == (0x0B, False)
    assert warp_apply_op(0xF0F0, 0x0FF0, "AND", 16) == (0x00F0, False)
    assert warp_apply_op(0xF0F0_0000, 0x0000_00FF, "OR", 32) == (0xF0F0_00FF, False)


def test_warp_shl_normal_no_drop() -> None:
    assert warp_apply_op(0b0001, 1, "SHL", 4) == (0b0010, False)


def test_warp_shl_drops_set_bits() -> None:
    result, dropped = warp_apply_op(0b1000, 1, "SHL", 4)
    assert result == 0b0000
    assert dropped is True


def test_warp_shl_clamp_beyond_width() -> None:
    assert warp_apply_op(0b0001, 4, "SHL", 4) == (0, True)
    assert warp_apply_op(0b0000, 4, "SHL", 4) == (0, False)


def test_warp_shr_logical_fills_zero() -> None:
    assert warp_apply_op(0b1000, 1, "SHR", 4) == (0b0100, False)
    assert warp_apply_op(0b1111, 2, "SHR", 4) == (0b0011, False)


def test_warp_shr_clamp_beyond_width() -> None:
    assert warp_apply_op(0b1111, 4, "SHR", 4) == (0, False)


def test_warp_shift_count_from_masked_b() -> None:
    # width 4: B masked to low 4 bits -> shift of 1, not 17.
    assert warp_apply_op(0b0001, 0b1_0001, "SHL", 4) == (0b0010, False)


def test_warp_unknown_op_raises() -> None:
    with pytest.raises(ValueError):
        warp_apply_op(1, 1, "NAND", 4)


def test_bits_invert() -> None:
    assert bits_invert("0000") == "1111"
    assert bits_invert("1010") == "0101"
    assert bits_invert("1") == "0"
    assert len(bits_invert("00110011")) == 8


def test_bits_invert_non_binary_raises() -> None:
    with pytest.raises(ValueError):
        bits_invert("012")


def test_cuda_thread_info_1d_block() -> None:
    info = cuda_thread_info(2, 5, (32, 1, 1))
    assert info["global"] == 69
    assert info["threadIdx.x"] == 5
    assert info["threadIdx.y"] == 0
    assert info["threadIdx.z"] == 0
    assert info["blockIdx.x"] == 2
    assert info["blockDim.x"] == 32
    assert info["blockDim.y"] == 1
    assert info["blockDim.z"] == 1


def test_cuda_thread_info_3d_decomposition() -> None:
    # linear = x + y*dim_x + z*dim_x*dim_y with blockDim (4, 3, 2)
    dims = (4, 3, 2)
    for z in range(2):
        for y in range(3):
            for x in range(4):
                linear = x + y * 4 + z * 12
                info = cuda_thread_info(0, linear, dims)
                assert info["threadIdx.x"] == x
                assert info["threadIdx.y"] == y
                assert info["threadIdx.z"] == z
                assert info["global"] == linear


def test_cuda_thread_info_global_formula() -> None:
    block_size = 2 * 2 * 2
    for block_idx in range(4):
        for linear_tid in range(block_size):
            info = cuda_thread_info(block_idx, linear_tid, (2, 2, 2))
            assert info["global"] == block_idx * block_size + linear_tid


def test_cuda_thread_info_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        cuda_thread_info(0, 0, (0, 1, 1))
    with pytest.raises(ValueError):
        cuda_thread_info(0, 8, (2, 2, 2))
    with pytest.raises(ValueError):
        cuda_thread_info(0, -1, (2, 2, 2))
