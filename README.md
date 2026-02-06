# Base Converter GUI

A fast, simple Tkinter calculator that converts between:

- Binary (base 2)
- Decimal (base 10)
- Hexadecimal (base 16)

All three fields stay synchronized in real time, and each base includes a column view
showing every digit with its positional power (`base^n`).

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
python -m baseconv_gui
```

## Notes

- Supports very large integers (Python arbitrary precision).
- Accepts optional leading `-`.
- Starts focused on the binary field so you can type immediately.
- `Tab` / `Shift+Tab` cycles only between binary, decimal, and hexadecimal text boxes.
- Each field has a `Copy` button to copy the current value.
- For readability, binary and hexadecimal outputs are grouped:
  - binary: `_` every 4 digits
  - hex: `_` every 4 digits
