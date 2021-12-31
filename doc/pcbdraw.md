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
the other dependencies (numpy, lxmlm, mistune, wand, pybars3, pyyaml, etc.)
are managed automatically.

## No installation

If all the dependencies are available in your system
you can run the script without installing, just invoke the `pcbdraw.py`.
As an example, from the root of the git repo you can use:

```
pcbdraw/pcbdraw.py
```

## Usage

Usage of PcbDraw is simple, just run:

```.{bash}
pcbdraw  <input_file> <output_file>
```
- `output_file` is a path to an output SVG, PNG or JPG file
- `input_file` is a path to an `*.kicad_pcb` file

If there is a missing module in the libraries, the script will output warning.

There are several options for the script:

- `--libs <comma separated list>` specifies libraries to use. A library is a
  directory mirroring KiCAD footprint structure -- however, instead of foot
  print files it contains SVG files. First fit is used. You can use `default` or
  `eagle-default` to use built-in libraries.
- `--style <JSON_file>` specifies color theme for the board. Default is a green
  board, other styles can be found in the `styles` directories. To specify one
  of the built-in styles, prefix it with `builtin:`. E.g., `--style
  builtin:oshpark-purple.json`
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
- `--shrink` take a border in millimeter and shrink the canvas to the actual
  board + component size
- `--resistor-values` take a comma seperated colon delimited key-value pairs for manually setting a resistor's value, used for throughole resistors's band. For example, "R1:10k,R2:470"
- `--resistor-flip` take comma seperated list of throughole resistors to flip the bands

## Breaking change in PcbDraw > v0.6

Note that PcbDraw v0.6 is the last version that uses the convention 1 user unit
= 1 millimeter. The newer version use proper SVG units. This, however, brings a
breaking change to the library. Please migrate your libraries. For more details
refer to [PcbDraw default library](https://github.com/yaqwsx/PcbDraw-Lib).

## Path to styles and libraries

The styles can be installed in various locations. PcbDraw will
look for them in the following places:

- 1st: the same directory where the script is installed. As an example take
  a look at the repo layout.
- 2nd: the user local data directory. The script adds `share/pcbdraw`. As an
  example, on Linux systems the path for styles will be:
  `~/.local/share/pcbdraw/styles`
- 3rd: the system data directory. The script adds `share/pcbdraw`. As an
  example, on Linux systems the path for styles will be:
  `/usr/share/pcbdraw/styles`

The exact paths used on your system are displayed by the `--help` option.

Similarly, the libraries will be searched for in these locations:

- Same directory where the script is installed
- User local data directory, on Linux this would be `~/.local/share/pcbdraw/footprints`
- System data directory, on Linux this would be `/usr/share/pcbdraw/footprints`

## Writing Custom Styles

Style is a JSON file contain color definitions for the board substrate (they
don't have any effect on modules):

```.{json}
{
    "clad": "#9c6b28",
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
