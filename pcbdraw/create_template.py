#!/usr/bin/env python3

from typing import BinaryIO, Callable, Union
from pcbnewTransition import pcbnew # type: ignore
import click
import os
from pathlib import Path

from lxml import etree # type: ignore
from .plot import PcbPlotter, PlotAction, PlotSubstrate, mm2ki

def loadFootprint(footprintPath: Union[str, Path]) -> pcbnew.FOOTPRINT:
    lib, foot = os.path.split(footprintPath)
    foot, _ = os.path.splitext(foot)
    return pcbnew.FootprintLoad(lib, foot)

def buildFootprintBoardFromFile(footprintPath: str) -> pcbnew.BOARD:
    """
    Given a path to kicad_mod file, build a single board with the component on
    0,0 in the default orientation.
    """
    footprint = loadFootprint(footprintPath)

    board = pcbnew.BOARD()
    footprint.SetPosition(pcbnew.VECTOR2I(0, 0))
    footprint.Reference().SetVisible(False)
    footprint.Value().SetVisible(False)
    board.Add(footprint)
    return board

def buildFootprintBoardFromFootprint(footprint: pcbnew.FOOTPRINT) -> pcbnew.BOARD:
    """
    Given a footprint file, build a single board with the component on
    0,0 in the default orientation.
    """
    try:
        newFootprint = footprint.Duplicate()
    except TypeError: # Footprint has overridden the method, cannot be called directly
        newFootprint = pcbnew.Cast_to_BOARD_ITEM(footprint).Duplicate()
    board = pcbnew.BOARD()
    if newFootprint.GetLayer() == pcbnew.B_Cu:
        newFootprint.Flip(pcbnew.VECTOR2I(0, 0), True)
    newFootprint.SetPosition(pcbnew.VECTOR2I(0, 0))
    board.Add(newFootprint)
    return board

class PlotComponentTopLayers(PlotSubstrate):
    def render(self, plotter: PcbPlotter) -> None:
        self._plotter = plotter

        to_plot = [
            PlotAction("copper", [pcbnew.F_Cu], self._process_layer),
            PlotAction("crt", [pcbnew.F_CrtYd], self._process_layer),
            PlotAction("fab", [pcbnew.F_Fab], self._process_layer),
            PlotAction("cmt", [pcbnew.Cmts_User], self._process_layer),
            PlotAction("edge", [pcbnew.Edge_Cuts], self._process_layer),
            PlotAction("silk", [pcbnew.F_SilkS], self._process_layer)]

        self._container = etree.Element("g", id="KiCAD footprint top")
        self._plotter.execute_plot_plan(to_plot)
        self._plotter.append_board_element(self._container)

class PlotComponentBottomLayers(PlotSubstrate):
    def render(self, plotter: PcbPlotter) -> None:
        self._plotter = plotter

        to_plot = [
            PlotAction("copper", [pcbnew.B_Cu], self._process_layer),
            PlotAction("crt", [pcbnew.B_CrtYd], self._process_layer),
            PlotAction("fab", [pcbnew.B_Fab], self._process_layer),
            PlotAction("cmt", [pcbnew.Cmts_User], self._process_layer),
            PlotAction("edge", [pcbnew.Edge_Cuts], self._process_layer),
            PlotAction("silk", [pcbnew.B_SilkS], self._process_layer)]

        self._container = etree.Element("g", id="KiCAD footprint bottom")
        self._plotter.execute_plot_plan(to_plot)
        self._plotter.append_board_element(self._container)

def addOrigin(document: etree.Element, ki2svg: Callable[[int], float]) -> None:
    """
    Add PcbDraw footprint origin to the module
    """
    origin = etree.Element("rect")
    origin.attrib["id"] = "origin"
    origin.attrib["fill"] = "red"
    origin.attrib["width"] = str(ki2svg(mm2ki(1)))
    origin.attrib["height"] = str(ki2svg(mm2ki(1)))
    origin.attrib["x"] = "0"
    origin.attrib["y"] = "0"

    document.getroot().append(origin)

def run_footprint_impl(footprint: Union[str, Path, pcbnew.FOOTPRINT],
                       output: BinaryIO, front: bool, back: bool) -> None:
    """
    Create a template for footprint based on the KiCAD footprint file.
    """
    if isinstance(footprint, pcbnew.FOOTPRINT):
        board = buildFootprintBoardFromFootprint(footprint)
    else:
        board = buildFootprintBoardFromFile(str(footprint))
    plotter = PcbPlotter(board)
    plotter.style = {
        "copper": "#666666",
        "crt": "#000000",
        "fab": "#000000",
        "cmt": "#000000",
        "edge": "#000000",
        "silk": "#61caff"
    }
    plotter.margin = 0
    plotter.svg_precision = 5

    plotter.plot_plan = []
    if front:
        plotter.plot_plan.append(PlotComponentTopLayers())
    if back:
        plotter.plot_plan.append(PlotComponentBottomLayers())

    document = plotter.plot()
    addOrigin(document, plotter.ki2svg)
    document.write(output)

@click.command("footprint")
@click.argument("footprint", type=click.Path(exists=True, file_okay=True, dir_okay=False))
@click.argument("output", type=click.File(mode="wb"))
@click.option("--front/--no-front", default=True,
    help="Render front size of the footprint")
@click.option("--back/--no-back", default=False,
    help="Render back size of the footprint")
def run_footprint(footprint: click.Path, output: BinaryIO, front: bool, back: bool) -> None:
    """
    Create a template for footprint based on the KiCAD footprint file.
    """
    return run_footprint_impl(str(footprint), output, front, back)

@click.command("board")
@click.argument("board", type=click.Path(exists=True, file_okay=True, dir_okay=False))
@click.argument("output", type=click.Path(exists=False, file_okay=False, dir_okay=True))
def run_board(board: str, output: click.Path) -> None:
    """
    Create a whole library of templates for footprints on given board
    """
    boardObj = pcbnew.LoadBoard(board)
    outdir = Path(str(output))
    outdir.mkdir(parents=True, exist_ok=True)
    footprints = {
        (str(f.GetFPID().GetLibNickname()), str(f.GetFPID().GetLibItemName())): f
        for f in boardObj.GetFootprints()}
    for (lib, name), f in footprints.items():
        print(f"Plotting: {lib}:{name}")
        libdir = outdir / lib
        libdir.mkdir(exist_ok=True)

        outFile = libdir / (name + ".svg")
        with open(outFile, "wb") as out:
            run_footprint_impl(f, out, front=True, back=False)

        outFile = libdir / (name + ".back.svg")
        with open(outFile, "wb") as out:
            run_footprint_impl(f, out, front=False, back=True)

@click.group()
def libtemplate() -> None:
    """
    Create footprint templates
    """
    pass

libtemplate.add_command(run_footprint)
libtemplate.add_command(run_board)

