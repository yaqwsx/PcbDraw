# Frequently asked questions

## The PNG output does not work! My images are empty or look weird.

PcbDraw uses either Inkscape or librsvg (`rsvg-convert`) to convert generated
SVG files into PNG files. If neither is available, conversion will fail.

We recommend installing librsvg as it is faster. On Debian/Ubuntu:

```
sudo apt install librsvg2-bin
```

Alternatively, install Inkscape 1.x. Make sure the `inkscape` or `rsvg-convert`
executable is in your PATH.

## PcbDraw doesn't work with my KiCad version

PcbDraw supports KiCad 9 and 10, following the policy of supporting the two
latest KiCad releases. Older versions (v5, v6, v7, v8) are no longer supported.
If you need support for older versions, use PcbDraw v1.1.x from PyPI.

PcbDraw invokes `kicad-cli` and does not import the `pcbnew` Python module. If
KiCad is installed outside `PATH`, set `KICAD_CLI` to the executable path.

## Component footprints are missing

PcbDraw ships with a basic set of SVG footprint images. If your board uses
footprints that are not in the built-in library, PcbDraw will show a warning and
skip those components. You can provide your own footprint SVGs via the `--libs`
option or create them using the `pcbdraw libtemplate` command. See the [library
documentation](library.md) for details.
