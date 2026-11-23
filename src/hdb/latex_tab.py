from __future__ import annotations

import base64
from concurrent.futures import Future, ThreadPoolExecutor
import tkinter as tk
from typing import NamedTuple

from .latex_render import (
    DEFAULT_SIZE,
    LATEX_SIZES,
    PREVIEW_DPI,
    LatexRenderError,
    compile_latex_dvi,
    copy_png_to_clipboard,
    dvi_to_png,
    latex_source_to_body,
    png_size,
)

BG = "#f5f7fa"
UI_FONT = ("DejaVu Sans", 13)
UI_FONT_BOLD = ("DejaVu Sans", 13, "bold")
SOURCE_FONT = ("DejaVu Sans Mono", 14)
ERROR_FG = "#b00020"
STATUS_FG = "#3f5368"
OK_FG = "#1b6e3c"

PREVIEW_BG = "white"
PREVIEW_BG_TRANSPARENT = "#c8d0d9"  # darker backdrop so transparency is visible

PLACEHOLDER_STATUS = "Paste a LaTeX equation above; it renders automatically."


class RenderResult(NamedTuple):
    dvi: bytes
    preview_png: bytes
    output_png: bytes


def render_job(
    source: str, cached_dvi: bytes | None, dpi: int, transparent: bool = False
) -> RenderResult:
    """Worker-thread job: compile (unless cached) and rasterise preview + output."""
    dvi = cached_dvi if cached_dvi is not None else compile_latex_dvi(source)
    return RenderResult(
        dvi,
        dvi_to_png(dvi, PREVIEW_DPI, transparent=transparent),
        dvi_to_png(dvi, dpi, transparent=transparent),
    )


class LatexFrame(tk.Frame):
    """LaTeX tab: paste an equation, see it rendered, copy it as a PNG image."""

    _DEBOUNCE_MS = 350
    _POLL_MS = 30

    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, bg=BG)

        self.size_var = tk.StringVar(value=DEFAULT_SIZE)
        self.status_var = tk.StringVar(value=PLACEHOLDER_STATUS)
        self.output_info_var = tk.StringVar(value="")
        self.transparent_var = tk.BooleanVar(value=False)

        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hdb-latex")
        self._job_id = 0
        self._debounce_after_id: str | None = None
        self._poll_after_id: str | None = None
        self._dvi_source: str | None = None
        self._dvi: bytes | None = None
        self._preview_png: bytes | None = None
        self._output_png: bytes | None = None
        self._preview_photo: tk.PhotoImage | None = None
        self._preview_shown: tk.PhotoImage | None = None

        self._build_ui()

        self.source_text.bind("<<Modified>>", self._on_source_modified)
        self.preview_frame.bind("<Configure>", lambda _e: self._refresh_preview())

    # ------------------------------------------------------------------ UI --
    def _build_ui(self) -> None:
        tk.Label(
            self,
            text="LaTeX equation",
            bg=BG,
            fg="#22313f",
            font=UI_FONT_BOLD,
            anchor="w",
        ).pack(fill="x", padx=12, pady=(12, 4))

        source_row = tk.Frame(self, bg=BG)
        source_row.pack(fill="x", padx=12)
        self.source_text = tk.Text(
            source_row,
            height=8,
            wrap="word",
            undo=True,
            font=SOURCE_FONT,
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#b8b8b8",
        )
        scrollbar = tk.Scrollbar(source_row, orient="vertical", command=self.source_text.yview)
        self.source_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.source_text.pack(side="left", fill="x", expand=True)

        controls = tk.Frame(self, bg=BG)
        controls.pack(fill="x", padx=12, pady=(10, 4))

        tk.Label(controls, text="Image size", bg=BG, fg="#22313f", font=UI_FONT_BOLD).pack(
            side="left"
        )
        for name, dpi in LATEX_SIZES.items():
            tk.Radiobutton(
                controls,
                text=f"{name} ({dpi} dpi)",
                value=name,
                variable=self.size_var,
                command=self._on_size_change,
                bg=BG,
                activebackground=BG,
                font=UI_FONT,
                anchor="w",
            ).pack(side="left", padx=(12, 0))

        tk.Checkbutton(
            controls,
            text="Transparent background",
            variable=self.transparent_var,
            command=self._on_transparent_change,
            bg=BG,
            activebackground=BG,
            font=UI_FONT,
        ).pack(side="left", padx=(24, 0))

        self.copy_button = tk.Button(
            controls,
            text="Copy image to clipboard",
            command=self._on_copy_click,
            font=UI_FONT_BOLD,
            state="disabled",
            padx=10,
        )
        self.copy_button.pack(side="right")
        tk.Button(controls, text="Clear", command=self._on_clear_click, font=UI_FONT, padx=10).pack(
            side="right", padx=(0, 8)
        )

        tk.Label(
            self,
            textvariable=self.output_info_var,
            bg=BG,
            fg=STATUS_FG,
            font=UI_FONT,
            anchor="w",
        ).pack(fill="x", padx=12)

        self.preview_frame = tk.Frame(
            self, bg="white", relief="solid", bd=1, highlightthickness=0
        )
        self.preview_frame.pack(fill="both", expand=True, padx=12, pady=(6, 6))
        self.preview_label = tk.Label(self.preview_frame, bg="white", bd=0)
        self.preview_label.place(relx=0.5, rely=0.5, anchor="center")

        self.status_label = tk.Label(
            self,
            textvariable=self.status_var,
            bg=BG,
            fg=STATUS_FG,
            anchor="w",
            justify="left",
            font=UI_FONT,
        )
        self.status_label.pack(fill="x", padx=12, pady=(0, 12))

    def focus_primary_input(self) -> None:
        self.source_text.focus_set()

    # ------------------------------------------------------------ handlers --
    def _on_source_modified(self, _event: tk.Event) -> None:
        if not self.source_text.edit_modified():
            return
        self.source_text.edit_modified(False)
        # Anything shown/copied no longer matches the source; invalidate at once
        # so a quick click on "Copy" can never grab a stale image.
        self._job_id += 1
        self._set_output(None)
        if self._debounce_after_id is not None:
            self.after_cancel(self._debounce_after_id)
        self._debounce_after_id = self.after(self._DEBOUNCE_MS, self._dispatch_render)

    def _on_size_change(self) -> None:
        if self._debounce_after_id is not None:
            return  # a render for the pending edit will pick up the new size
        self._dispatch_render()

    def _on_transparent_change(self) -> None:
        backdrop = PREVIEW_BG_TRANSPARENT if self.transparent_var.get() else PREVIEW_BG
        self.preview_frame.configure(bg=backdrop)
        self.preview_label.configure(bg=backdrop)
        self._on_size_change()  # same path: re-rasterise from the cached DVI

    def _on_clear_click(self) -> None:
        self.source_text.delete("1.0", "end")
        self.source_text.focus_set()

    def _on_copy_click(self) -> None:
        if self._output_png is None:
            return
        width, height = png_size(self._output_png)
        try:
            tool = copy_png_to_clipboard(self._output_png)
        except LatexRenderError as exc:
            self._set_status(str(exc), ERROR_FG)
            return
        self._set_status(
            f"Copied {width} × {height} px {'transparent ' if self.transparent_var.get() else ''}PNG "
            f"({self.size_var.get().lower()}) to the clipboard via {tool}.",
            OK_FG,
        )

    # ----------------------------------------------------------- rendering --
    def _dispatch_render(self) -> None:
        self._debounce_after_id = None
        source = self.source_text.get("1.0", "end-1c")
        self._job_id += 1
        job_id = self._job_id
        if not latex_source_to_body(source):
            self._set_output(None, clear_preview=True)
            self._set_status(PLACEHOLDER_STATUS, STATUS_FG)
            return

        dpi = LATEX_SIZES[self.size_var.get()]
        transparent = self.transparent_var.get()
        cached = self._dvi if source == self._dvi_source else None
        self._set_output(None)
        self._set_status("Rendering…", STATUS_FG)
        future = self._executor.submit(render_job, source, cached, dpi, transparent)
        self._schedule_poll(job_id, source, future)

    def _schedule_poll(self, job_id: int, source: str, future: Future[RenderResult]) -> None:
        # Poll from the main thread instead of touching Tk from the worker.
        self._poll_after_id = self.after(self._POLL_MS, self._poll_job, job_id, source, future)

    def _poll_job(self, job_id: int, source: str, future: Future[RenderResult]) -> None:
        self._poll_after_id = None
        if job_id != self._job_id:
            return  # superseded by a newer edit/size change: drop the stale result
        if not future.done():
            self._schedule_poll(job_id, source, future)
            return
        try:
            result = future.result()
        except LatexRenderError as exc:
            self._set_output(None, clear_preview=True)
            self._set_status(str(exc), ERROR_FG)
            return
        except Exception as exc:  # defensive: never leave the tab stuck on "Rendering…"
            self._set_output(None, clear_preview=True)
            self._set_status(f"Unexpected render error: {exc}", ERROR_FG)
            return

        self._dvi_source = source
        self._dvi = result.dvi
        self._set_preview(result.preview_png)
        self._set_output(result.output_png)
        self._set_status("Rendered. Click “Copy image to clipboard” to copy the PNG.", STATUS_FG)

    # ------------------------------------------------------- state helpers --
    def _set_status(self, message: str, color: str) -> None:
        self.status_var.set(message)
        self.status_label.configure(fg=color)

    def _set_output(self, png: bytes | None, clear_preview: bool = False) -> None:
        self._output_png = png
        if png is None:
            self.copy_button.configure(state="disabled")
            self.output_info_var.set("")
            if clear_preview:
                self._preview_png = None
                self._refresh_preview()
            return
        width, height = png_size(png)
        kind = "transparent PNG" if self.transparent_var.get() else "PNG"
        self.output_info_var.set(f"Output: {width} × {height} px {kind}")
        self.copy_button.configure(state="normal")

    def _set_preview(self, png: bytes) -> None:
        self._preview_png = png
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        """Show the preview PNG, shrunk by an integer factor to fit the pane."""
        if self._preview_png is None:
            self.preview_label.configure(image="")
            self._preview_photo = None
            self._preview_shown = None
            return
        photo = tk.PhotoImage(data=base64.b64encode(self._preview_png))
        avail_w = max(self.preview_frame.winfo_width() - 24, 1)
        avail_h = max(self.preview_frame.winfo_height() - 24, 1)
        factor = max(
            1,
            -(-photo.width() // avail_w),
            -(-photo.height() // avail_h),
        )
        shown = photo.subsample(factor) if factor > 1 else photo
        self._preview_photo = photo
        self._preview_shown = shown
        self.preview_label.configure(image=shown)

    # ------------------------------------------------------------- cleanup --
    def destroy(self) -> None:
        for after_id in (self._debounce_after_id, self._poll_after_id):
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
        self._executor.shutdown(wait=False, cancel_futures=True)
        super().destroy()
