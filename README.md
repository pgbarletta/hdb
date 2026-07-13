# hdb

`hdb` is a Tkinter desktop tool with four synchronized calculator/visualizer tabs:

- `Base Converter`: Binary (base 2), Decimal (base 10), Hexadecimal (base 16)
- `Warp Calculator`: Fixed-width bitwise operations and CUDA launch thread visualizer
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
- `Ctrl+2`: switch to `Warp Calculator`
- `Ctrl+3`: switch to `Integer Visualizer`
- `Ctrl+4`: switch to `Float Visualizer`
- `Ctrl+A`: select all text in any text input (Entry, Spinbox, Combobox, Text widgets)
- `Ctrl+Tab` / `Ctrl+Shift+Tab`: cycle to the next / previous tab (wraps around), always — even when the cursor is inside a text box
- `Tab` / `Shift+Tab`:
  - on `Base Converter`: cycle base text boxes
  - on `Warp Calculator`: default widget tab behavior
  - on `Float Visualizer`: cycle editable float text boxes (decimal + sign/exponent/mantissa) without auto-selecting text
- `Ctrl+C`: copy selected text (native copy in plain entries; native copy in fixed-width bit editors)
- `Ctrl+X`: cut (plain entries: native delete selection; fixed-width bit editors: copy selection to clipboard and zero the bits)
- `Ctrl+U` in a base-converter textbox or visualizer decimal input: delete left of cursor
- `Ctrl+Z` / `Ctrl+Shift+Z` in a base-converter textbox: undo / redo
- `Esc`: always quit (works even when focus is inside a textbox)
- `Ctrl+C` in the launching terminal (SIGINT): quits promptly, even when the window is idle

## Base converter behavior

- Edits in binary/decimal/hex stay synchronized in real time.
- Invalid input highlights only the source field and updates status text.
- Leading zeros are preserved in the field you are actively editing.
- Binary and hexadecimal are grouped with `_` every 4 digits.
- Each base panel includes positional power columns (`base^n`).

## Warp calculator behavior

**Binary Calculator:**
- Fixed-width operand editors for A and B, displayed as binary strings with red per-bit index guides.
- Keystroke semantics match float bit fields: `0/1` replace at cursor; typing at end appends with left-shift; `Backspace`/`Delete` write `0`.
- Unary `~` (NOT) button inverts each operand in place.
- Bitwise operations: `AND`, `OR`, `XOR`, `SHL` (shift left), `SHR` (logical shift right).
- Width cycle button rolls through `4 → WARP(5) → 8 → 16 → 32 → 4`, re-sanitizing operands and result (widening zero-pads high bits; narrowing keeps low bits).
- Results displayed in copyable rows: fixed-width binary and hexadecimal.
- When SHL drops set bits beyond the width window, status notes the dropped carry-out.
- Shift count B is the unsigned value of B masked to the current width; shift ≥ width yields 0.

**CUDA Thread Visualizer:**
- Launch configuration input: `<<<blocks, (x, y, z)>>>` with four decimal entry fields for block count and 3D blockDim.
- Constraints (with caps and status message on exceed):
  - `blocks ≤ 32`
  - `blockDim.x * blockDim.y * blockDim.z ≤ 1024` (CUDA threads/block limit)
  - total threads (blocks × block_size) ≤ 4096
- Threads decomposed using CUDA linearization: `linear = threadIdx.x + threadIdx.y*blockDim.x + threadIdx.z*blockDim.x*blockDim.y`.
- Canvas draws one block per section (labeled `Block 0`, `Block 1`, etc.).
- Within each block, warps are drawn as vertical columns side by side.
- Each warp column has a label at the top (`w0`, `w1`, etc.) and always contains 32 lane squares stacked vertically (0–31).
- Row-per-warp visualization model: each `(y, z)` row of `blockDim.x` threads occupies its own warp(s) (`ceil(blockDim.x / 32)` warps per row). When `blockDim.x` is not a multiple of 32, the leftover lanes of each row's last warp are drawn grayed out and are not clickable — e.g. `blockDim (16, 1, 16)` draws 16 warps with lanes 16–31 gray in every warp.
- Note: this is a deliberate visualization model; real CUDA hardware packs warps from consecutive linear thread ids without per-dimension padding.
- The status line reports active threads, warps per block, total lanes, and unused lanes.
- Color coding: each thread square's background is colored by its `threadIdx.y` index (0 = blue, 1 = green, 2 = amber, 3 = violet, 4 = teal, 5 = rose, cycling); each warp column sits on a background rectangle colored by its `threadIdx.z` index with the same palette. Colors are rendered with a simulated transparency (blended toward the white backdrop; squares ~35% opacity, column rectangles ~16%). Gray is reserved for unused lanes.
- Each thread displayed as a clickable square labeled with its lane index (0–31 within the warp).
- The grid drawer occupies the left half of the section; a permanently visible "Thread info" panel occupies the right half.
- The info panel always shows the full text skeleton — `blockIdx.x`, `threadIdx.x`, `threadIdx.y`, `threadIdx.z`, and the fully expanded global index calculation `blockIdx.x*blockDim.x*blockDim.y*blockDim.z + threadIdx.z*blockDim.x*blockDim.y + threadIdx.y*blockDim.x + threadIdx.x` — with `-` placeholders when no thread is selected.
- Clicking a thread square highlights it and fills the info panel with that thread's numbers (every multiplier substituted).
- Clicking the highlighted thread again deselects it (numbers revert to placeholders); only one thread is highlighted at a time; changing the launch config clears the selection.
- Canvas scrolls vertically only; no horizontal scrollbar widget (by repo convention).
- Scrolling: the mouse wheel scrolls the grid when the pointer is over it; `Page Up`/`Page Down` scroll it by pages whenever the Warp Calculator tab is visible (including while typing in the operand or launch-config entries).

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
