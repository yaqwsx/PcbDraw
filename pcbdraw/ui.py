import sys
from dataclasses import dataclass
from enum import IntEnum
from typing import Tuple

import click

from . import __version__
from .convert import save
from .plot import (PcbPlotter, PlotComponents, PlotPaste, PlotPlaceholders,
                   PlotSubstrate, PlotVCuts, ResistorValue, load_remapping,
                   mm2ki)
from .renderer import (GuiPuppetError, RenderAction, Side, postProcessCrop,
                       renderBoard, validateExternalPrerequisites)
from .populate import populate
from .pcbnew_common import fakeKiCADGui


class Layer(IntEnum):
    F_Cu = 0
    B_Cu = 31
    B_Adhes = 32
    F_Adhes = 33
    B_Paste = 34
    F_Paste = 35
    B_SilkS = 36
    F_SilkS = 37
    B_Mask = 38
    F_Mask = 39
    Dwgs_User = 40
    Cmts_User = 41
    Eco1_User = 42
    Eco2_User = 43
    Edge_Cuts = 44
    Margin = 45
    B_CrtYd = 46
    F_CrtYd = 47
    B_Fab = 48
    F_Fab = 49

class KiCADLayer(click.ParamType):
    name = "KiCAD layer"

    def convert(self, value, param, ctx):
        if isinstance(value, int):
            if value in [item.value for item in Layer]:
                return Layer(value)
            return self.fail(f"{value!r} is not a valid layer number", param, ctx)
        if isinstance(value, str):
            try:
                return Layer[value.replace(".", "_")]
            except KeyError:
                return self.fail(f"{value!r} is not a valid layer name", param, ctx)
        return self.fail(f"{value!r} is not of expected type", param, ctx)

class CommaList(click.ParamType):
    name = "Comma separated list"

    def convert(self, value, param, ctx):
        if isinstance(value, list):
            return value
        if not isinstance(value, str):
            self.fail(f"Incorrect type of '{value}': {type(value)}")
        values = [x.strip() for x in value.split(",")]
        return values

@dataclass
class WarningStderrReporter:
    silent: bool

    def __post_init__(self):
        self.triggered = False

    def __call__(self, tag: str, msg: str) -> None:
        if self.silent:
            return
        sys.stderr.write(msg + "\n")
        self.triggered = True


@click.command()
@click.argument("input", type=click.Path(file_okay=True, dir_okay=False, exists=True))
@click.argument("output", type=click.Path(file_okay=True, dir_okay=False))
@click.option("--style", "-s", type=str, default=None,
    help="A name of built-in style or a path to style file")
@click.option("--libs", "-l", type=CommaList(), default=["KiCAD-6"],
    help="Comma separated list of libraries to use")
@click.option("--placeholders", "-p", is_flag=True,
    help="Render placeholders to show the components origins")
@click.option("--remap", "-m", type=click.Path(file_okay=True, dir_okay=False, exists=True),
    help="JSON file with map from part reference to <lib>:<model> to remap packages")
@click.option("--drill-holes/--no-drill-holes", default=True,
    help="Make drill holes transparent")
@click.option("--side", type=click.Choice(["front", "back"]), default="front",
    help="Specify which side of the PCB to render")
@click.option("--mirror", is_flag=True,
    help="Mirror the board")
@click.option("--highlight", type=CommaList(), default=[],
    help="Comma separated list of components to highlight")
@click.option("--filter", type=CommaList(), default=None,
    help="Comma separated list of components to show, if not specified, show all")
@click.option("--vcuts", "-v", type=KiCADLayer(), default=None,
    help="If layer specified, renders V-cuts from it")
@click.option("--dpi", type=int, default=300,
    help="DPI for bitmap output")
@click.option("--margin", type=int, default=1.5,
    help="Specify margin of the final image in millimeters")
@click.option("--silent", is_flag=True,
    help="Do not output any warnings")
@click.option("--werror", is_flag=True,
    help="Treat warnings as errors")
@click.option("--resistor-values", type=CommaList(), default=[],
    help="Comma separated list of resistor value remapping. For example, \"R1:10k,R2:470\"")
@click.option("--resistor-flip", type=CommaList(), default=[],
    help="Comma separated list of resistor bands to flip")
@click.option("--paste", is_flag=True,
    help="Add paste layer")
@click.option("--components/--no-components", default=True,
    help="Render components")
@click.option("--outline-width", type=float, default=0.15,
    help="Outline width in mm")
@click.option("--show-lib-paths", is_flag=True,
    help="Show library paths and quit")
def plot(input, output, style, libs, placeholders, remap, drill_holes, side,
         mirror, highlight, filter, vcuts, dpi, margin, silent, werror,
         resistor_values, resistor_flip, components, paste, outline_width,
         show_lib_paths):
    """
    Create a stylized drawing of the PCB.
    """

    app = fakeKiCADGui()

    plotter = PcbPlotter(input)
    plotter.setup_arbitrary_data_path(".")
    plotter.setup_env_data_path()
    plotter.setup_builtin_data_path()
    plotter.setup_global_data_path()

    plotter.yield_warning = WarningStderrReporter(silent=silent)

    if style is not None:
        plotter.resolve_style(style)
    plotter.libs = libs
    plotter.render_back = side == "back"
    plotter.mirror = mirror
    plotter.margin = margin

    if show_lib_paths:
        print_lib_paths(plotter)
        return 0

    plotter.plot_plan = [PlotSubstrate(
                            drill_holes=drill_holes,
                            outline_width=mm2ki(outline_width))]
    if paste:
        plotter.plot_plan.append(PlotPaste())
    if vcuts is not None:
        plotter.plot_plan.append(PlotVCuts(layer=vcuts))

    if components:
        plotter.plot_plan.append(
            build_plot_components(remap, highlight, filter, resistor_flip, resistor_values))
    if placeholders:
        plotter.plot_plan.append(PlotPlaceholders())

    image = plotter.plot()

    if werror and plotter.yield_warning.triggered:
        sys.exit("Warning treated as errors. See output above.")

    save(image, output, dpi)

def build_plot_components(remap, highlight, filter, resistor_flip, resistor_values_input):
    remapping = load_remapping(remap)
    def remapping_fun(ref: str, lib: str, name: str) -> Tuple[str, str]:
        if ref in remapping:
            return remapping[ref]
        return lib, name

    resistor_values = {}
    for mapping in resistor_values_input:
        key, value = tuple(mapping.split(":"))
        resistor_values[key] = ResistorValue(value=value)
    for ref in resistor_flip:
        field = resistor_values.get(key, ResistorValue())
        field.flip_bands = True
        resistor_values[ref] = field

    plot_components = PlotComponents(
        remapping=remapping_fun,
        resistor_values=resistor_values)

    if filter is not None:
        filter = set(filter)
        def filter_fun(ref: str) -> bool:
            return ref in filter
        plot_components.filter = filter_fun
    if highlight is not None:
        highlight = set(highlight)
        def highlight_fun(ref: str) -> bool:
            return ref in highlight
        plot_components.highlight = highlight_fun
    return plot_components

def print_lib_paths(plotter: PcbPlotter) -> None:
    plotter._build_libs_path()
    print("The following paths are searched when looking for data files:")
    for p in plotter.data_path:
        print(f"- {p}")
    print("")
    print("Following libraries were selected: " + ", ".join(plotter.libs))
    if len(plotter._libs_path) > 0:
        print("Corresponding locations found:")
        for p in plotter._libs_path:
            print(f"- {p}")
    else:
        print("No paths for the libraries were found")


@click.command()
@click.argument("input", type=click.Path(file_okay=True, dir_okay=False, exists=True))
@click.argument("output", type=click.Path(file_okay=True, dir_okay=False))
@click.option("--side", type=click.Choice(["front", "back"]), default="front",
    help="Specify which side to render")
@click.option("--padding", type=int, default=5,
    help="Image padding in millimeters")
@click.option("--renderer", type=click.Choice(["raytrace", "normal"]), default="raytrace",
    help="Specify what renderer to use")
@click.option("--projection", type=click.Choice(["orthographic", "perspective"]), default="orthographic",
    help="Specify projection")
@click.option("--no-components", is_flag=True, default=False,
    help="Disable component rendering")
@click.option("--transparent", is_flag=True,
    help="Make transparent background of the image")
@click.option("--baseresolution", type=int, default=3000,
    help="Canvas size for the renderer; resulting boards is roughly 2/3 of the resolution")
@click.option("--bgcolor1", type=(int, int, int), default=(None, None, None),
    help="First background color")
@click.option("--bgcolor2", type=(int, int, int), default=(None, None, None),
    help="Second background color")
def render(input, output, side, renderer, projection, no_components, transparent,
           padding, baseresolution, bgcolor1, bgcolor2):
    """
    Create a rendered image of the PCB using KiCAD's 3D Viewer
    """
    try:
        validateExternalPrerequisites()

        app = fakeKiCADGui()

        if bgcolor1[0] is None:
            bgcolor1 = None
        if bgcolor2[0] is None:
            bgcolor2 = None

        plan = [RenderAction(
            side=Side.FRONT if side == "front" else Side.BACK,
            components=not no_components,
            raytraced=renderer == "raytrace",
            orthographic=projection == "orthographic",
            postprocess=postProcessCrop(input, mm2ki(padding), mm2ki(padding), transparent)
        )]
        if transparent:
            if bgcolor1 is not None or bgcolor2 is not None:
                print("Transparent background was specified, ignoring colors")
            bgcolor2 = bgcolor1 = (200, 100, 100)
        images = renderBoard(input, plan, baseResolution=(baseresolution, baseresolution),
                            bgColor1=bgcolor1, bgColor2=bgcolor2)
        save(image=images[0][0], filename=output)
    except GuiPuppetError as e:
        e.img.save("error.png")
        e.message = "The following GUI error ocurred; image saved in error.png:\n" + e.message

@click.group()
@click.version_option(__version__)
def run():
    """
    PcbDraw generates images of KiCAD PCBs
    """
    pass

run.add_command(render)
run.add_command(plot)
run.add_command(populate)

if __name__ == "__main__":
    run()
