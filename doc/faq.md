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

## PcbDraw doesn't work with my KiCAD version

PcbDraw requires KiCAD 9 or newer. Older versions (v5, v6, v7, v8) are no
longer supported. If you need support for older versions, use PcbDraw v1.1.x
from PyPI.

## Component footprints are missing

PcbDraw ships with a basic set of SVG footprint images. If your board uses
footprints that are not in the built-in library, PcbDraw will show a warning and
skip those components. You can provide your own footprint SVGs via the `--libs`
option or create them using the `pcbdraw libtemplate` command. See the [library
documentation](library.md) for details.
