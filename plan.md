# Datatype Visualizer Plan

## System Overview
This plan adds a new datatype visualizer mode to the existing GUI calculator while preserving current base-converter behavior.

Source-of-truth references used:
- `codebase-analysis-docs/codebasemap.md` section `2.2 Startup flow`
- `codebase-analysis-docs/codebasemap.md` section `2.3 Main update flow (valid path)`
- `codebase-analysis-docs/codebasemap.md` section `2.5 Keyboard/event routing`
- `codebase-analysis-docs/codebasemap.md` section `3.2 Cross-base synchronization`
- `codebase-analysis-docs/codebasemap.md` section `3.5 Keyboard shortcuts + focus cycling`
- `codebase-analysis-docs/codebasemap.md` section `5. Things You Must Know Before Changing This Codebase`
- `codebase-analysis-docs/assets/architecture-overview.mmd`
- `codebase-analysis-docs/assets/update-sequence.mmd`
- `codebase-analysis-docs/assets/keyboard-routing.mmd`

## Requirements & Acceptance Criteria
1. Add three top-level tabs:
- `Base Converter`
- `Integer Visualizer`
- `Float Visualizer`

2. Add global tab shortcuts:
- `Ctrl+1` -> Base Converter
- `Ctrl+2` -> Integer Visualizer
- `Ctrl+3` -> Float Visualizer

3. Integer visualizer:
- Support C++ integer types excluding bool/char families.
- Required fixed-width coverage: `uint8_t`, `int8_t`, `uint16_t`, `int16_t`, `uint32_t`, `int32_t`, `uint64_t`, `int64_t`.
- Also support common non-fixed types: `short`, `unsigned short`, `int`, `unsigned int`, `long`, `unsigned long`, `long long`, `unsigned long long`.
- Show selected type, decimal value, and conversion calculation.
- Show both signed and unsigned interpretations of the active bit pattern.
- Detect overflow and show wrapped result with red visual highlighting.

4. Float visualizer:
- IEEE-754 support for `half` (binary16), `single` (binary32), `double` (binary64).
- Include and visualize special values: `NaN`, `+inf`, `-inf`, subnormals, signed zero.
- Show bit layout as `sign | exponent | mantissa`.
- Show selected type, decimal value, and forward/reverse conversion calculations.
- Show conversion error as absolute and ULP error (`0` when exact).

5. Presentation:
- Bits rendered in individual boxes.
- Nibbles separated by spacing.
- Role boundaries separated by `|` (especially for float sign/exponent/mantissa).
- Concise numeric explanations inline; detailed explanation appears on hover tooltip/pop-up.

6. Input behavior:
- Decimal input only for visualizer conversions (no hex conversion mode in these tabs).
- Scientific notation accepted in decimal fields.

7. UX consistency:
- Keep current invalid-input treatment style (localized red highlight + status messaging).

8. Dependency update:
- Add `numpy` for reliable half/single/double packing, decomposition, and ULP/error computations.

## Components & Files
Planned file changes and symbols:

1. `src/hdb/app.py`
- Update `BaseConverterApp._build_ui` to host a notebook/tab container.
- Add tab-switch key bindings in `BaseConverterApp._wire_events`.
- Add new handlers/symbols:
  - `_select_tab(index: int)`
  - `_on_ctrl_1_tab(event)`
  - `_on_ctrl_2_tab(event)`
  - `_on_ctrl_3_tab(event)`
- Preserve existing converter symbols and behavior:
  - `_update_from_source`
  - `_make_change_handler`
  - `_make_focus_out_handler`
  - `_on_tab_key`, `_on_shift_tab_key`
  - history and invalid-state methods

2. `src/hdb/datatypes.py` (new)
- Integer type metadata and range/bit helpers.
- Float decomposition/pack/unpack helpers via `numpy`.
- Symbols (planned):
  - `IntegerTypeSpec`
  - `FloatTypeSpec`
  - `INT_TYPE_SPECS`
  - `FLOAT_TYPE_SPECS`
  - `parse_decimal_input(...)`
  - `int_wrap_and_flags(...)`
  - `int_bits(...)`
  - `float_bits_and_fields(...)`
  - `float_error_metrics(...)`
  - `format_float_forward_calc(...)`
  - `format_float_reverse_calc(...)`

3. `src/hdb/visualizer.py` (new)
- UI frames and bit-grid rendering logic.
- Symbols (planned):
  - `IntegerVisualizerFrame`
  - `FloatVisualizerFrame`
  - `BitGrid`
  - `HoverExplain`

4. `pyproject.toml`
- Add runtime dependency: `numpy`.

5. `README.md`
- Document tabs, shortcuts, supported types, float field split, overflow wrapping indication, and error metrics.

6. `tests/test_datatypes.py` (new)
- Unit tests for integer and float conversion/decomposition.

7. `tests/test_visualizer_behavior.py` (new)
- Tests for formatting/calculation output and error metric display conventions.

8. `codebase-analysis-docs/codebasemap.md`
- Update architecture, capability catalog, symbol map, and invariants after implementation.

9. `codebase-analysis-docs/assets/*.mmd`
- Update architecture and keyboard diagrams to include notebook tabs and `Ctrl+1/2/3` flows if changed.

## Event/Data Flow Changes
1. Startup extends current flow (`codebasemap.md` section `2.2`):
- Build notebook.
- Mount existing converter UI in tab 1.
- Mount integer and float visualizer frames in tabs 2 and 3.

2. Base Converter flow remains unchanged (`codebasemap.md` section `2.3`):
- Existing StringVar trace conversion loop stays as-is.

3. Integer visualizer flow:
- Decimal input/type selection -> parse -> bounds check -> wrapped-result calc -> bit render -> signed/unsigned views -> formula text -> status/error.

4. Float visualizer flow:
- Decimal input/type selection -> quantize to target float type -> classify special/normal/subnormal -> sign/exp/mantissa render -> forward/reverse formulas -> abs/ULP error.

5. Keyboard routing update (`keyboard-routing.mmd` compatibility):
- Add `Ctrl+1/2/3` global bindings without breaking existing `Tab`, `Shift+Tab`, `Ctrl+U`, `Ctrl+Z`, `Ctrl+Shift+Z`, `Esc`.

## Edge Cases & Invariants
Invariants that must remain true:
- Base converter still synchronizes `bin/dec/hex` from active source field.
- `_programmatic` continues preventing recursive StringVar trace loops.
- Invalid input remains localized to source field styling and status message.
- Existing entry points remain valid: `hdb`, `python -m hdb`.
- Existing shortcuts continue to function.

New edge cases to handle:
- Integer overflow/underflow shows wrap indicator and wrapped value.
- Integer view shows both signed and unsigned interpretations for same bit pattern.
- Float special values and signed zero render correctly.
- Decimal scientific notation input is accepted.
- ULP and absolute error show `0` for exact representation.

## Testing & Validation
Unit tests:
- Integer:
  - min/max boundaries by type
  - overflow detection and wrapped results
  - bit rendering source data correctness
  - signed/unsigned interpretation consistency
- Float:
  - pack/unpack bit fields for half/single/double
  - special value decoding (`NaN`, `inf`, subnormal, `-0.0`)
  - absolute and ULP error computation
  - exact representation yields `0` errors

Manual validation:
- `Ctrl+1/2/3` tab switching.
- Existing base-converter shortcuts unchanged.
- Hover explanation pop-ups appear and remain concise.
- Invalid input visual treatment matches current style.

## Implementation Roadmap
1. Add numeric/type backend in `src/hdb/datatypes.py`.
2. Add visualizer UI components in `src/hdb/visualizer.py`.
3. Integrate notebook tabs and tab shortcut routing in `src/hdb/app.py`.
4. Integrate integer visualizer overflow/wrap and dual signed/unsigned display.
5. Integrate float visualizer IEEE-754 decomposition and error metrics.
6. Add/adjust tests.
7. Update `README.md`.
8. Update `codebase-analysis-docs/codebasemap.md` and affected diagrams.

## Risks & Open Questions
Known risks:
- `src/hdb/app.py` is already a high-coupling module (`codebasemap.md` section `5`), so UI integration should minimize churn and isolate new logic in new modules.
- `long`/`unsigned long` widths are platform-dependent in C++; implementation should document and display resolved bit width at runtime.

Open questions:
- None currently blocking implementation.
