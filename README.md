# PcbDraw

Convert your KiCAD boards into nice looking 2D drawings suitable for pinout
diagrams. Never draw them manually again!

![example](promo_pcbdraw.png)

This small Python script takes a KiCAD board (.kicad_pcb file) and produces a 2D
nice looking drawing of the board as an SVG file. This allows you to quickly and
automatically create awesome pinout diagrams for your project. These diagrams
are much easier to read than a labeled photo of a physical board or an actual
KiCAD design.

You and your users will love them!

PcbDraw also comes with a small utility called Populate which allows you to
easily specify & maintain nice looking HTML or Markdown population manuals.

![example](promo_populate.jpg)

## Installation

PcbDraw is a stand-alone CLI tool distributed as a Python package. Read more
details in the [installation guide](doc/installation.md).

## Usage

There are two separate guides:

- [usage of PcbDraw](doc/pcbdraw.md)
- [usage of Populate](doc/populate.md)

There are also examples of usage in the `examples` directory.

## PcbDraw seems to be broken!

Please, read [FAQ](doc/faq.md) first. If it does not answer your problem, feel
free to open issue on GitHub.

## Running with KiCAD nightly (v5.99)

If you would like to use PcbDraw with KiCAD nightly, you can! Just point
environmental variable PYTHON_PATH to the correct path to the nighly module.
E.g., on Ubuntu:

```
PYTHONPATH=/usr/lib/kicad-nightly/lib/python3/dist-packages pcbdraw --help
```

## Contributing

Feel free to submit issues and pull requests!

## Future Work

- make reasonably complete module library
