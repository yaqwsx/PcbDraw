# Installation

PcbDraw is a stand-alone CLI tool. It is not an action plugin for KiCAD and
therefore, it has no menu inside Pcbnew. PcbDraw is compatible with both, KiCAD
v5 and v6. However, on **Windows and MacOS it works only with v6** (due to
limitations in KiCAD).

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

PcbDraw also requires either Inkscape 1.x or librsvg installed to perform
conversion from vector to rater images. The executables `inkscape` or
`rsvg-convert` have to be in PATH. Optionally, you can specify environmental
variables `PCBDRAW_INKSCAPE` or `PCBDRAW_RSVG` with paths to the tools. If they
are set, PcbDraw will use these paths.

## Windows

On Windows, you have to use KiCAD v6 and also, you have to install Inkscape 1.x.
PcbDraw doesn't work with Inkscape 0.9x. To install PcbDraw on Windows, you have
to open "KiCAD Command Prompt". You can find it in the start menu:

![KiCAD Command Prompt in Start menu](resources/windowsCommandPrompt1.jpg)

Once you have it open like this:

![KiCAD Command Prompt in Start menu](resources/windowsCommandPrompt2.jpg)

you can put command in there and confirm them by pressing enter. This is also
the prompt from which you will invoke all PcbDraw's CLI commands. They,
unfortunately, does not work in an ordinary Command prompt due to the way KiCAD
is packaged on Windows.

Then you have to enter:

```
pip install PcbDraw
```

Now you can test that it works:

```.bash
pcbdraw --help
```

You should get a help menu.

All further invocations of PcbDraw have to be made from KiCAD Command Prompt,
not the regular command prompt.

## Docker

Simply follow the [guide for running KiKit inside a docker
container](https://github.com/yaqwsx/KiKit/blob/master/doc/installation.md#running-kikit-via-docker)
as the KiKit image contains also PcbDraw.
