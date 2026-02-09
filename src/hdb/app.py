from __future__ import annotations

import os
import signal
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from tkinter import ttk

from .visualizer import FloatVisualizerFrame, IntegerVisualizerFrame

UI_FONT = ("DejaVu Sans", 13)
UI_FONT_BOLD = ("DejaVu Sans", 13, "bold")
PANEL_TITLE_FONT = ("DejaVu Sans", 15, "bold")
ENTRY_FONT = ("DejaVu Sans Mono", 30, "bold")
COLUMN_DIGIT_FONT = ("DejaVu Sans Mono", 18, "bold")
COLUMN_POWER_FONT = ("DejaVu Sans Mono", 10)
COLUMN_DIGIT_FONT_WIDE = ("DejaVu Sans Mono", 19, "bold")
COLUMN_POWER_FONT_WIDE = ("DejaVu Sans Mono", 12)

BASES = {
    "bin": 2,
    "dec": 10,
    "hex": 16,
}

TITLES = {
    "bin": "Binary (Base 2)",
    "dec": "Decimal (Base 10)",
    "hex": "Hexadecimal (Base 16)",
}


def clean_input(text: str) -> str:
    return text.strip().replace("_", "").replace(" ", "")


def parse_value(text: str, base: int) -> int:
    cleaned = clean_input(text)
    if cleaned in {"", "+", "-"}:
        return 0
    return int(cleaned, base)


def group_from_right(digits: str, group_size: int) -> str:
    if not digits:
        return "0"
    parts: list[str] = []
    remaining = digits
    while remaining:
        parts.append(remaining[-group_size:])
        remaining = remaining[:-group_size]
    return "_".join(reversed(parts))


def format_value(value: int, base: int) -> str:
    if base == 10:
        return f"{value:_}"

    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    if base == 2:
        digits = format(magnitude, "b")
    elif base == 16:
        digits = format(magnitude, "X")
    else:
        raise ValueError(f"Unsupported base: {base}")

    return sign + group_from_right(digits, 4)


def format_source_text(text: str, base: int) -> str:
    cleaned = clean_input(text)
    if cleaned in {"", "+", "-"}:
        return text

    negative = cleaned.startswith("-")
    if cleaned[:1] in {"+", "-"}:
        cleaned = cleaned[1:]

    if not cleaned:
        cleaned = "0"

    if base == 2:
        grouped = group_from_right(cleaned, 4)
    elif base == 10:
        grouped = group_from_right(cleaned, 3)
    elif base == 16:
        grouped = group_from_right(cleaned.upper(), 4)
    else:
        raise ValueError(f"Unsupported base: {base}")

    return ("-" if negative else "") + grouped


@dataclass
class BasePanel:
    key: str
    base: int
    frame: tk.LabelFrame
    entry: tk.Entry
    copy_button: tk.Button
    canvas: tk.Canvas
    _default_bg: str
    _render_cache: tuple[bool, str] | None = None

    def set_invalid(self, is_invalid: bool) -> None:
        if is_invalid:
            self.entry.configure(
                bg="#ffeaea", highlightthickness=2, highlightbackground="#cc4444"
            )
        else:
            self.entry.configure(
                bg=self._default_bg, highlightthickness=1, highlightbackground="#b8b8b8"
            )

    def update_columns(self, number_text: str) -> None:
        cleaned = clean_input(number_text)
        negative = cleaned.startswith("-")
        if cleaned[:1] in {"+", "-"}:
            cleaned = cleaned[1:]
        if not cleaned:
            cleaned = "0"

        render_key = (negative, cleaned)
        if self._render_cache == render_key:
            return
        self._render_cache = render_key

        self.canvas.delete("all")

        y_top = 4
        if negative:
            self.canvas.create_text(
                8,
                y_top,
                anchor="nw",
                text="Negative value",
                fill="#aa3333",
                font=UI_FONT_BOLD,
            )
            y_top = 26

        total_digits = len(cleaned)
        if self.base == 2:
            # Compact binary layout: keeps 32 columns readable within the wider default window.
            col_width = 32
            col_gap = 1
            box_height = 64
            digit_font = COLUMN_DIGIT_FONT
            power_font = COLUMN_POWER_FONT
            digit_y_offset = 21
            power_y_offset = 49
        else:
            col_width = 46
            col_gap = 2
            box_height = 72
            digit_font = COLUMN_DIGIT_FONT_WIDE
            power_font = COLUMN_POWER_FONT_WIDE
            digit_y_offset = 25
            power_y_offset = 57

        max_power = max(0, total_digits - 1)
        widest_power_text = f"{self.base}^{max_power}"
        power_font_obj = tkfont.Font(font=power_font)
        col_width = max(col_width, power_font_obj.measure(widest_power_text) + 8)

        x_padding = 6

        for idx, digit in enumerate(cleaned):
            power = total_digits - 1 - idx
            x0 = x_padding + (idx * (col_width + col_gap))
            x1 = x0 + col_width
            y0 = y_top
            y1 = y_top + box_height

            self.canvas.create_rectangle(x0, y0, x1, y1, outline="#7f8c8d", width=1)
            self.canvas.create_text(
                (x0 + x1) / 2,
                y0 + digit_y_offset,
                text=digit,
                font=digit_font,
                fill="#1f2d3d",
            )
            self.canvas.create_text(
                (x0 + x1) / 2,
                y0 + power_y_offset,
                text=f"{self.base}^{power}",
                font=power_font,
                fill="#34495e",
            )

        total_width = max(200, x_padding + (total_digits * (col_width + col_gap)) + 8)
        total_height = y_top + box_height + 4
        self.canvas.configure(
            scrollregion=(0, 0, total_width, total_height),
            height=total_height,
        )


class BaseConverterApp(tk.Tk):
    def __init__(self) -> None:
        # Disable Tk input methods early to avoid noisy fabricated-key logs on some Linux builds.
        os.environ.setdefault("TK_NO_INPUT_METHODS", "1")
        super().__init__()
        self._disable_input_methods()
        self.title("hdb Datatype Visualizer")
        self.geometry("1400x980")
        self.minsize(1100, 760)
        self.configure(bg="#f5f7fa")
        self.option_add("*TCombobox*Listbox.font", "DejaVu Sans Mono 13")

        self._programmatic = False
        self._history_replaying = False
        self.vars = {key: tk.StringVar(value="0") for key in BASES}
        self.panels: dict[str, BasePanel] = {}
        self.history: dict[str, list[str]] = {key: ["0"] for key in BASES}
        self.history_pos: dict[str, int] = {key: 0 for key in BASES}
        self.entry_order = ("bin", "dec", "hex")
        self.status_var = tk.StringVar(
            value="Type in any field to convert in real time."
        )

        self._build_ui()
        self._wire_events()
        self._install_signal_handlers()
        self._update_from_source("dec")
        self.after(10, lambda: self._select_tab(0))

    def _disable_input_methods(self) -> None:
        try:
            self.tk.call("tk", "useinputmethods", False)
        except tk.TclError:
            # Not available on all platforms/windowing systems.
            pass

    def _build_ui(self) -> None:
        root = tk.Frame(self, bg="#f5f7fa")
        root.pack(fill="both", expand=True, padx=12, pady=10)

        style = ttk.Style(self)
        style.configure("Hdb.TNotebook", tabposition="n")
        style.configure(
            "Hdb.TNotebook.Tab",
            font=("DejaVu Sans", 10, "bold"),
            padding=(8, 4),
            anchor="w",
        )

        self.notebook = ttk.Notebook(root, style="Hdb.TNotebook")
        self.notebook.pack(fill="both", expand=True)

        converter_tab = tk.Frame(self.notebook, bg="#f5f7fa")
        integer_tab = tk.Frame(self.notebook, bg="#f5f7fa")
        float_tab = tk.Frame(self.notebook, bg="#f5f7fa")

        self.notebook.add(converter_tab, text="Base Converter")
        self.notebook.add(integer_tab, text="Integer Visualizer")
        self.notebook.add(float_tab, text="Float Visualizer")

        self._build_converter_tab(converter_tab)

        self.integer_visualizer = IntegerVisualizerFrame(integer_tab)
        self.integer_visualizer.pack(fill="both", expand=True)

        self.float_visualizer = FloatVisualizerFrame(float_tab)
        self.float_visualizer.pack(fill="both", expand=True)

    def _build_converter_tab(self, parent: tk.Widget) -> None:
        for key in ("bin", "dec", "hex"):
            panel = self._build_panel(parent, key)
            panel.frame.pack(fill="x", pady=8)
            self.panels[key] = panel

        status_bar = tk.Label(
            parent,
            textvariable=self.status_var,
            bg="#f5f7fa",
            fg="#3f5368",
            anchor="w",
            font=UI_FONT,
        )
        status_bar.pack(fill="x", pady=(8, 0))

    def _build_panel(self, parent: tk.Widget, key: str) -> BasePanel:
        frame = tk.LabelFrame(
            parent,
            text=TITLES[key],
            font=PANEL_TITLE_FONT,
            bg="#ffffff",
            fg="#22313f",
            bd=1,
            relief="solid",
            padx=10,
            pady=8,
        )

        entry_row = tk.Frame(frame, bg="#ffffff")
        entry_row.pack(fill="x")

        entry = tk.Entry(
            entry_row,
            textvariable=self.vars[key],
            font=ENTRY_FONT,
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground="#b8b8b8",
            insertwidth=4,
        )
        entry.pack(side="left", fill="x", expand=True)

        copy_button = tk.Button(
            entry_row,
            text="Copy",
            command=lambda entry_key=key: self._copy_value(entry_key),
            font=UI_FONT_BOLD,
            padx=14,
            pady=10,
            bd=1,
            relief="solid",
            highlightthickness=0,
            cursor="hand2",
            takefocus=False,
        )
        copy_button.pack(side="left", padx=(8, 0))

        canvas = tk.Canvas(
            frame,
            bg="#fcfdff",
            height=76,
            bd=1,
            relief="solid",
            highlightthickness=0,
            takefocus=False,
        )
        canvas.pack(fill="x")

        return BasePanel(
            key=key,
            base=BASES[key],
            frame=frame,
            entry=entry,
            copy_button=copy_button,
            canvas=canvas,
            _default_bg=entry.cget("bg"),
        )

    def _wire_events(self) -> None:
        for key, var in self.vars.items():
            var.trace_add("write", self._make_change_handler(key))
            panel = self.panels[key]
            panel.entry.bind("<FocusOut>", self._make_focus_out_handler(key))
            panel.entry.bind("<Return>", self._make_focus_out_handler(key))
            panel.entry.bind("<KeyPress-C>", self._make_copy_key_handler(key))
            panel.entry.bind("<Control-c>", self._make_copy_key_handler(key))
            panel.entry.bind("<Control-C>", self._make_copy_key_handler(key))
            panel.entry.bind("<Control-u>", self._on_ctrl_u_key)
            panel.entry.bind("<Control-U>", self._on_ctrl_u_key)
            panel.entry.bind("<Control-z>", self._on_ctrl_z_key)
            panel.entry.bind("<Control-Z>", self._on_ctrl_z_key)
            panel.entry.bind("<Control-Shift-z>", self._on_ctrl_shift_z_key)
            panel.entry.bind("<Control-Shift-Z>", self._on_ctrl_shift_z_key)
        self.bind_all("<Tab>", self._on_tab_key, add=True)
        self.bind_all("<Shift-Tab>", self._on_shift_tab_key, add=True)
        self.bind_all("<ISO_Left_Tab>", self._on_shift_tab_key, add=True)
        self.bind_all("<Escape>", self._on_escape_quit, add=True)
        self.bind_all("<Control-Key-1>", self._on_ctrl_1_tab, add=True)
        self.bind_all("<Control-Key-2>", self._on_ctrl_2_tab, add=True)
        self.bind_all("<Control-Key-3>", self._on_ctrl_3_tab, add=True)
        self._bind_escape_on_inputs()

    def _bind_escape_on_inputs(self) -> None:
        def _attach(widget: tk.Widget) -> None:
            if isinstance(widget, (tk.Entry, ttk.Combobox, tk.Text, tk.Spinbox)):
                widget.bind("<Escape>", self._on_escape_quit, add=True)
            for child in widget.winfo_children():
                _attach(child)

        _attach(self)

    def _install_signal_handlers(self) -> None:
        def _on_sigint(_signum: int, _frame: object) -> None:
            self.after(0, self._quit_app)

        signal.signal(signal.SIGINT, _on_sigint)

    def _make_change_handler(self, key: str):
        def _handler(*_args) -> None:
            if not self._programmatic:
                self._update_from_source(key)

        return _handler

    def _make_focus_out_handler(self, key: str):
        def _handler(_event) -> None:
            try:
                parse_value(self.vars[key].get(), BASES[key])
            except ValueError:
                return
            self._programmatic = True
            self.vars[key].set(format_source_text(self.vars[key].get(), BASES[key]))
            self._programmatic = False
            self._update_from_source(key)

        return _handler

    def _make_copy_key_handler(self, key: str):
        def _handler(_event: tk.Event) -> str:
            self._copy_value(key)
            return "break"

        return _handler

    def _on_ctrl_u_key(self, event: tk.Event) -> str:
        widget = event.widget
        if isinstance(widget, tk.Entry):
            cursor_index = widget.index(tk.INSERT)
            widget.delete(0, cursor_index)
        return "break"

    def _on_ctrl_z_key(self, event: tk.Event) -> str:
        widget = event.widget
        key = self._entry_key_from_widget(widget)
        if key is not None:
            self._history_step(key=key, step=-1)
        return "break"

    def _on_ctrl_shift_z_key(self, event: tk.Event) -> str:
        widget = event.widget
        key = self._entry_key_from_widget(widget)
        if key is not None:
            self._history_step(key=key, step=1)
        return "break"

    def _push_history(self, key: str, text: str) -> None:
        if self._programmatic or self._history_replaying:
            return
        history = self.history[key]
        pos = self.history_pos[key]
        if history[pos] == text:
            return
        if pos < len(history) - 1:
            del history[pos + 1 :]
        history.append(text)
        if len(history) > 500:
            del history[: len(history) - 500]
        self.history_pos[key] = len(history) - 1

    def _history_step(self, key: str, step: int) -> None:
        current_pos = self.history_pos[key]
        next_pos = current_pos + step
        history = self.history[key]
        if next_pos < 0 or next_pos >= len(history):
            return

        self.history_pos[key] = next_pos
        self._history_replaying = True
        try:
            self._programmatic = True
            self.vars[key].set(history[next_pos])
            self._programmatic = False
            self._update_from_source(key)
        finally:
            self._history_replaying = False
        self.panels[key].entry.icursor(tk.END)

    def _quit_app(self) -> None:
        self.quit()
        self.destroy()

    def _copy_value(self, key: str) -> None:
        value = clean_input(self.vars[key].get())
        self.clipboard_clear()
        self.clipboard_append(value)
        self.status_var.set(
            f"Copied {TITLES[key].split()[0].lower()} value to clipboard."
        )

    def _focus_binary_entry(self) -> None:
        entry = self.panels["bin"].entry
        entry.focus_set()
        entry.selection_range(0, tk.END)
        entry.icursor(tk.END)

    def _focus_entry_by_key(self, key: str, *, select_text: bool = True) -> None:
        entry = self.panels[key].entry
        entry.focus_set()
        if select_text:
            entry.selection_range(0, tk.END)
        else:
            entry.selection_clear()
        entry.icursor(tk.END)

    def _entry_key_from_widget(self, widget: object) -> str | None:
        for key, panel in self.panels.items():
            if widget is panel.entry:
                return key
        return None

    @staticmethod
    def _logical_char_count(text: str, limit: int) -> int:
        count = 0
        for char in text[:limit]:
            if char not in {"_", " "}:
                count += 1
        return count

    @staticmethod
    def _cursor_index_from_logical_count(text: str, logical_count: int) -> int:
        if logical_count <= 0:
            return 0
        count = 0
        for idx, char in enumerate(text):
            if char not in {"_", " "}:
                count += 1
                if count >= logical_count:
                    return idx + 1
        return len(text)

    def _cycle_entry_focus(self, reverse: bool, widget: object | None = None) -> str:
        focused_key = self._entry_key_from_widget(widget)
        if focused_key is None:
            focused_widget = self.focus_get()
            focused_key = self._entry_key_from_widget(focused_widget)
        if focused_key is None:
            target_key = self.entry_order[-1] if reverse else self.entry_order[0]
            self._focus_entry_by_key(target_key, select_text=False)
            return "break"

        current_index = self.entry_order.index(focused_key)
        step = -1 if reverse else 1
        next_index = (current_index + step) % len(self.entry_order)
        self._focus_entry_by_key(self.entry_order[next_index], select_text=False)
        return "break"

    def _current_tab_index(self) -> int:
        selected = self.notebook.select()
        if not selected:
            return 0
        return int(self.notebook.index(selected))

    def _select_tab(self, index: int) -> None:
        self.notebook.select(index)
        if index == 0:
            self._focus_binary_entry()
            return
        if index == 1:
            self.integer_visualizer.focus_primary_input()
            return
        if index == 2:
            self.float_visualizer.focus_primary_input()

    def _on_ctrl_1_tab(self, _event: tk.Event) -> str:
        self._select_tab(0)
        return "break"

    def _on_ctrl_2_tab(self, _event: tk.Event) -> str:
        self._select_tab(1)
        return "break"

    def _on_ctrl_3_tab(self, _event: tk.Event) -> str:
        self._select_tab(2)
        return "break"

    def _on_tab_key(self, event: tk.Event) -> str | None:
        tab_index = self._current_tab_index()
        if tab_index == 0:
            return self._cycle_entry_focus(reverse=False, widget=event.widget)
        return None

    def _on_shift_tab_key(self, event: tk.Event) -> str | None:
        tab_index = self._current_tab_index()
        if tab_index == 0:
            return self._cycle_entry_focus(reverse=True, widget=event.widget)
        return None

    def _on_escape_quit(self, _event: tk.Event) -> str:
        self._quit_app()
        return "break"

    def _update_from_source(self, source_key: str) -> None:
        source_text = self.vars[source_key].get()
        try:
            value = parse_value(source_text, BASES[source_key])
        except ValueError:
            self._mark_invalid(source_key, source_text)
            self._push_history(source_key, source_text)
            return

        self._clear_invalid_state()
        self.status_var.set("Real-time conversion active.")

        formatted = {key: format_value(value, base) for key, base in BASES.items()}
        source_formatted = format_source_text(source_text, BASES[source_key])

        source_clean = clean_input(source_text)
        should_reformat_source = (
            source_clean not in {"", "+", "-"}
            and source_text != source_formatted
        )
        source_cursor_index = 0
        source_logical_count = 0
        source_cursor_at_end = False
        source_entry = self.panels[source_key].entry
        if should_reformat_source:
            source_cursor_index = source_entry.index(tk.INSERT)
            source_cursor_at_end = source_cursor_index == len(source_text)
            source_logical_count = self._logical_char_count(source_text, source_cursor_index)

        self._programmatic = True
        for key, text in formatted.items():
            if key != source_key:
                self.vars[key].set(text)
        if should_reformat_source:
            self.vars[source_key].set(source_formatted)
        self._programmatic = False
        if should_reformat_source:
            if source_cursor_at_end:
                new_cursor_index = len(source_formatted)
            else:
                new_cursor_index = self._cursor_index_from_logical_count(
                    source_formatted, source_logical_count
                )
            expected_text = source_formatted

            def _restore_cursor() -> None:
                if not source_entry.winfo_exists():
                    return
                if self.vars[source_key].get() != expected_text:
                    return
                source_entry.icursor(new_cursor_index)

            self.after_idle(_restore_cursor)

        self._push_history(source_key, self.vars[source_key].get())

        render_text = dict(formatted)
        render_text[source_key] = source_formatted
        for key, panel in self.panels.items():
            panel.update_columns(render_text[key])

    def _mark_invalid(self, source_key: str, current_text: str) -> None:
        for key, panel in self.panels.items():
            panel.set_invalid(key == source_key)
        self.status_var.set(
            f"Invalid {TITLES[source_key].split()[0].lower()} input: {current_text!r}"
        )

    def _clear_invalid_state(self) -> None:
        for panel in self.panels.values():
            panel.set_invalid(False)


def main() -> None:
    app = BaseConverterApp()
    app.mainloop()
