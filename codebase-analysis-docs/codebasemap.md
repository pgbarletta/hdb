# Codebase Map: `hdb` Datatype Visualizer

## 1. High-Level Overview
`hdb` is a Tkinter desktop application with three top-level notebook tabs:
- `Base Converter`
- `Integer Visualizer`
- `Float Visualizer`

Primary behavior contract:
- Base converter keeps binary/decimal/hexadecimal synchronized in real time.
- Base converter preserves leading zeros in the actively edited source field.
- Integer visualizer shows fixed-width and C++ native integer interpretations.
- Float visualizer has one shared decimal input and three concurrent result panels (`half`, `single`, `double`).
- Float visualizer layout places `half` and `single` side-by-side on the first row, with `double` on its own row below.
- Notebook tabs are the top-most widget in the main window.
- Typography is enlarged across primary controls and value rows for readability.
- Float panels expose editable bit fields (`sign`, `exponent`, `mantissa`) per format.
- Editing any float format synchronizes all float formats and the shared decimal value.
- Float bit-field editors are fixed-width and zero-filled; edits overwrite bits in place.
- Float bit-field editors include red per-bit index guides under each textbox.
- Horizontal scrollbar widgets are removed from base/visualizer panels.
- Visualizer value/formula rows are selectable and copyable.
- Invalid input remains localized to the active source field.

Primary entry paths:
- Console script `hdb` via `pyproject.toml` -> `hdb.app:main`
- Module execution `python -m hdb` via `src/hdb/__main__.py` -> `main()`

Referenced diagrams:
- `codebase-analysis-docs/assets/architecture-overview.mmd`
- `codebase-analysis-docs/assets/update-sequence.mmd`
- `codebase-analysis-docs/assets/keyboard-routing.mmd`

### PHASE 0 FILE INDEX (priority-scored)

| # | Priority | Path | Type | Notes |
|---|---:|---|---|---|
| 1 | 10 | `src/hdb/app.py` | runtime | Main window, notebook routing, base converter flow |
| 2 | 9 | `src/hdb/visualizer.py` | runtime | Integer/float visualizer tabs, per-format float result panels |
| 3 | 9 | `src/hdb/datatypes.py` | runtime | Integer/float specs, decomposition, ULP/error helpers |
| 4 | 8 | `README.md` | docs/contract | User-visible behavior and shortcuts |
| 5 | 8 | `pyproject.toml` | packaging | Entry points and runtime dependency (`numpy`) |
| 6 | 7 | `tests/test_app_base_converter_behavior.py` | tests | Base source-format preservation checks |
| 7 | 7 | `tests/test_datatypes.py` | tests | Integer and float backend checks |
| 8 | 7 | `tests/test_visualizer_behavior.py` | tests | Float formatting behavior checks |
| 9 | 6 | `src/hdb/__main__.py` | entry wrapper | `python -m hdb` launcher |
| 10 | 6 | `src/hdb/__init__.py` | package API | Export of `main` |

### STATE BLOCK (P0)
- `INDEX_VERSION`: `10`
- `FILE_MAP_SUMMARY`: Runtime logic is split across app shell, backend numeric helpers, and dedicated visualizer frames/panels.
- `OPEN QUESTIONS`: C++ native type widths (`long`, `unsigned long`) vary by platform and are runtime-resolved.
- `KNOWN RISKS`: `BaseConverterApp._update_from_source` remains high-sensitivity.
- `GLOSSARY_DELTA`: `ULP size`, `ULP error`, `float result panel`, `stale-result drop`.

## 2. Architecture & Event/Data Flow

### 2.1 Module architecture
- `src/hdb/app.py`
  - Base converter parsing/formatting helpers: `clean_input`, `parse_value`, `group_from_right`, `format_value`, `format_source_text`
  - Base UI dataclass: `BasePanel`
  - Main app shell: `BaseConverterApp`
  - Entrypoint: `main()`
- `src/hdb/datatypes.py`
  - Type metadata: `IntegerTypeSpec`, `FloatTypeSpec`, `INT_TYPE_SPECS`, `FLOAT_TYPE_SPECS`
  - Integer helpers: `parse_decimal_input`, `int_wrap_and_flags`, `int_bits`
  - Float helpers: `float_bits_and_fields`, `float_fields_from_bit_text`, `float_ulp_size`, `float_error_metrics`, `format_float_forward_calc`, `format_float_reverse_calc`, `format_ulp_error_formula`, `build_float_panel_display_data`, `build_float_panel_display_data_from_bits`, `build_all_float_panel_display_data`
- `src/hdb/visualizer.py`
  - UI components: `BitGrid`, `HoverExplain`, `IntegerVisualizerFrame`, `FloatVisualizerFrame`, `FloatResultPanel`
  - Copyable row helper: `_make_copyable_entry`

### 2.2 Startup flow
1. `main()` creates `BaseConverterApp` and calls `mainloop()`.
2. `BaseConverterApp.__init__` disables Tk input methods (`TK_NO_INPUT_METHODS` + `tk useinputmethods false`) and initializes base-converter state/history.
3. `_build_ui` mounts notebook tabs as the top window element and constructs:
   - base converter panel set
   - `IntegerVisualizerFrame`
   - `FloatVisualizerFrame`
4. `_wire_events` binds base-entry handlers and global shortcuts.
5. `_install_signal_handlers` registers SIGINT -> `_quit_app`.
6. `_update_from_source("dec")` normalizes initial base values.
7. `_select_tab(0)` focuses base converter binary entry.

### 2.3 Base converter update flow (valid path)
Source symbol: `BaseConverterApp._update_from_source`
1. Read source text from `self.vars[source_key]`.
2. Parse with `parse_value`; if valid, compute integer value.
3. Format all bases with `format_value`.
4. Build source-field display with `format_source_text` (preserves leading zeros).
5. Update non-source vars under `_programmatic=True` guard.
6. Optionally reformat source and restore cursor using logical-count helpers, with explicit end-of-text pinning when typing at the end.
7. Push source text to per-entry history.
8. Re-render base panels with `BasePanel.update_columns`.
9. Set base-converter status message.

### 2.4 Integer visualizer flow
Source symbol: `IntegerVisualizerFrame._on_change`
1. Parse decimal input with `parse_decimal_input`.
2. Validate finite integral value.
3. Resolve `IntegerTypeSpec` from `INT_TYPE_SPECS`.
4. Compute wrapped value + overflow/underflow via `int_wrap_and_flags`.
5. Build bit text via `int_bits`; derive signed/unsigned interpretations.
6. Render boxed bits in `BitGrid`.
7. Update calculation text + status; overflow uses red highlight.

### 2.5 Float visualizer flow
Source symbols: `FloatVisualizerFrame._on_change`, `_dispatch_compute`, `_apply_compute_result`, `FloatResultPanel.apply_display_data`
1. Parse shared decimal input with `parse_decimal_input`.
2. Debounce rapid edits (`after_cancel`/`after`) for `30 ms` before submitting compute.
3. Run `build_all_float_panel_display_data(...)` in a single-worker thread pool.
4. On completion, marshal result back to main thread via `after(0, ...)`.
5. Drop stale results using `request_id` comparison.
6. Apply latest panel data to `half/single/double` and update editable `sign/exponent/mantissa` fields per panel.
7. Emit timing logs to stdout (`[hdb][float-timing]`) for stale drops and latest apply path.
8. UI layout uses two lanes on top (`half`, `single`) and one full-width lane below (`double`).

Float direct-bit edit path:
1. User edits `sign/exponent/mantissa` bit fields in one float panel.
2. `FloatVisualizerFrame._on_panel_bit_fields_edit` decodes the source panel bits to a canonical numeric value.
3. Decimal plus all float panels (`half/single/double`) are synchronized immediately from that value.

### 2.6 Keyboard/event routing
Global bindings in `BaseConverterApp._wire_events`:
- `Ctrl+1`, `Ctrl+2`, `Ctrl+3`: notebook tab switching.
- `Tab`, `Shift+Tab`: custom entry cycling on base tab; default traversal on other tabs.
- `Escape`: quit.
- `Escape` is also bound directly on input widgets (`Entry`/`Combobox`/`Text`/`Spinbox`) to avoid widget-class interception.

Base-entry local bindings preserved:
- Copy (`C`, `Ctrl+C`), `Ctrl+U`, undo/redo (`Ctrl+Z`, `Ctrl+Shift+Z`), canonicalization on focus-out.
Visualizer decimal inputs:
- `Ctrl+U` deletes everything left of cursor (same behavior as base converter entries).
- Float-entry `Tab`/`Shift+Tab` traversal is handled at widget level in `FloatVisualizerFrame` so focus moves without default select-all behavior.

### STATE BLOCK (P2)
- `INDEX_VERSION`: `19`
- `FILE_MAP_SUMMARY`: Base conversion remains trace-driven; UI is larger-font with top notebook tabs; float visualizer uses debounced worker-thread compute with main-thread UI apply plus larger editable per-format sign/exponent/mantissa fields that are fixed-width/zero-filled, include aligned red two-character bit-index tokens (single digits centered) and per-field reverse-factor text (including evaluated mantissa term), stay synchronized across formats, use top-row side-by-side (`half`/`single`) plus bottom-row (`double`) layout, use non-selecting widget-level tab traversal over an explicit focus ring, and enforce reliable Escape quit via both global and direct input-widget bindings, with stdout timing logs.
- `OPEN QUESTIONS`: none blocking implementation.
- `KNOWN RISKS`: Base converter history/cursor logic remains tightly coupled.
- `GLOSSARY_DELTA`: `binade`, `ULP size`.

## 3. Capability Catalog

### 3.1 Base parsing + validation
- Symbols: `clean_input`, `parse_value`
- Behavior:
  - `""`, `"+"`, `"-"` map to `0`
  - `int(cleaned, base)` enforces base-digit validity

### 3.2 Base synchronization
- Symbol: `_update_from_source`
- Invariants:
  - Non-source fields always reflect parsed integer
  - `_programmatic` prevents recursive StringVar traces

### 3.3 Base formatting/grouping
- Symbols: `group_from_right`, `format_value`, `format_source_text`
- Behavior:
  - Decimal uses underscore grouping (`f"{value:_}"`)
  - Binary/hex grouped every four digits from right
  - Hex output uppercase
  - Active source field preserves user-entered leading zeros after normalization

### 3.4 Integer wrapping + bit interpretation
- Symbols: `int_wrap_and_flags`, `int_bits`
- Behavior:
  - Uses modulo `2^N` wrapping
  - Reports overflow/underflow against selected type bounds
  - Shows both signed and unsigned interpretations of one bit pattern

### 3.5 Float decomposition + error metrics
- Symbols: `float_bits_and_fields`, `float_ulp_size`, `float_error_metrics`, `build_float_panel_display_data`
- Behavior:
  - Quantization and raw-bit extraction using `numpy`
  - Classifies `NaN`, infinities, zero signs, subnormals, normals
  - Computes both ULP size (spacing) and ULP error (normalized absolute error)
  - ULP-error display can include symbolic form plus substituted operands and intermediate absolute-difference term
  - Exact representation yields absolute/ULP error `0`

### 3.6 Visual bit presentation
- Symbols: `BitGrid`, `HoverExplain`
- Behavior:
  - Bits rendered as individual boxes
  - Nibble spacing every 4 bits, with grouping reset at field boundaries
  - Role boundaries rendered with `|` markers
  - Used by integer visualizer bit-pattern display

### 3.7 Float panel fanout + field editing
- Symbols: `FloatVisualizerFrame`, `FloatResultPanel`, `build_all_float_panel_display_data`, `float_fields_from_bit_text`
- Behavior:
  - One shared decimal input drives three concurrent format panels
  - Visual layout is two columns on the first row (`half`, `single`) and one full-width panel on the second row (`double`)
  - Each panel displays quantized value, class, ULP size, and absolute error
  - Each panel provides editable `sign`, `exponent`, `mantissa` text boxes
  - Bit text boxes use enlarged font for readability
  - Float traversal uses an explicit focus ring (`decimal`, then each panel's `sign/exponent/mantissa`)
  - Reverse decomposition factors are displayed beside each of those three bit editors
  - Mantissa reverse factor includes its evaluated numeric result (`... = value`) for normal/subnormal numbers
  - Red bit-index tokens are shown under each bit textbox; each token has width 2 and is aligned per bit column
  - Bit text boxes are fixed-width and sanitize to `0/1`, with missing bits right-padded by `0`
  - Typing `0/1` at end of a bit box appends the bit and left-shifts prior bits (fixed-width)
  - In bit text boxes, `Backspace`/`Delete` zero out target bits instead of deleting characters
  - Editing any panel field set updates decimal + half + single + double immediately

### 3.8 Float responsiveness pipeline
- Symbols: `FloatVisualizerFrame._dispatch_compute`, `FloatVisualizerFrame._apply_compute_result`, `ThreadPoolExecutor`
- Behavior:
  - A `30 ms` debounce limits recomputation during rapid typing
  - Worker thread computes display payload off the Tk main thread
  - `request_id` prevents out-of-order/stale result application
  - Per-request timing metrics are printed to stdout for debounce/compute/queue/apply/total

### 3.9 Copyable output rows
- Symbols: `_make_copyable_entry`, `IntegerVisualizerFrame._build_value_row`, `FloatResultPanel._build_value_row`
- Behavior:
  - Summary/value rows are rendered as read-only `Entry` widgets
  - Text remains selectable/copyable without editing state mutation

## 4. Cross-Cutting Invariants
- Base converter still synchronizes `bin/dec/hex` from active source field.
- Base converter source field preserves leading zeros through live reformatting/focus-out.
- `_programmatic` and `_history_replaying` continue guarding recursion/replay.
- Invalid base input highlights only the source base field.
- Existing entry points remain valid: `hdb`, `python -m hdb`.
- Base converter shortcuts remain functional.
- Visualizer tabs accept decimal input only (including scientific notation).
- Float visualizer preserves IEEE-754 special value classification.
- Float panel editable fields enforce binary characters, fixed per-field widths, and zero-fill backspace/delete semantics.
- Float panel bit text boxes are large and include per-bit red index guides.
- Float panel bit fields at cursor-end typing use append+left-shift semantics while preserving fixed width.
- Float-tab widget-level Tab/Shift+Tab traversal moves focus without selecting text.
- Horizontal scrollbar widgets are intentionally removed from base and visualizer panes.
- Tk widget mutation remains on the main thread only.
- Tk startup configuration suppresses `imDefLkup.c` fabricated-key stderr noise on affected Linux Tk builds.

## 5. Things You Must Know Before Changing This Codebase
1. `BaseConverterApp._update_from_source` is still the highest regression-risk function.
2. Tab-scoped behavior matters: base entry `Tab`/`Shift+Tab` routing is conditional on active notebook tab.
3. Integer native types (`long`, etc.) use platform-dependent widths via `ctypes.sizeof(...)`.
4. Float decomposition correctness depends on `numpy` dtype/view behavior in `datatypes.py`.
5. Distinguish ULP spacing (`float_ulp_size`) from ULP error (`float_error_metrics`).
6. Copyability of displayed results depends on read-only `Entry` rows; avoid replacing them with non-selectable labels.
7. Keep worker thread results fenced by `request_id`; never apply stale payloads.

## 6. Testing and Validation Posture
Automated tests present:
- `tests/test_app_base_converter_behavior.py`
- `tests/test_datatypes.py`
- `tests/test_visualizer_behavior.py`

Coverage focus:
- Integer wrapping and bit-pattern correctness
- Float classification and exact-error convention
- Float ULP size behavior within same binade
- Float aggregated panel-data builder shape/invariants
- Forward/reverse/ULP-formula float format output shape
- Float bit-field sanitization keeps fixed width via zero-padding

Manual checklist:
- `Ctrl+1/2/3` tab switching
- Base converter trace synchronization, invalid highlighting, cursor restoration
- `Ctrl+U` in integer/float decimal input deletes left of cursor
- Base converter preserves leading zeros in active source field
- Integer overflow highlighting and signed/unsigned dual view
- Float shared input updates all three result panels
- Float typing remains responsive during rapid edits
- Float panels show ULP size
- Visualizer and integer summary rows are selectable/copyable

## 7. Source File Index (Symbol Map)

## `src/hdb/app.py`
- Role: Main app shell with notebook integration and preserved base converter implementation.
- Defines:
  - Constants: `BASES`, `TITLES`
  - Functions: `clean_input`, `parse_value`, `group_from_right`, `format_value`, `format_source_text`, `main`
  - Classes: `BasePanel`, `BaseConverterApp`
- New/updated `BaseConverterApp` methods:
  - `_build_converter_tab`
  - `_bind_escape_on_inputs`
  - `_disable_input_methods`
  - `_current_tab_index`
  - `_select_tab`
  - `_on_ctrl_1_tab`, `_on_ctrl_2_tab`, `_on_ctrl_3_tab`
  - `_on_tab_key`, `_on_shift_tab_key` (tab-aware)

## `src/hdb/datatypes.py`
- Role: Shared integer and float transformation backend.
- Defines:
  - Dataclasses: `IntegerTypeSpec`, `FloatTypeSpec`
  - Constants: `INT_TYPE_SPECS`, `FLOAT_TYPE_SPECS`
  - Functions:
    - `parse_decimal_input`
    - `int_wrap_and_flags`
    - `int_bits`
    - `float_bits_and_fields`
    - `float_fields_from_bit_text`
    - `float_ulp_size`
    - `float_error_metrics`
    - `format_float_forward_calc`
    - `format_float_reverse_calc`
    - `format_ulp_error_formula`
    - `build_float_panel_display_data`
    - `build_float_panel_display_data_from_bits`
    - `build_all_float_panel_display_data`

## `src/hdb/visualizer.py`
- Role: Notebook tab UI for integer and float visualizations.
- Defines classes:
  - `HoverExplain`
  - `BitGrid`
  - `_make_copyable_entry`
  - `IntegerVisualizerFrame`
  - `FloatVisualizerFrame`
  - `FloatResultPanel`
- Notable handlers:
  - `BitGrid.render(..., line_break_before=...)`
  - `IntegerVisualizerFrame._on_ctrl_u_key`
  - `FloatVisualizerFrame.cycle_entry_focus`
  - `FloatVisualizerFrame._bind_tab_navigation_handlers`
  - `FloatVisualizerFrame._focus_without_selection`
  - `FloatVisualizerFrame._active_focus_ring`
  - `FloatVisualizerFrame._on_ctrl_u_key`
  - `FloatVisualizerFrame._on_panel_bit_fields_edit`
  - `FloatVisualizerFrame._compute_payload_timed`
  - `FloatVisualizerFrame._dispatch_compute`
  - `FloatVisualizerFrame._apply_compute_result`
  - `FloatResultPanel.focus_entries`
  - `FloatResultPanel._bit_index_tokens`
  - `FloatResultPanel._build_bit_index_guides`
  - `FloatResultPanel._bind_bit_index_guides`
  - `FloatResultPanel._build_bit_row`
  - `FloatResultPanel._format_factor_decimal`
  - `FloatResultPanel._sanitize_bits`

## `tests/test_app_base_converter_behavior.py`
- Role: Base-converter source-format tests for leading-zero preservation across bases.

## `tests/test_datatypes.py`
- Role: Backend behavior checks for integer and float helpers.

## `tests/test_visualizer_behavior.py`
- Role: Formatting behavior checks for float calculation display helpers.

## `pyproject.toml`
- Role: Packaging metadata and dependencies.
- Notable config:
  - Runtime dependency: `numpy>=1.26`
  - Console script: `hdb = "hdb.app:main"`

## `README.md`
- Role: User-facing behavior contract.
- Describes:
  - three tabs and keyboard shortcuts
  - float shared-input multi-panel visualization

## 8. Glossary
- `ULP size`: Numeric spacing between adjacent representable values at a quantized value.
- `ULP error`: Absolute error divided by ULP size.
- `binade`: Range of floating-point values sharing exponent (except subnormal/special regions).
- `bit grid`: Horizontal boxed-bit renderer used by the integer visualizer tab.

## 9. Open Questions / Assumptions
### OPEN QUESTIONS
- None blocking.

### ASSUMPTIONS
- Tkinter is available in target runtime.
- `numpy` is installed per `pyproject.toml` dependency.

### STATE BLOCK (FINAL)
- `INDEX_VERSION`: `31`
- `FILE_MAP_SUMMARY`: Reflects converter shell + dedicated datatype backend + larger-font GUI reformat + top-aligned notebook tabs + float editable `sign/exponent/mantissa` fields with full half/single/double/decimal synchronization + top-row side-by-side half/single layout with full-width double row + larger fixed-width zero-filled bit-field editing (`Backspace`/`Delete` write `0`, end-typing appends with left-shift) + aligned red two-character bit-index tokens below each float bit textbox + reverse decomposition moved beside sign/exponent/mantissa fields (and summary `Forward`/`Reverse` rows removed) with evaluated mantissa factor result text + explicit widget-level float focus-ring Tab/Shift+Tab traversal without text selection while base traversal remains app-level/tab-scoped + no horizontal scrollbar widgets + removed float ULP-formula and ULP-error rows + reliable Escape quit via global and direct input-widget bindings + `30 ms` debounced worker-thread pipeline with stale-result guard, stdout timing logs, and Tk input-method suppression.
- `OPEN QUESTIONS`: none.
- `KNOWN RISKS`: base converter sync/cursor/history path remains sensitive.
- `GLOSSARY_DELTA`: finalized for ULP size/error distinction and async float compute path.
