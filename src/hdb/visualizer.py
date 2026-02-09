from __future__ import annotations

from bisect import bisect_right
from concurrent.futures import Future, ThreadPoolExecutor
import time
import tkinter as tk
import tkinter.font as tkfont
from decimal import Decimal
from tkinter import ttk
from typing import Any, Callable

from .datatypes import (
    FLOAT_TYPE_SPECS,
    INT_TYPE_SPECS,
    FloatTypeSpec,
    build_all_float_panel_display_data,
    float_fields_from_bit_text,
    int_bits,
    int_wrap_and_flags,
    parse_decimal_input,
)

UI_FONT = ("DejaVu Sans", 13)
UI_FONT_BOLD = ("DejaVu Sans", 13, "bold")
PANEL_TITLE_FONT = ("DejaVu Sans", 14, "bold")
ENTRY_FONT = ("DejaVu Sans Mono", 17, "bold")
VALUE_FONT = ("DejaVu Sans Mono", 13)
BIT_FIELD_FONT = ("DejaVu Sans Mono", 21, "bold")
BIT_INDEX_FONT = ("DejaVu Sans Mono", 9, "bold")
BIT_FONT = ("DejaVu Sans Mono", 15, "bold")
BIT_SEPARATOR_FONT = ("DejaVu Sans Mono", 16, "bold")
TOOLTIP_FONT = ("DejaVu Sans", 12)
BITGRID_SINGLE_ROW_HEIGHT = 56
BITGRID_DOUBLE_ROW_HEIGHT = 92
BIT_INDEX_ROW_HEIGHT = 14


class HoverExplain:
    def __init__(
        self,
        widget: tk.Widget,
        text_provider: str | Callable[[], str],
    ) -> None:
        self.widget = widget
        self.text_provider = text_provider
        self._tooltip: tk.Toplevel | None = None

        widget.bind("<Enter>", self._on_enter, add=True)
        widget.bind("<Leave>", self._on_leave, add=True)
        widget.bind("<Motion>", self._on_motion, add=True)

    def _resolve_text(self) -> str:
        if callable(self.text_provider):
            return self.text_provider()
        return self.text_provider

    def _on_enter(self, event: tk.Event) -> None:
        text = self._resolve_text()
        if not text:
            return
        self._tooltip = tk.Toplevel(self.widget)
        self._tooltip.overrideredirect(True)
        self._tooltip.attributes("-topmost", True)
        label = tk.Label(
            self._tooltip,
            text=text,
            bg="#fffdeb",
            fg="#1f2d3d",
            justify="left",
            padx=8,
            pady=6,
            relief="solid",
            bd=1,
            font=TOOLTIP_FONT,
        )
        label.pack()
        self._move_tooltip(event)

    def _on_leave(self, _event: tk.Event) -> None:
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None

    def _on_motion(self, event: tk.Event) -> None:
        self._move_tooltip(event)

    def _move_tooltip(self, event: tk.Event) -> None:
        if self._tooltip is None:
            return
        self._tooltip.geometry(f"+{event.x_root + 16}+{event.y_root + 16}")


class BitGrid(tk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, bg="#ffffff")
        self._render_cache: tuple[str, tuple[int, ...], int | None, bool] | None = None
        self._current_bit_text = ""
        self._last_role_boundaries: tuple[int, ...] = ()
        self._last_line_break_before: int | None = None
        self._last_editable = False
        self._active_on_bits_change: Callable[[str], None] | None = None

        self.canvas = tk.Canvas(
            self,
            bg="#ffffff",
            bd=0,
            highlightthickness=0,
            height=BITGRID_SINGLE_ROW_HEIGHT,
        )
        self.canvas.pack(fill="x", expand=True)

        self.inner = tk.Frame(self.canvas, bg="#ffffff")
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._sync_scroll_region)
        self.canvas.bind("<Configure>", self._sync_window_width)

    def _sync_scroll_region(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_window_width(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _render_row(
        self,
        host: tk.Widget,
        bit_text: str,
        role_boundaries: tuple[int, ...],
        start: int,
        stop: int,
        *,
        skip_leading_separator: bool,
        editable: bool,
        entries: list[tk.Entry | None],
        bit_values: list[str],
    ) -> None:
        field_starts = [0, *role_boundaries]
        for idx in range(start, stop):
            if idx in role_boundaries and not (skip_leading_separator and idx == start):
                sep = tk.Label(
                    host,
                    text="|",
                    bg="#ffffff",
                    fg="#6c7a89",
                    font=BIT_SEPARATOR_FONT,
                )
                sep.pack(side="left", padx=(6, 6))

            field_start = field_starts[bisect_right(field_starts, idx) - 1]
            within_field_pos = idx - field_start
            left_pad = 8 if within_field_pos > 0 and within_field_pos % 4 == 0 else 2
            if not editable:
                bit_label = tk.Label(
                    host,
                    text=bit_text[idx],
                    width=1,
                    bg="#f7fbff",
                    fg="#1f2d3d",
                    relief="solid",
                    bd=1,
                    font=BIT_FONT,
                    padx=2,
                    pady=4,
                )
                bit_label.pack(side="left", padx=(left_pad, 2), pady=4)
                continue

            bit_var = tk.StringVar(value=bit_text[idx])
            bit_entry = tk.Entry(
                host,
                width=1,
                justify="center",
                font=BIT_FONT,
                relief="solid",
                bd=1,
                bg="#f7fbff",
                fg="#1f2d3d",
                insertwidth=0,
            )
            bit_entry.configure(textvariable=bit_var)
            bit_entry.pack(side="left", padx=(left_pad, 2), pady=4)
            entries[idx] = bit_entry

            def _emit_bits_change() -> None:
                self._current_bit_text = "".join(bit_values)
                self._render_cache = (
                    self._current_bit_text,
                    self._last_role_boundaries,
                    self._last_line_break_before,
                    self._last_editable,
                )
                if self._active_on_bits_change is not None:
                    self._active_on_bits_change(self._current_bit_text)

            def _focus_entry(target_idx: int) -> None:
                target = entries[target_idx]
                if target is None:
                    return
                target.focus_set()
                target.icursor(tk.END)

            def _on_key(event: tk.Event, bit_idx: int = idx) -> str | None:
                if event.keysym in {"Tab", "ISO_Left_Tab"}:
                    return None
                if event.keysym in {"Left", "KP_Left"}:
                    if bit_idx > 0:
                        _focus_entry(bit_idx - 1)
                    return "break"
                if event.keysym in {"Right", "KP_Right"}:
                    if bit_idx < len(entries) - 1:
                        _focus_entry(bit_idx + 1)
                    return "break"
                if event.keysym == "Home":
                    _focus_entry(0)
                    return "break"
                if event.keysym == "End":
                    _focus_entry(len(entries) - 1)
                    return "break"

                if event.char in {"0", "1"}:
                    if bit_values[bit_idx] != event.char:
                        bit_values[bit_idx] = event.char
                        bit_var.set(event.char)
                        _emit_bits_change()
                    if bit_idx < len(entries) - 1:
                        _focus_entry(bit_idx + 1)
                    return "break"

                if event.keysym in {"BackSpace", "Delete"}:
                    if bit_values[bit_idx] != "0":
                        bit_values[bit_idx] = "0"
                        bit_var.set("0")
                        _emit_bits_change()
                    if event.keysym == "BackSpace" and bit_idx > 0:
                        _focus_entry(bit_idx - 1)
                    return "break"

                return "break"

            bit_entry.bind("<KeyPress>", _on_key, add=True)
            bit_entry.bind("<FocusIn>", lambda _e, v=bit_var: v.set(v.get()[:1] or "0"), add=True)

    def render(
        self,
        bit_text: str,
        role_boundaries: tuple[int, ...] = (),
        line_break_before: int | None = None,
        *,
        editable: bool = False,
        on_bits_change: Callable[[str], None] | None = None,
    ) -> None:
        if line_break_before is not None and not (0 < line_break_before < len(bit_text)):
            line_break_before = None

        self._active_on_bits_change = on_bits_change
        self._last_role_boundaries = role_boundaries
        self._last_line_break_before = line_break_before
        self._last_editable = editable

        render_key = (bit_text, role_boundaries, line_break_before, editable)
        if self._render_cache == render_key:
            return
        self._render_cache = render_key
        self._current_bit_text = bit_text
        bit_values = list(bit_text)
        entries: list[tk.Entry | None] = [None] * len(bit_text)

        for child in self.inner.winfo_children():
            child.destroy()

        if line_break_before is None:
            row = tk.Frame(self.inner, bg="#ffffff")
            row.pack(anchor="w")
            self._render_row(
                row,
                bit_text,
                role_boundaries,
                0,
                len(bit_text),
                skip_leading_separator=False,
                editable=editable,
                entries=entries,
                bit_values=bit_values,
            )
            self.canvas.configure(height=BITGRID_SINGLE_ROW_HEIGHT)
            return

        first_row = tk.Frame(self.inner, bg="#ffffff")
        first_row.pack(anchor="w")
        second_row = tk.Frame(self.inner, bg="#ffffff")
        second_row.pack(anchor="w")

        self._render_row(
            first_row,
            bit_text,
            role_boundaries,
            0,
            line_break_before,
            skip_leading_separator=False,
            editable=editable,
            entries=entries,
            bit_values=bit_values,
        )
        self._render_row(
            second_row,
            bit_text,
            role_boundaries,
            line_break_before,
            len(bit_text),
            skip_leading_separator=True,
            editable=editable,
            entries=entries,
            bit_values=bit_values,
        )
        self.canvas.configure(height=BITGRID_DOUBLE_ROW_HEIGHT)

    def current_bit_text(self) -> str:
        return self._current_bit_text


def _make_copyable_entry(
    parent: tk.Widget,
    variable: tk.StringVar,
    bg: str,
    width: int = 1,
    *,
    takefocus: bool = True,
) -> tk.Entry:
    entry = tk.Entry(
        parent,
        textvariable=variable,
        relief="flat",
        bd=0,
        highlightthickness=0,
        font=VALUE_FONT,
        fg="#1f2d3d",
        bg=bg,
        readonlybackground=bg,
        width=width,
        takefocus=1 if takefocus else 0,
    )
    entry.configure(state="readonly")
    return entry


class IntegerVisualizerFrame(tk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, bg="#f5f7fa")

        self.type_var = tk.StringVar(value="int32_t")
        self.decimal_var = tk.StringVar(value="0")
        self.status_var = tk.StringVar(value="Enter a decimal integer to inspect bit layout.")
        self._hover_text = ""

        self._build_ui()

        self.type_var.trace_add("write", self._on_change)
        self.decimal_var.trace_add("write", self._on_change)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Return>", self._on_focus_out)
        self.entry.bind("<Control-u>", self._on_ctrl_u_key)
        self.entry.bind("<Control-U>", self._on_ctrl_u_key)

        self._on_change()

    def _build_ui(self) -> None:
        controls = tk.Frame(self, bg="#f5f7fa")
        controls.pack(fill="x", padx=12, pady=(12, 8))

        style = ttk.Style(self)
        style.configure("Hdb.TCombobox", font=VALUE_FONT)

        tk.Label(
            controls,
            text="C++ Integer Type",
            bg="#f5f7fa",
            fg="#22313f",
            font=UI_FONT_BOLD,
        ).pack(side="left")

        type_combo = ttk.Combobox(
            controls,
            textvariable=self.type_var,
            values=list(INT_TYPE_SPECS.keys()),
            width=24,
            state="readonly",
            style="Hdb.TCombobox",
        )
        type_combo.pack(side="left", padx=(8, 16))

        tk.Label(
            controls,
            text="Decimal Input",
            bg="#f5f7fa",
            fg="#22313f",
            font=UI_FONT_BOLD,
        ).pack(side="left")

        self.entry = tk.Entry(
            controls,
            textvariable=self.decimal_var,
            width=28,
            font=ENTRY_FONT,
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#b8b8b8",
        )
        self.entry.pack(side="left", padx=(8, 0), fill="x", expand=True)
        self._default_bg = self.entry.cget("bg")

        summary = tk.Frame(self, bg="#f5f7fa")
        summary.pack(fill="x", padx=12)

        self.type_info_var = tk.StringVar()
        self.input_value_var = tk.StringVar()
        self.wrapped_value_var = tk.StringVar()
        self.signed_view_var = tk.StringVar()
        self.unsigned_view_var = tk.StringVar()
        self.bit_text_var = tk.StringVar()
        self.calc_var = tk.StringVar()

        self._build_value_row(summary, "Selected:", self.type_info_var)
        self._build_value_row(summary, "Input Decimal:", self.input_value_var)
        self.wrapped_value_entry = self._build_value_row(summary, "Wrapped Result:", self.wrapped_value_var)
        self._build_value_row(summary, "Signed View:", self.signed_view_var)
        self._build_value_row(summary, "Unsigned View:", self.unsigned_view_var)
        self._build_value_row(summary, "Bit Pattern:", self.bit_text_var)
        calc_label = self._build_value_row(summary, "Calculation:", self.calc_var)
        HoverExplain(calc_label, lambda: self._hover_text)

        self.bit_grid = BitGrid(self)
        self.bit_grid.pack(fill="x", padx=12, pady=(8, 8))

        status = tk.Label(
            self,
            textvariable=self.status_var,
            bg="#f5f7fa",
            fg="#3f5368",
            anchor="w",
            font=UI_FONT,
        )
        status.pack(fill="x", padx=12, pady=(0, 12))

    def _build_value_row(
        self,
        parent: tk.Widget,
        label: str,
        variable: tk.StringVar,
    ) -> tk.Entry:
        row = tk.Frame(parent, bg="#f5f7fa")
        row.pack(fill="x", pady=1)

        tk.Label(
            row,
            text=label,
            width=14,
            anchor="w",
            bg="#f5f7fa",
            fg="#34495e",
            font=UI_FONT_BOLD,
        ).pack(side="left")

        value_entry = _make_copyable_entry(row, variable, bg="#f5f7fa")
        value_entry.pack(side="left", fill="x", expand=True, padx=(2, 0))
        return value_entry

    def _set_invalid(self, is_invalid: bool) -> None:
        if is_invalid:
            self.entry.configure(
                bg="#ffeaea",
                highlightthickness=2,
                highlightbackground="#cc4444",
            )
        else:
            self.entry.configure(
                bg=self._default_bg,
                highlightthickness=1,
                highlightbackground="#b8b8b8",
            )

    def _parse_integer_input(self) -> int:
        parsed = parse_decimal_input(self.decimal_var.get())
        if parsed.is_nan() or parsed in {Decimal("Infinity"), Decimal("-Infinity")}:
            raise ValueError("Integer mode only accepts finite values.")
        if parsed != parsed.to_integral_value():
            raise ValueError("Integer mode requires a whole number.")
        return int(parsed)

    def _on_focus_out(self, _event: tk.Event) -> None:
        try:
            value = self._parse_integer_input()
        except ValueError:
            return
        self.decimal_var.set(f"{value:_}")

    @staticmethod
    def _on_ctrl_u_key(event: tk.Event) -> str:
        widget = event.widget
        if isinstance(widget, tk.Entry):
            cursor_index = widget.index(tk.INSERT)
            widget.delete(0, cursor_index)
        return "break"

    def _on_change(self, *_args) -> None:
        spec = INT_TYPE_SPECS[self.type_var.get()]
        try:
            value = self._parse_integer_input()
        except ValueError as exc:
            self._set_invalid(True)
            self.status_var.set(str(exc))
            return

        self._set_invalid(False)

        wrapped, overflow, underflow = int_wrap_and_flags(value, spec)
        bit_text = int_bits(wrapped, spec.bits)

        unsigned_value = int(bit_text, 2)
        signed_value = (
            unsigned_value
            if bit_text[0] == "0"
            else unsigned_value - (1 << spec.bits)
        )

        wrapped_view = signed_value if spec.signed else unsigned_value

        self.type_info_var.set(
            f"{spec.name} ({'signed' if spec.signed else 'unsigned'}, {spec.bits}-bit)"
        )
        self.input_value_var.set(f"{value}")
        self.wrapped_value_var.set(f"{wrapped_view}")
        self.signed_view_var.set(f"{signed_value}")
        self.unsigned_view_var.set(f"{unsigned_value}")
        self.bit_text_var.set(bit_text)

        if overflow or underflow:
            self.wrapped_value_entry.configure(fg="#bf2a2a")
            self.calc_var.set(
                f"{value} mod 2^{spec.bits} = {unsigned_value} (active value wraps)"
            )
            self.status_var.set("Overflow/underflow detected; wrapped result highlighted.")
        else:
            self.wrapped_value_entry.configure(fg="#1f2d3d")
            self.calc_var.set(f"{value} fits in {spec.bits} bits without wrapping")
            self.status_var.set("Integer visualization updated.")

        min_value = -(1 << (spec.bits - 1)) if spec.signed else 0
        max_value = (1 << (spec.bits - 1)) - 1 if spec.signed else (1 << spec.bits) - 1
        self._hover_text = (
            f"Range for {spec.name}: [{min_value}, {max_value}]\n"
            f"Bit pattern interpreted as signed={signed_value}, unsigned={unsigned_value}."
        )

        self.bit_grid.render(bit_text)

    def focus_primary_input(self) -> None:
        self.entry.focus_set()
        self.entry.selection_range(0, tk.END)
        self.entry.icursor(tk.END)


class FloatVisualizerFrame(tk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, bg="#f5f7fa")

        self.decimal_var = tk.StringVar(value="0")
        self.status_var = tk.StringVar(value="Enter a decimal value to inspect IEEE-754 fields.")
        self.float_panels: dict[str, FloatResultPanel] = {}
        self._suspend_decimal_trace = False
        self._debounce_ms = 30
        self._debounce_after_id: str | None = None
        self._pending_value: Decimal | None = None
        self._pending_input_ts: float | None = None
        self._compute_request_id = 0
        self._last_submitted_input: str | None = None
        self._request_meta: dict[int, dict[str, float]] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hdb-float")
        self._focus_ring_entries: list[tk.Entry] = []

        self._build_ui()

        self.decimal_var.trace_add("write", self._on_change)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Return>", self._on_focus_out)
        self.entry.bind("<Control-u>", self._on_ctrl_u_key)
        self.entry.bind("<Control-U>", self._on_ctrl_u_key)

        self._on_change()

    def _build_ui(self) -> None:
        controls = tk.Frame(self, bg="#f5f7fa")
        controls.pack(fill="x", padx=12, pady=(12, 8))

        tk.Label(
            controls,
            text="Decimal Input",
            bg="#f5f7fa",
            fg="#22313f",
            font=UI_FONT_BOLD,
        ).pack(side="left")

        self.entry = tk.Entry(
            controls,
            textvariable=self.decimal_var,
            width=40,
            font=ENTRY_FONT,
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#b8b8b8",
        )
        self.entry.pack(side="left", padx=(8, 0), fill="x", expand=True)
        self._default_bg = self.entry.cget("bg")
        self._focus_ring_entries.append(self.entry)

        panels_host = tk.Frame(self, bg="#f5f7fa")
        panels_host.pack(fill="both", expand=True, padx=12, pady=(8, 8))

        top_row = tk.Frame(panels_host, bg="#f5f7fa")
        top_row.pack(fill="both", expand=True)
        half_cell = tk.Frame(top_row, bg="#f5f7fa")
        half_cell.pack(side="left", fill="both", expand=True, padx=(0, 6))
        single_cell = tk.Frame(top_row, bg="#f5f7fa")
        single_cell.pack(side="left", fill="both", expand=True, padx=(6, 0))

        bottom_row = tk.Frame(panels_host, bg="#f5f7fa")
        bottom_row.pack(fill="x")

        panel_hosts: dict[str, tk.Frame] = {
            "half": half_cell,
            "single": single_cell,
            "double": bottom_row,
        }

        for name in ("half", "single", "double"):
            spec = FLOAT_TYPE_SPECS[name]
            host = panel_hosts[name]
            panel = FloatResultPanel(
                host,
                spec,
                on_bit_fields_edit=(
                    lambda sign_bits, exponent_bits, mantissa_bits, panel_name=name: self._on_panel_bit_fields_edit(
                        panel_name, sign_bits, exponent_bits, mantissa_bits
                    )
                ),
            )
            panel.pack(fill="both", expand=(name != "double"), pady=6)
            self.float_panels[name] = panel
            self._focus_ring_entries.extend(panel.focus_entries())

        self._bind_tab_navigation_handlers()

        status = tk.Label(
            self,
            textvariable=self.status_var,
            bg="#f5f7fa",
            fg="#3f5368",
            anchor="w",
            font=UI_FONT,
        )
        status.pack(fill="x", padx=12, pady=(0, 12))

    def _set_invalid(self, is_invalid: bool) -> None:
        if is_invalid:
            self.entry.configure(
                bg="#ffeaea",
                highlightthickness=2,
                highlightbackground="#cc4444",
            )
        else:
            self.entry.configure(
                bg=self._default_bg,
                highlightthickness=1,
                highlightbackground="#b8b8b8",
            )

    def _on_focus_out(self, _event: tk.Event) -> None:
        try:
            parsed = parse_decimal_input(self.decimal_var.get())
        except ValueError:
            return

        if parsed.is_nan() or parsed in {Decimal("Infinity"), Decimal("-Infinity")}:
            self._set_decimal_text(str(parsed))
            return

        self._set_decimal_text(format(parsed, ".12g"))

    @staticmethod
    def _on_ctrl_u_key(event: tk.Event) -> str:
        widget = event.widget
        if isinstance(widget, tk.Entry):
            cursor_index = widget.index(tk.INSERT)
            widget.delete(0, cursor_index)
        return "break"

    def _on_change(self, *_args) -> None:
        if self._suspend_decimal_trace:
            return
        try:
            value = parse_decimal_input(self.decimal_var.get())
        except ValueError as exc:
            self._set_invalid(True)
            if self._debounce_after_id is not None:
                self.after_cancel(self._debounce_after_id)
                self._debounce_after_id = None
            self._pending_value = None
            self._pending_input_ts = None
            self._compute_request_id += 1
            self.status_var.set(str(exc))
            return

        self._set_invalid(False)
        self._pending_value = value
        self._pending_input_ts = time.perf_counter()
        if self._debounce_after_id is not None:
            self.after_cancel(self._debounce_after_id)
        self._debounce_after_id = self.after(self._debounce_ms, self._dispatch_compute)
        self.status_var.set("Float visualization updating...")

    def _set_decimal_text(self, text: str) -> None:
        self._suspend_decimal_trace = True
        try:
            self.decimal_var.set(text)
        finally:
            self._suspend_decimal_trace = False

    @staticmethod
    def _decimal_text_for_value(value: Decimal) -> str:
        if value.is_nan() or value in {Decimal("Infinity"), Decimal("-Infinity")}:
            return str(value)
        return format(value, ".12g")

    def _on_panel_bit_fields_edit(
        self,
        panel_name: str,
        sign_bits: str,
        exponent_bits: str,
        mantissa_bits: str,
    ) -> None:
        spec = FLOAT_TYPE_SPECS[panel_name]

        if len(sign_bits) != 1 or len(exponent_bits) != spec.exponent_bits or len(mantissa_bits) != spec.mantissa_bits:
            self.status_var.set(
                f"Editing {spec.name}: sign {len(sign_bits)}/1, "
                f"exponent {len(exponent_bits)}/{spec.exponent_bits}, "
                f"mantissa {len(mantissa_bits)}/{spec.mantissa_bits}"
            )
            return

        bit_text = f"{sign_bits}{exponent_bits}{mantissa_bits}"

        if self._debounce_after_id is not None:
            self.after_cancel(self._debounce_after_id)
            self._debounce_after_id = None
        self._pending_value = None
        self._pending_input_ts = None
        self._compute_request_id += 1
        self._last_submitted_input = None

        try:
            source_fields = float_fields_from_bit_text(bit_text, spec)
        except ValueError as exc:
            self.status_var.set(str(exc))
            return

        shared_value = Decimal.from_float(float(source_fields["quantized"]))
        results = build_all_float_panel_display_data(shared_value)
        for name, panel in self.float_panels.items():
            data = results.get(name)
            if data is None:
                continue
            panel.apply_display_data(data)

        self._set_invalid(False)
        self._set_decimal_text(self._decimal_text_for_value(shared_value))
        self.status_var.set(f"Synchronized all float formats from {spec.name} bit fields.")

    @staticmethod
    def _compute_payload_timed(
        value: Decimal,
    ) -> tuple[dict[str, dict[str, Any]], float]:
        start = time.perf_counter()
        payload = build_all_float_panel_display_data(value)
        compute_ms = (time.perf_counter() - start) * 1000.0
        return payload, compute_ms

    def _dispatch_compute(self) -> None:
        self._debounce_after_id = None
        if self._pending_value is None:
            return

        value = self._pending_value
        input_ts = self._pending_input_ts
        if input_ts is None:
            input_ts = time.perf_counter()
        normalized = str(value)
        if normalized == self._last_submitted_input:
            self.status_var.set("Float visualization updated.")
            return

        self._last_submitted_input = normalized
        self._compute_request_id += 1
        request_id = self._compute_request_id
        submit_ts = time.perf_counter()
        self._request_meta[request_id] = {
            "input_ts": input_ts,
            "submit_ts": submit_ts,
        }

        future = self._executor.submit(self._compute_payload_timed, value)
        future.add_done_callback(
            lambda done, rid=request_id: self._schedule_result_apply(rid, done)
        )

    def _schedule_result_apply(
        self,
        request_id: int,
        future: Future[tuple[dict[str, dict[str, Any]], float]],
    ) -> None:
        done_ts = time.perf_counter()
        try:
            self.after(0, self._apply_compute_result, request_id, future, done_ts)
        except tk.TclError:
            return

    def _apply_compute_result(
        self,
        request_id: int,
        future: Future[tuple[dict[str, dict[str, Any]], float]],
        done_ts: float,
    ) -> None:
        if not self.winfo_exists():
            return
        meta = self._request_meta.pop(request_id, None)
        if request_id != self._compute_request_id:
            if meta is not None:
                total_ms = (time.perf_counter() - meta["input_ts"]) * 1000.0
                print(
                    f"[hdb][float-timing] req={request_id} dropped=stale total_ms={total_ms:.2f}",
                    flush=True,
                )
            return

        try:
            results, compute_ms = future.result()
        except Exception as exc:
            self.status_var.set(f"Float compute failed: {exc}")
            return

        apply_start = time.perf_counter()
        for name, panel in self.float_panels.items():
            data = results.get(name)
            if data is None:
                continue
            panel.apply_display_data(data)
        self.status_var.set("Float visualization updated.")
        apply_end = time.perf_counter()

        if meta is not None:
            debounce_ms = (meta["submit_ts"] - meta["input_ts"]) * 1000.0
            queue_ms = (apply_start - done_ts) * 1000.0
            apply_ms = (apply_end - apply_start) * 1000.0
            total_ms = (apply_end - meta["input_ts"]) * 1000.0
            print(
                (
                    "[hdb][float-timing] "
                    f"req={request_id} debounce_ms={debounce_ms:.2f} "
                    f"compute_ms={compute_ms:.2f} queue_ms={queue_ms:.2f} "
                    f"apply_ms={apply_ms:.2f} total_ms={total_ms:.2f}"
                ),
                flush=True,
            )

    def focus_primary_input(self) -> None:
        self._focus_without_selection(self.entry)

    def _bind_tab_navigation_handlers(self) -> None:
        for entry in self._focus_ring_entries:
            entry.bind("<Tab>", self._on_entry_tab, add=True)
            entry.bind("<Shift-Tab>", self._on_entry_shift_tab, add=True)
            entry.bind("<ISO_Left_Tab>", self._on_entry_shift_tab, add=True)

    def _on_entry_tab(self, event: tk.Event) -> str:
        return self.cycle_entry_focus(reverse=False, widget=event.widget)

    def _on_entry_shift_tab(self, event: tk.Event) -> str:
        return self.cycle_entry_focus(reverse=True, widget=event.widget)

    @staticmethod
    def _focus_without_selection(entry: tk.Entry) -> None:
        entry.focus_set()
        try:
            entry.selection_clear()
            entry.icursor(tk.END)
        except tk.TclError:
            return
        try:
            entry.after_idle(entry.selection_clear)
        except tk.TclError:
            pass

    def _active_focus_ring(self) -> list[tk.Entry]:
        return [entry for entry in self._focus_ring_entries if entry.winfo_exists()]

    def cycle_entry_focus(self, reverse: bool, widget: object | None = None) -> str:
        entries = self._active_focus_ring()
        if not entries:
            return "break"

        current_entry: tk.Entry | None = None
        if isinstance(widget, tk.Entry) and widget in entries:
            current_entry = widget
        else:
            focused = self.focus_get()
            if isinstance(focused, tk.Entry) and focused in entries:
                current_entry = focused

        if current_entry is None:
            target = entries[-1] if reverse else entries[0]
        else:
            current_index = entries.index(current_entry)
            step = -1 if reverse else 1
            target = entries[(current_index + step) % len(entries)]

        if current_entry is not None:
            try:
                current_entry.selection_clear()
            except tk.TclError:
                pass
        self._focus_without_selection(target)
        return "break"

    def destroy(self) -> None:
        if self._debounce_after_id is not None:
            try:
                self.after_cancel(self._debounce_after_id)
            except tk.TclError:
                pass
            self._debounce_after_id = None
        self._executor.shutdown(wait=False, cancel_futures=True)
        super().destroy()


class FloatResultPanel(tk.LabelFrame):
    def __init__(
        self,
        parent: tk.Widget,
        spec: FloatTypeSpec,
        on_bit_fields_edit: Callable[[str, str, str], None] | None = None,
    ) -> None:
        super().__init__(
            parent,
            text=f"{spec.name.title()} ({spec.bits}-bit)",
            font=PANEL_TITLE_FONT,
            bg="#ffffff",
            fg="#22313f",
            bd=1,
            relief="solid",
            padx=10,
            pady=8,
        )
        self.spec = spec
        self._on_bit_fields_edit = on_bit_fields_edit
        self._programmatic_bit_update = False

        self.quantized_value_var = tk.StringVar()
        self.classification_var = tk.StringVar()
        self.abs_error_var = tk.StringVar()
        self.ulp_size_var = tk.StringVar()
        self.bit_text_var = tk.StringVar()
        self.sign_bits_var = tk.StringVar(value="0")
        self.exponent_bits_var = tk.StringVar(value="0" * spec.exponent_bits)
        self.mantissa_bits_var = tk.StringVar(value="0" * spec.mantissa_bits)
        self.sign_factor_var = tk.StringVar(value="(-1)^0 = 1")
        self.exponent_factor_var = tk.StringVar(value="")
        self.mantissa_factor_var = tk.StringVar(value="")
        self.sign_bits_entry: tk.Entry | None = None
        self.exponent_bits_entry: tk.Entry | None = None
        self.mantissa_bits_entry: tk.Entry | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        summary = tk.Frame(self, bg="#ffffff")
        summary.pack(fill="x")

        self._build_value_row(summary, "Quantized:", self.quantized_value_var)
        self._build_value_row(summary, "Class:", self.classification_var)
        self._build_value_row(summary, "Abs Error:", self.abs_error_var)
        self._build_value_row(summary, "ULP Size:", self.ulp_size_var)
        self._build_value_row(summary, "Bit Pattern:", self.bit_text_var)

        editor = tk.Frame(self, bg="#ffffff")
        editor.pack(fill="x", pady=(8, 0))
        self.sign_bits_entry = self._build_bit_row(
            editor,
            "Sign:",
            self.sign_bits_var,
            1,
            self.sign_factor_var,
        )
        self.exponent_bits_entry = self._build_bit_row(
            editor,
            "Exponent:",
            self.exponent_bits_var,
            self.spec.exponent_bits,
            self.exponent_factor_var,
        )
        self.mantissa_bits_entry = self._build_bit_row(
            editor,
            "Mantissa:",
            self.mantissa_bits_var,
            self.spec.mantissa_bits,
            self.mantissa_factor_var,
        )

        self.sign_bits_var.trace_add("write", self._on_bit_fields_change)
        self.exponent_bits_var.trace_add("write", self._on_bit_fields_change)
        self.mantissa_bits_var.trace_add("write", self._on_bit_fields_change)

    def _build_value_row(
        self,
        parent: tk.Widget,
        label: str,
        variable: tk.StringVar,
    ) -> tk.Entry:
        row = tk.Frame(parent, bg="#ffffff")
        row.pack(fill="x", pady=1)

        tk.Label(
            row,
            text=label,
            width=12,
            anchor="w",
            bg="#ffffff",
            fg="#34495e",
            font=UI_FONT_BOLD,
        ).pack(side="left")

        value_entry = _make_copyable_entry(row, variable, bg="#ffffff")
        value_entry.pack(side="left", fill="x", expand=True, padx=(2, 0))
        return value_entry

    def _build_bit_row(
        self,
        parent: tk.Widget,
        label: str,
        variable: tk.StringVar,
        bit_count: int,
        factor_var: tk.StringVar,
    ) -> tk.Entry:
        row = tk.Frame(parent, bg="#ffffff")
        row.pack(fill="x", pady=1)

        tk.Label(
            row,
            text=label,
            width=12,
            anchor="w",
            bg="#ffffff",
            fg="#34495e",
            font=UI_FONT_BOLD,
        ).pack(side="left")

        field_stack = tk.Frame(row, bg="#ffffff")
        field_stack.pack(side="left", padx=(2, 0))
        entry = tk.Entry(
            field_stack,
            textvariable=variable,
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#b8b8b8",
            font=BIT_FIELD_FONT,
            width=max(bit_count, 1),
        )
        entry.pack(side="top", anchor="w")
        index_canvases = self._build_bit_index_guides(field_stack, bit_count)
        self._bind_bit_index_guides(entry, index_canvases, bit_count)
        factor_entry = _make_copyable_entry(
            row,
            factor_var,
            bg="#ffffff",
            width=48,
            takefocus=False,
        )
        factor_entry.pack(side="left", fill="x", expand=True, padx=(10, 0))

        def _replace_bit(bit_index: int, replacement: str) -> None:
            bits = self._sanitize_bits(variable.get(), bit_count)
            bit_index = max(0, min(bit_index, bit_count - 1))
            variable.set(bits[:bit_index] + replacement + bits[bit_index + 1 :])

        def _on_keypress(event: tk.Event) -> str | None:
            if event.keysym in {"Tab", "ISO_Left_Tab", "Left", "Right", "Home", "End"}:
                return None

            # Keep clipboard shortcuts working.
            if event.state & 0x4:
                return None

            cursor = entry.index(tk.INSERT)
            if event.char in {"0", "1"}:
                if cursor >= bit_count:
                    bits = self._sanitize_bits(variable.get(), bit_count)
                    variable.set(self._insert_at_end_with_left_shift(bits, event.char))
                    entry.icursor(bit_count)
                    return "break"
                _replace_bit(cursor, event.char)
                entry.icursor(min(cursor + 1, bit_count))
                return "break"

            if event.keysym == "BackSpace":
                target = max(cursor - 1, 0)
                _replace_bit(target, "0")
                entry.icursor(target)
                return "break"

            if event.keysym == "Delete":
                target = min(cursor, bit_count - 1)
                _replace_bit(target, "0")
                entry.icursor(target)
                return "break"

            return "break"

        entry.bind("<KeyPress>", _on_keypress, add=True)
        return entry

    def focus_entries(self) -> list[tk.Entry]:
        entries = [
            self.sign_bits_entry,
            self.exponent_bits_entry,
            self.mantissa_bits_entry,
        ]
        return [entry for entry in entries if isinstance(entry, tk.Entry)]

    @staticmethod
    def _sanitize_bits(text: str, bit_count: int) -> str:
        filtered = "".join(ch for ch in text if ch in {"0", "1"})
        if len(filtered) >= bit_count:
            return filtered[:bit_count]
        return filtered + ("0" * (bit_count - len(filtered)))

    @staticmethod
    def _bit_index_tokens(bit_count: int, width: int = 2) -> list[str]:
        if bit_count <= 0:
            return []
        token_width = max(1, width)
        return [f"{idx:>{token_width}d}" for idx in range(bit_count - 1, -1, -1)]

    def _build_bit_index_guides(self, parent: tk.Widget, bit_count: int) -> list[tk.Canvas]:
        if bit_count <= 0:
            return []
        canvases: list[tk.Canvas] = []
        canvas = tk.Canvas(
            parent,
            bg="#ffffff",
            bd=0,
            highlightthickness=0,
            height=BIT_INDEX_ROW_HEIGHT,
        )
        canvas.pack(side="top", fill="x", anchor="w")
        canvases.append(canvas)
        return canvases

    def _bind_bit_index_guides(
        self,
        entry: tk.Entry,
        canvases: list[tk.Canvas],
        bit_count: int,
    ) -> None:
        if bit_count <= 0 or not canvases:
            return
        tokens = self._bit_index_tokens(bit_count, width=2)
        bit_font = tkfont.Font(font=BIT_FIELD_FONT)
        min_width = max(1, bit_font.measure("0") * bit_count)
        canvas = canvases[0]

        def _render(_event: tk.Event | None = None) -> None:
            width = max(entry.winfo_width(), min_width)
            cell_width = width / bit_count
            canvas.configure(width=width)
            canvas.delete("all")
            for col, token in enumerate(tokens):
                x = (col + 0.5) * cell_width
                canvas.create_text(
                    x,
                    BIT_INDEX_ROW_HEIGHT / 2,
                    text=token,
                    fill="#c0392b",
                    font=BIT_INDEX_FONT,
                )

        entry.bind("<Configure>", _render, add=True)
        entry.after_idle(_render)

    @staticmethod
    def _insert_at_end_with_left_shift(bits: str, incoming_bit: str) -> str:
        if not bits:
            return incoming_bit
        return bits[1:] + incoming_bit

    def _set_bit_fields(self, sign_bits: str, exponent_bits: str, mantissa_bits: str) -> None:
        self._programmatic_bit_update = True
        try:
            self.sign_bits_var.set(sign_bits)
            self.exponent_bits_var.set(exponent_bits)
            self.mantissa_bits_var.set(mantissa_bits)
        finally:
            self._programmatic_bit_update = False

    def _set_factor_text(
        self,
        sign_bits: str,
        exponent_bits: str,
        mantissa_bits: str,
        classification: str,
    ) -> None:
        sign = int(sign_bits, 2)
        exponent_raw = int(exponent_bits, 2)
        mantissa_raw = int(mantissa_bits, 2)
        bias = (1 << (self.spec.exponent_bits - 1)) - 1
        sign_value = "-1" if sign == 1 else "1"
        mantissa_denominator = Decimal(2) ** self.spec.mantissa_bits
        mantissa_term = Decimal(mantissa_raw) / mantissa_denominator

        self.sign_factor_var.set(f"(-1)^{sign} = {sign_value}")

        if classification == "normal":
            unbiased = exponent_raw - bias
            self.exponent_factor_var.set(
                f"2^({exponent_raw}-{bias}) = 2^{unbiased}"
            )
            self.mantissa_factor_var.set(
                f"1 + {mantissa_raw}/2^{self.spec.mantissa_bits} = "
                f"{self._format_factor_decimal(Decimal(1) + mantissa_term)}"
            )
            return

        if classification == "subnormal":
            self.exponent_factor_var.set(f"2^(1-{bias}) = 2^{1 - bias}")
            self.mantissa_factor_var.set(
                f"{mantissa_raw}/2^{self.spec.mantissa_bits} = "
                f"{self._format_factor_decimal(mantissa_term)}"
            )
            return

        if classification in {"+0", "-0"}:
            self.exponent_factor_var.set("zero case")
            self.mantissa_factor_var.set("0")
            return

        if classification in {"+inf", "-inf"}:
            self.exponent_factor_var.set(f"{exponent_raw} (all 1s)")
            self.mantissa_factor_var.set("0 -> infinity")
            return

        self.exponent_factor_var.set(f"{exponent_raw} (all 1s)")
        self.mantissa_factor_var.set(
            f"{mantissa_raw}/2^{self.spec.mantissa_bits} (non-zero) -> NaN"
        )

    @staticmethod
    def _format_factor_decimal(value: Decimal) -> str:
        if value == 0:
            return "0"
        return format(value, ".17g")

    def _on_bit_fields_change(self, *_args) -> None:
        if self._programmatic_bit_update:
            return

        sign_bits = self._sanitize_bits(self.sign_bits_var.get(), 1)
        exponent_bits = self._sanitize_bits(self.exponent_bits_var.get(), self.spec.exponent_bits)
        mantissa_bits = self._sanitize_bits(self.mantissa_bits_var.get(), self.spec.mantissa_bits)

        if (
            sign_bits != self.sign_bits_var.get()
            or exponent_bits != self.exponent_bits_var.get()
            or mantissa_bits != self.mantissa_bits_var.get()
        ):
            self._set_bit_fields(sign_bits, exponent_bits, mantissa_bits)

        if self._on_bit_fields_edit is not None:
            self._on_bit_fields_edit(sign_bits, exponent_bits, mantissa_bits)

    def apply_display_data(self, data: dict[str, Any]) -> None:
        self.quantized_value_var.set(str(data["quantized_text"]))
        classification = str(data["classification"])
        self.classification_var.set(classification)
        self.abs_error_var.set(str(data["abs_error"]))
        self.ulp_size_var.set(str(data["ulp_size"]))
        bit_text = str(data["bit_text"])
        self.bit_text_var.set(bit_text)
        boundaries = tuple(data["role_boundaries"])
        mantissa_start = boundaries[-1] if boundaries else 1 + self.spec.exponent_bits
        sign_bits = bit_text[:1]
        exponent_bits = bit_text[1:mantissa_start]
        mantissa_bits = bit_text[mantissa_start:]
        self._set_bit_fields(sign_bits, exponent_bits, mantissa_bits)
        self._set_factor_text(sign_bits, exponent_bits, mantissa_bits, classification)
