"""LaTeX equation -> PNG rendering and clipboard helpers (no Tk imports).

Rendering shells out to the system ``latex`` and ``dvipng`` binaries so that the
full TeX math feature set (``\\boxed``, ``amsmath`` environments, ...) works.
Compilation (slow part) is split from rasterisation (fast part) so that changing
the output size only re-runs ``dvipng`` on the cached DVI.
"""
from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

# Output size presets -> dvipng resolution (dots per inch).
LATEX_SIZES: dict[str, int] = {
    "Small": 150,
    "Medium": 300,
    "Large": 600,
}
DEFAULT_SIZE = "Medium"
PREVIEW_DPI = 300

_TIMEOUT_SECONDS = 20.0

_PREAMBLE = (
    "\\documentclass{article}\n"
    "\\usepackage{amsmath,amssymb,amsfonts,bm}\n"
    "\\usepackage[active,tightpage]{preview}\n"
    "\\pagestyle{empty}\n"
    "\\begin{document}\n"
    "\\begin{preview}\n"
)
_POSTAMBLE = "\n\\end{preview}\n\\end{document}\n"


class LatexRenderError(Exception):
    """Raised when LaTeX/dvipng is missing, fails, or times out."""


def _unwrap_math_delimiters(text: str) -> str | None:
    """Return the inner math if ``text`` is wholly wrapped in one math delimiter pair."""
    if text.startswith("\\[") and text.endswith("\\]"):
        return text[2:-2].strip()
    if text.startswith("\\(") and text.endswith("\\)"):
        return text[2:-2].strip()
    if text.startswith("$$") and text.endswith("$$") and len(text) >= 4:
        return text[2:-2].strip()
    if text.startswith("$") and text.endswith("$") and len(text) >= 2:
        inner = text[1:-1]
        if not re.search(r"(?<!\\)\$", inner):
            return inner.strip()
    return None


def latex_source_to_body(text: str) -> str:
    """Turn pasted user text into the body placed inside the ``preview`` environment.

    Returns ``""`` for blank input. Plain math (optionally wrapped in ``\\[ \\]``,
    ``$$ $$``, ``$ $`` or ``\\( \\)``) is typeset as tight inline ``\\displaystyle``
    math; text that starts with a ``\\begin{...}`` environment or that already
    contains its own math delimiters is passed through untouched.
    """
    stripped = text.strip()
    if not stripped:
        return ""

    inner = _unwrap_math_delimiters(stripped)
    if inner is None:
        if stripped.startswith("\\begin{"):
            return stripped
        if re.search(r"(?<!\\)\$|\\\(|\\\[", stripped):
            return stripped
        inner = stripped
    if not inner:
        return ""

    if "&" in inner:
        inner = f"\\begin{{aligned}}\n{inner}\n\\end{{aligned}}"
    elif "\\\\" in inner:
        inner = f"\\begin{{gathered}}\n{inner}\n\\end{{gathered}}"
    return f"$\\displaystyle\n{inner}\n$"


def build_latex_document(text: str) -> str:
    """Full ``.tex`` source for ``text`` (raises ``ValueError`` on blank input)."""
    body = latex_source_to_body(text)
    if not body:
        raise ValueError("empty LaTeX source")
    return _PREAMBLE + body + _POSTAMBLE


def missing_tools() -> list[str]:
    """Names of required rendering binaries that are not on ``PATH``."""
    return [tool for tool in ("latex", "dvipng") if shutil.which(tool) is None]


def _extract_latex_error(log_text: str) -> str:
    lines = log_text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("!"):
            message = line[1:].strip()
            for follow in lines[index + 1 : index + 6]:
                if follow.startswith("l."):
                    return f"{message} ({follow.strip()})"
            return message
    return "LaTeX failed to compile the equation."


def compile_latex_dvi(text: str, timeout: float = _TIMEOUT_SECONDS) -> bytes:
    """Compile ``text`` with ``latex`` and return the DVI bytes."""
    missing = missing_tools()
    if missing:
        raise LatexRenderError(
            f"Missing required tool(s): {', '.join(missing)}. Install a TeX distribution "
            "(e.g. texlive) that provides latex and dvipng."
        )
    document = build_latex_document(text)
    with tempfile.TemporaryDirectory(prefix="hdb-latex-") as tmp:
        workdir = Path(tmp)
        (workdir / "eq.tex").write_text(document, encoding="utf-8")
        try:
            proc = subprocess.run(
                [
                    "latex",
                    "-no-shell-escape",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "eq.tex",
                ],
                cwd=workdir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                env={**os.environ, "openout_any": "p", "openin_any": "p"},
            )
        except subprocess.TimeoutExpired as exc:
            raise LatexRenderError("LaTeX timed out.") from exc
        dvi_path = workdir / "eq.dvi"
        if proc.returncode != 0 or not dvi_path.exists():
            log = proc.stdout.decode("utf-8", errors="replace")
            raise LatexRenderError(_extract_latex_error(log))
        return dvi_path.read_bytes()


def dvi_to_png(
    dvi: bytes,
    dpi: int,
    timeout: float = _TIMEOUT_SECONDS,
    transparent: bool = False,
) -> bytes:
    """Rasterise DVI bytes to a tightly cropped PNG at ``dpi`` (white or transparent background)."""
    if shutil.which("dvipng") is None:
        raise LatexRenderError("Missing required tool: dvipng.")
    with tempfile.TemporaryDirectory(prefix="hdb-latex-") as tmp:
        workdir = Path(tmp)
        (workdir / "eq.dvi").write_bytes(dvi)
        try:
            proc = subprocess.run(
                [
                    "dvipng",
                    "-q",
                    "-T",
                    "tight",
                    "-bg",
                    "Transparent" if transparent else "White",
                    "-D",
                    str(int(dpi)),
                    "-o",
                    "eq.png",
                    "eq.dvi",
                ],
                cwd=workdir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise LatexRenderError("dvipng timed out.") from exc
        png_path = workdir / "eq.png"
        if proc.returncode != 0 or not png_path.exists():
            detail = proc.stdout.decode("utf-8", errors="replace").strip()
            raise LatexRenderError(f"dvipng failed. {detail}".strip())
        return png_path.read_bytes()


def png_size(png: bytes) -> tuple[int, int]:
    """Return ``(width, height)`` in pixels from a PNG's IHDR chunk."""
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    width, height = struct.unpack(">II", png[16:24])
    return width, height


def clipboard_command() -> list[str] | None:
    """Command that reads a PNG on stdin and places it on the system clipboard."""
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        return ["wl-copy", "--type", "image/png"]
    if shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard", "-t", "image/png", "-i"]
    return None


def copy_png_to_clipboard(png: bytes) -> str:
    """Put ``png`` on the system clipboard as an image; returns the tool used.

    Tk cannot place images on the clipboard, so this delegates to ``wl-copy`` or
    ``xclip`` (which keep serving the selection from a background process).
    """
    command = clipboard_command()
    if command is None:
        raise LatexRenderError(
            "No clipboard tool found. Install xclip (X11) or wl-clipboard (Wayland)."
        )
    # stderr goes to a temp file, not a pipe: the tool forks a background process
    # that keeps serving the clipboard and would inherit (and hold open) a pipe,
    # so reading it to EOF would block until the clipboard owner changes.
    with tempfile.TemporaryFile() as err_file:
        try:
            proc = subprocess.run(
                command,
                input=png,
                stdout=subprocess.DEVNULL,
                stderr=err_file,
                timeout=10.0,
            )
        except subprocess.TimeoutExpired as exc:
            raise LatexRenderError(f"{command[0]} timed out.") from exc
        if proc.returncode != 0:
            err_file.seek(0)
            detail = err_file.read().decode("utf-8", errors="replace").strip()
            raise LatexRenderError(f"{command[0]} failed. {detail}".strip())
    return command[0]
