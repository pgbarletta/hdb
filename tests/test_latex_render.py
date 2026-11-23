import struct

import pytest

from hdb import latex_render as lr

PASTED_EQUATION = r"""
\[
\boxed{
\mathbf F_i
=-\frac{\partial U}{\partial\phi}
\frac{\partial\phi}{\partial\mathbf r_i},
\qquad i=1,2,3,4
}
\]
"""

needs_tex = pytest.mark.skipif(
    bool(lr.missing_tools()), reason="latex and dvipng are required"
)


def test_size_presets_are_ordered_small_medium_large() -> None:
    assert list(lr.LATEX_SIZES) == ["Small", "Medium", "Large"]
    dpis = list(lr.LATEX_SIZES.values())
    assert dpis == sorted(dpis) and len(set(dpis)) == 3
    assert lr.DEFAULT_SIZE in lr.LATEX_SIZES


@pytest.mark.parametrize(
    "source",
    [
        r"\[ x^2 \]",
        "$$ x^2 $$",
        "$x^2$",
        r"\( x^2 \)",
        "x^2",
        "\n  x^2  \n",
    ],
)
def test_delimiters_are_stripped_to_same_body(source: str) -> None:
    assert lr.latex_source_to_body(source) == "$\\displaystyle\nx^2\n$"


@pytest.mark.parametrize("source", ["", "   \n\t", r"\[   \]", "$$ $$"])
def test_blank_source_gives_empty_body(source: str) -> None:
    assert lr.latex_source_to_body(source) == ""
    with pytest.raises(ValueError):
        lr.build_latex_document(source)


def test_environment_and_text_with_own_math_pass_through() -> None:
    env = "\\begin{align*}\na &= b\n\\end{align*}"
    assert lr.latex_source_to_body(env) == env
    mixed = r"Energy $E = mc^2$ here"
    assert lr.latex_source_to_body(mixed) == mixed


def test_dollar_inside_wrapped_math_is_not_treated_as_one_pair() -> None:
    # "$a$ and $b$" is text with two inline maths, not one $...$ pair.
    text = "$a$ and $b$"
    assert lr.latex_source_to_body(text) == text


def test_multiline_math_uses_gathered_or_aligned() -> None:
    assert "\\begin{gathered}" in lr.latex_source_to_body(r"\[ a \\ b \]")
    assert "\\begin{aligned}" in lr.latex_source_to_body(r"\[ a &= b \\ c &= d \]")


def test_document_wraps_pasted_equation_with_required_packages() -> None:
    doc = lr.build_latex_document(PASTED_EQUATION)
    assert "\\usepackage{amsmath" in doc
    assert "\\boxed{" in doc
    assert doc.count("\\[") == 0  # display delimiters replaced by tight inline math
    assert doc.index("\\begin{preview}") < doc.index("\\boxed") < doc.index("\\end{preview}")


def test_png_size_reads_ihdr_and_rejects_garbage() -> None:
    png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 610, 127)
    assert lr.png_size(png) == (610, 127)
    with pytest.raises(ValueError):
        lr.png_size(b"not a png at all, definitely")


def test_latex_error_message_extraction() -> None:
    log = "This is pdfTeX\n! Undefined control sequence.\nl.8 \\foo\n\nmore"
    assert lr._extract_latex_error(log) == "Undefined control sequence. (l.8 \\foo)"
    assert "failed" in lr._extract_latex_error("no bang lines here")


@needs_tex
def test_render_pasted_equation_at_each_size_scales_with_dpi() -> None:
    dvi = lr.compile_latex_dvi(PASTED_EQUATION)
    widths = {}
    for name, dpi in lr.LATEX_SIZES.items():
        png = lr.dvi_to_png(dvi, dpi)
        assert png.startswith(b"\x89PNG")
        widths[name] = lr.png_size(png)[0]
    assert widths["Small"] < widths["Medium"] < widths["Large"]
    # Resolution is linear in dpi (allow a pixel of rounding either way).
    assert abs(widths["Large"] - 2 * widths["Medium"]) <= 3
    assert abs(widths["Medium"] - 2 * widths["Small"]) <= 3


@needs_tex
def test_render_is_tightly_cropped() -> None:
    dvi = lr.compile_latex_dvi("x")
    width, height = lr.png_size(lr.dvi_to_png(dvi, 300))
    assert width < 100 and height < 100


@needs_tex
def test_bad_latex_raises_readable_error() -> None:
    with pytest.raises(lr.LatexRenderError, match="Undefined control sequence"):
        lr.compile_latex_dvi(r"\notarealmacro")


@needs_tex
def test_shell_escape_and_absolute_file_reads_are_blocked() -> None:
    with pytest.raises(lr.LatexRenderError):
        lr.compile_latex_dvi(r"\input{/etc/hostname}")


def test_missing_tools_gives_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lr.shutil, "which", lambda _name: None)
    with pytest.raises(lr.LatexRenderError, match="latex, dvipng"):
        lr.compile_latex_dvi("x")


def test_clipboard_prefers_wl_copy_on_wayland(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setattr(lr.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert lr.clipboard_command() == ["wl-copy", "--type", "image/png"]


def test_clipboard_falls_back_to_xclip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(
        lr.shutil, "which", lambda name: "/usr/bin/xclip" if name == "xclip" else None
    )
    command = lr.clipboard_command()
    assert command is not None and command[0] == "xclip"
    assert command[-3:] == ["-t", "image/png", "-i"]


def test_copy_without_any_clipboard_tool_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lr, "clipboard_command", lambda: None)
    with pytest.raises(lr.LatexRenderError, match="clipboard"):
        lr.copy_png_to_clipboard(b"\x89PNG")


def _png_color_type(png: bytes) -> int:
    return png[25]  # IHDR color type byte


@needs_tex
def test_transparent_background_png_has_alpha_and_opaque_does_not() -> None:
    dvi = lr.compile_latex_dvi("x^2")
    opaque = lr.dvi_to_png(dvi, 300)
    transparent = lr.dvi_to_png(dvi, 300, transparent=True)
    assert lr.png_size(opaque) == lr.png_size(transparent)
    assert b"tRNS" not in opaque and _png_color_type(opaque) != 6
    assert b"tRNS" in transparent or _png_color_type(transparent) == 6
