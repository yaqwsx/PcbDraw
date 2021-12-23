# Installation

PcbDraw is a stand-alone CLI tool. It is not an action plugin for KiCAD and
therefore, it has no menu inside Pcbnew. PcbDraw is compatible with both, KiCAD
v5 and KiCAD v5.99 (the upcoming v6 release). However, on **Windows and MacOS it
works only with v5.99** (due to limitations in KiCAD). If you would like to use
PcbDraw on Windows, you can run it via Docker as described below.

## Linux & MacOS

PcbDraw is distributed as a Python package. On most of the Linux distributions
you just have to install KiCAD and then install PcbDraw via Pip:

```
pip install PcbDraw # Use pip or pip3 based on your distribution
```

If you would like to use the upstream (unstable) version of PcbDraw, you can
install it directly from GitHub:

```
pip3 install git+https://github.com/yaqwsx/PcbDraw@master
```

## Windows

On Windows, you have to use KiCAD v5.99. To install KiKit on Windows, you have
to open "KiCAD Command Prompt". You can find it in the start menu:

![KiCAD Command Prompt in Start menu](resources/windowsCommandPrompt1.jpg)

Once you have it open like this:

![KiCAD Command Prompt in Start menu](resources/windowsCommandPrompt2.jpg)

you can put command in there and confirm them by pressing
enter. This is also the prompt from which you will invoke all KiKit's CLI
commands. They, unfortunatelly, does not work in an ordinary Command prompt due
to the way KiCAD is packaged on Windows.

Then you have to enter:

```
pip install PcbDraw
```

Now you can test that it works:

```.bash
pcbdraw --help
```

You should get something like this:
```
usage: pcbdraw [-h] [--version] [-s STYLE] [-l LIBS] [-p] [-m REMAP] [-c] [--no-drillholes] [-b] [--mirror] [-a HIGHLIGHT] [-f FILTER] [-v] [--silent] [--dpi DPI] [--no-warn-back] [--shrink SHRINK] board output

positional arguments:
  board                 .kicad_pcb file to draw
  output                destination for final SVG or PNG file

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -s STYLE, --style STYLE
                        JSON file with board style
  -l LIBS, --libs LIBS  comma separated list of libraries; use default, kicad-default or eagle-default for built-in libraries
  -p, --placeholder     show placeholder for missing components
  -m REMAP, --remap REMAP
                        JSON file with map part reference to <lib>:<model> to remap packages
  -c, --list-components
                        Dry run, just list the components
  --no-drillholes       Do not make holes transparent
  -b, --back            render the backside of the board
  --mirror              mirror the board
  -a HIGHLIGHT, --highlight HIGHLIGHT
                        comma separated list of components to highlight
  -f FILTER, --filter FILTER
                        comma separated list of components to show
  -v, --vcuts           Render V-CUTS on the Cmts.User layer
  --silent              Silent warning messages about missing footprints
  --dpi DPI             DPI for bitmap output
  --no-warn-back        Don't show warnings about back footprints
  --shrink SHRINK       Shrink the canvas size to the size of the board. Specify border in millimeters
```

All further invocations of PcbDraw have to be made from KiCAD Command Prompt,
not the regular command prompt.

## Docker

Simply follow the [guide for running KiKit inside a docker
container](https://github.com/yaqwsx/KiKit/blob/master/doc/installation.md#running-kikit-via-docker)
as the KiKit image contains also PcbDraw.
