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

On Windows, you have to use KiCAD v5.99. Then, you have to install PcbDraw via
Python bundled with KiCAD not the Python you have installed on your system.
Therefore, open a terminal inside the installation directory of KiCAD and
invoke:

```
./python.exe -m pip install PcbDraw
```

## Docker

Simply follow the [guide for running KiKit inside a docker
container](https://github.com/yaqwsx/KiKit/blob/master/doc/installation.md#running-kikit-via-docker)
as the KiKit image contains also PcbDraw.
