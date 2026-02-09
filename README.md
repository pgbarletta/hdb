# hdb

`hdb` is a Tkinter desktop tool with three synchronized calculator/visualizer tabs:

- `Base Converter`: Binary (base 2), Decimal (base 10), Hexadecimal (base 16)
- `Integer Visualizer`: C++ integer bit-layout and wrap behavior
- `Float Visualizer`: IEEE-754 half/single/double decomposition

UI layout notes:
- The notebook tabs are the top-most element in the window.
- Typography is intentionally scaled up across controls, values, and bit views for readability.
- Horizontal scrollbar widgets are removed from converter/visualizer panels for a cleaner layout.

## Install

```bash
pip install .
```

## Run

```bash
hdb
```

or:

```bash
python -m hdb
```

## Keyboard shortcuts

- `Ctrl+1`: switch to `Base Converter`
- `Ctrl+2`: switch to `Integer Visualizer`
- `Ctrl+3`: switch to `Float Visualizer`
- `Tab` / `Shift+Tab`:
  - on `Base Converter`: cycle base text boxes
  - on `Float Visualizer`: cycle editable float text boxes (decimal + sign/exponent/mantissa) without auto-selecting text
- `Ctrl+U` in a base-converter textbox or visualizer decimal input: delete left of cursor
- `Ctrl+Z` / `Ctrl+Shift+Z` in a base-converter textbox: undo / redo
- `Esc`: always quit (works even when focus is inside a textbox)

## Base converter behavior

- Edits in binary/decimal/hex stay synchronized in real time.
- Invalid input highlights only the source field and updates status text.
- Leading zeros are preserved in the field you are actively editing.
- Binary and hexadecimal are grouped with `_` every 4 digits.
- Each base panel includes positional power columns (`base^n`).

## Integer visualizer behavior

Supported fixed-width types:
- `uint8_t`, `int8_t`, `uint16_t`, `int16_t`, `uint32_t`, `int32_t`, `uint64_t`, `int64_t`

Supported C++ native types (runtime-width dependent):
- `short`, `unsigned short`, `int`, `unsigned int`, `long`, `unsigned long`, `long long`, `unsigned long long`

Features:
- Decimal input (scientific notation accepted when integral).
- Bit pattern rendered in individual boxes with nibble spacing.
- Shows signed and unsigned interpretations of the active bit pattern.
- Detects overflow/underflow and highlights wrapped result.
- Result rows are selectable/copyable text.

## Float visualizer behavior

Supported IEEE-754 formats:
- `half` (binary16)
- `single` (binary32)
- `double` (binary64)

Features:
- One shared decimal input at the top of the tab.
- Layout: `half` and `single` are side-by-side on the top row; `double` is on its own row below.
- Three result panels (`half`, `single`, `double`) update together from that input.
- Float computations are debounced and executed on a worker thread to keep UI typing responsive.
- Stale async results are discarded so only the latest input is rendered.
- Each applied or dropped float request logs timing metrics to stdout (`[hdb][float-timing] ...`).
- Each panel includes its own bit layout (`sign | exponent | mantissa`), classification, absolute error, and ULP size.
- Each float panel has larger editable bit text boxes: one for `sign`, one for `exponent`, one for `mantissa`.
- Each bit textbox has red 2-character bit-index tokens under it, aligned per bit column (single-digit indices are centered).
- Reverse decomposition factors are shown next to each bit textbox (`sign`, `exponent`, `mantissa`).
- Mantissa factor includes the evaluated numeric result (`1 + .../2^... = ...` for normals).
- Editing any float panel bit fields (`half`/`single`/`double`) synchronizes all float formats and decimal in real time.
- Float bit-field editors are fixed-width and zero-filled by default (they do not shrink when edited).
- In float bit-field editors, `Backspace` and `Delete` write `0` instead of deleting characters.
- In float bit-field editors, typing `0/1` at end appends the bit and left-shifts existing bits (fixed-width window behavior).
- Handles and classifies `NaN`, `+inf`, `-inf`, subnormals, `+0`, and `-0`.
- Displays absolute error (`0` for exact representation).
- Result rows (including calculation text and bit-pattern text) are selectable/copyable.

Linux runtime note:
- Tk input methods are disabled at startup to suppress repeated `imDefLkup.c` fabricated-key stderr spam.
