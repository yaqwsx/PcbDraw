# PcbDraw

PcbDraw allows you to convert KiCad board files into a nice looking
visualizations. There are two modes of drawing the boards:

- plotting them. The result is a simplified and stylized board image. However,
  you have to supply hand-drawn footprint images. It can also remap symbols,
  easily select board style and also, render resistor values color bands.
- rendering them. This optional invokes Pcbnew's 3D renderer and renders the 3D
  image of the board. Note that this option doesn't work on Windows and its
  implementation is rather hacky and fragile as KiCAD doesn't offer any API for
  programmatically obtaining 3D renders of the board.

## Plotting boards

Board plotting is available under the `pcbdraw plot <input_file> <output_file>`
command. The output file can by any of the `.svg`, `.jpg` or `.png`. The command
has the following options:

- `-s, --style TEXT` name of the style or a path to a style file. Style files
  are explained below.
- `-l, --libs COMMA SEPARATED LIST` name of libraries that will be used for
  resolving the footprints. Default `KiCAD-6`.
- `-p, --placeholders` Render placeholders to the board showing the component
  origins.
- `m, --remap FILE` takes a path to a JSON file containing a dictionary from
  component references to alternative modules to change a module for given
  component. This allows you to e.g. choose different colors for LEDs without a
  need to change original board and create new packages for different colors.
  Format of dictionary entry is `"<ref>": "<library>:<module>"`  - e.g.
  `"PHOTO1": "Resistors:R_PHOTO_7mm"`.
- `--drill-holes / --no-drill-holes` Make drill holes transparent
- `--side [front|back]` Specify which side of the PCB to render
- `--mirror` Mirror the board
- `--highlight COMMA SEPARATED LIST` Comma separated list of component
  designators to highlight
- `-f, --filter COMMA SEPARATED LIST` Comma separated list of component designators
  to show, if not specified, show all
- `-v, --vcuts KICAD LAYER` If layer is specified, renders V-cuts from it
- `--resistor-values COMMA SEPARATED LIST` Comma separated colon delimited
  key-value pairs for manually setting a resistor's value, used for through-hole
  resistors's band. For example, `R1:10k,R2:470 1%`.
- `--resistor-flip COMMA SEPARATED LIST` Comma separated list of resistor
  designators whose bands to flip.
- `--paste` Render paste layer
- `--components / --no-components` Render components
- `--outline-width FLOAT` Outline width of the board substrate in mm
- `--dpi INTEGER` DPI for bitmap output
- `--margin INTEGER` Specify margin of the final image in millimeters
- `--silent` Do not output any warnings
- `--werror` Treat warnings as errors
- `--show-lib-paths` Show library paths and quit.

## Path to styles and libraries

The styles can be installed in various locations. PcbDraw will
look for them in the following places (in the order as specified):

- if the name matches existing file, it will be use (i.e., the name is path)
- built-in styles and libraries distributed with the PcbDraw.
- the user local data directory. The script adds `share/pcbdraw`. As an
  example, on Linux systems the path for styles will be:
  `~/.local/share/pcbdraw/styles`
- the system data directory. The script adds `share/pcbdraw`. As an example, on
  Linux systems the path for styles will be: `/usr/share/pcbdraw/styles`

The exact paths used on your system are displayed when you add
`--show-lib-paths` to you command.

By convention, footprint libraries can be inside `footprints` subdirectory and
styles inside `styles` subdirectory.

### Writing Custom Styles

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

### The Footprint Library

The footprint library has a separate [documentation page](library.md).


## Rendering boards

Board plotting is available under the `pcbdraw render <input_file> <output_file>`
command. The output file can by any of the `.jpg` or `.png`. The command
has the following options:

- `--side [front|back]` Specify which side to render
- `--padding INTEGER` Image padding in millimeters
- `-renderer [raytrace|normal]` Specify what renderer to use
- `--projection [orthographic|perspective]` Specify projection
- `--no-components` Disable component rendering
- `--transparent` Make transparent background of the image
- `--baseresolution INTEGER` Canvas size for the renderer; resulting boards is
  roughly 2/3 of the resolution
- `--bgcolor1 <INTEGER INTEGER INTEGER>` First background color
- `--bgcolor2 <INTEGER INTEGER INTEGER>` Second background color

The component 3D models are taken from the board settings and KiCAD parameters.
The board thickness and color is also taken from the board file.

Note that rendering only works on Linux and it is relatively slow - getting the
image can take between 10-120 seconds (based on the board complexity).

