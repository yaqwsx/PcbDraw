# PcbDraw

PcbDraw allows you to convert KiCad board files into a nice looking
visualizations.

## Installing

You can install PcbDraw via pip:

```
pip install pcbdraw
```

## Dependencies

This script requires the `pcbnew` Python module (should come with KiCAD). All
the other dependencies are managed automatically.

## Usage

Usage of PcbDraw is simple, just run:

```.{bash}
pcbdraw  <input_file> <output_file>
```
- `output_file` is a path to an output SVG file
- `input_file` is a path to an `*.kicad_pcb` file

The script will output several debug messages of KiCAD Python API you can
ignore. I haven't found a way to disable them. If there is a missing module in
the libraries, the script will output warning.

There are several options for the script:

- `--libs=<comma separated list>` specifies libraries to use. A library is a
  directory mirroring KiCAD footprint structure -- however, instead of foot
  print files it contains SVG files. First fit is used. Use can use `default` or
  `eagle-default` to use built-in libraries.
- `--style=<JSON_file>` specifies color theme for the board. Default is a green
  board, other styles can be found in the `styles` directories.
- `--list-components` prints a list of all components from the front side of PCB.
  Doesn't produce drawing.
- `--placeholder` shows a red square in the drawing for missing modules.
- `--remap` takes a path to a JSON file containing a dictionary from component
  references to alternative modules to change a module for given component. This
  allows you to e.g. choose different colors for LEDs without a need to change
  original board and create new packages for different colors. Format of
  dictionary entry is `"<ref>": "<library>:<module>"`  - e.g. `"PHOTO1":
  "Resistors:R_PHOTO_7mm"`.
- `--no-drillholes` do not make the drill holes transparent.
- `--back` render the backward of the board, it will mirror the board automatically
- `--mirror` render the board mirrored on the x axis
- `--highlight` take a comma separated list of components and highlight them
- `--filter` take a comma separated list of components and show only them

## Writing Custom Styles

Style is a JSON file contain color definitions for the board substrate (they
don't have any effect on modules):

```.{json}
{
    "copper": "#417e5a",
    "board": "#4ca06c",
    "silk": "#f0f0f0",
    "pads": "#b5ae30",
    "outline": "#000000",
    "highlight-on-top": false,
    "highlight-style": "stroke:none;fill:#ff0000;opacity:0.5;",
    "highlight-padding": 1.5,
    "highlight-offset": 0
}
```

Colors are in HEX format, names of the colors should be self descriptive.

## Module Library

Library is a collection of SVG files each containing one drawing of a component.
The library structure follows KiCAD library structure - each footprint (module)
is a separate file placed in directories representing libraries.

It is also possible to have multiple libraries with different component style.

All the details about the library can be found in [its
repository](https://github.com/yaqwsx/PcbDraw-Lib). Note that the library is
essential for this script and unfortunately it is still incomplete -
contributions are welcomed! Drawing a single component from scratch takes less
than 10 minutes, which is not much time. Please, send a pull-request for
components you have created.

When specifying multiple module libraries, the first library path to match a
given footprint is used for rendering. The lookup order is the same you
wrote the `--libs` option.

## Eagle Boards

Boards from Eagle CAD are not supported directly now (and probably never will).
You can import an Eagle board into KiCAD and then feed it into PcbDraw. Since
version 5 the import feature works great.