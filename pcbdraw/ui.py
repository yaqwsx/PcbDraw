import platform
import sys
from dataclasses import dataclass
from enum import IntEnum
from typing import Tuple, Optional, Any, List

import click
from PIL import Image

from . import __version__
from .convert import save
from .plot import (PcbPlotter, PlotComponents, PlotPaste, PlotPlaceholders,
                   PlotSubstrate, PlotVCuts, ResistorValue, load_remapping,
                   mm2ki)
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

    def convert(self, value: Any, param: Optional[click.Parameter],
                ctx: Optional[click.Context]) -> Layer:
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

    def convert(self, value: Any, param: Optional[click.Parameter],
                ctx: Optional[click.Context]) -> List[str]:
        if isinstance(value, list):
            return value
        if not isinstance(value, str):
            self.fail(f"Incorrect type of '{value}': {type(value)}")
        values = [x.strip() for x in value.split(",")]
        return values

@dataclass
class WarningStderrReporter:
    silent: bool

    def __post_init__(self) -> None:
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
@click.option("--libs", "-l", type=CommaList(), default=["KiCAD-base"],
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
@click.option("--filter", "-f", type=CommaList(), default=None,
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
def plot(input: str, output: str, style: Optional[str], libs: List[str],
         placeholders: bool, remap: str, drill_holes: bool, side: str,
         mirror: bool, highlight: List[str], filter: Optional[List[str]],
         vcuts: bool, dpi: int, margin: float, silent: bool, werror: bool,
         resistor_values: List[str], resistor_flip: List[str], components: bool,
         paste: bool, outline_width: float, show_lib_paths: bool) -> int:
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


    plotter.libs = libs
    plotter.render_back = side == "back"
    plotter.mirror = mirror
    plotter.margin = mm2ki(margin)

    # KiCAD 6 uses the default precision 6 which makes the images not
    # displayable by common web-browsers. Lowering the precision to 5 helps.
    # Since there's not much of a point of using lower resolution, we hard-code
    # the resolution for UI in order to make it clean. It is, however, still
    # configurable when it is used via via API.
    plotter.svg_precision = 5

    if show_lib_paths:
        print_lib_paths(plotter)
        return 0

    if style is not None:
        plotter.resolve_style(style)

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
    return 0

def build_plot_components(remap: str, highlight: List[str], filter: Optional[List[str]],
                          resistor_flip: List[str], resistor_values_input: List[str]) \
                          -> PlotComponents:
    remapping = load_remapping(remap)
    def remapping_fun(ref: str, lib: str, name: str) -> Tuple[str, str]:
        if ref in remapping:
            remapped_lib, remapped_name = remapping[ref]
            if name.endswith('.back'):
                return remapped_lib, remapped_name + '.back'
            else:
                return remapped_lib, remapped_name
        return lib, name

    resistor_values = {}
    for mapping in resistor_values_input:
        key, value = tuple(mapping.split(":"))
        resistor_values[key] = ResistorValue(value=value)
    for ref in resistor_flip:
        field = resistor_values.get(ref, ResistorValue())
        field.flip_bands = True
        resistor_values[ref] = field

    plot_components = PlotComponents(
        remapping=remapping_fun,
        resistor_values=resistor_values)

    if filter is not None:
        filter_set = set(filter)
        def filter_fun(ref: str) -> bool:
            return ref in filter_set
        plot_components.filter = filter_fun
    if highlight is not None:
        highlight_set = set(highlight)
        def highlight_fun(ref: str) -> bool:
            return ref in highlight_set
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

def processColor(c: Tuple[Optional[int], Optional[int], Optional[int]]) \
        -> Optional[Tuple[int, int, int]]:
    if c[0] is not None and c[1] is not None and c[2] is not None:
        return c[0], c[1], c[2]
    return None


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
def render(input: str, output: str, side: str, renderer: str, projection: str,
           no_components: bool, transparent: bool, padding: float,
           baseresolution: int,
           bgcolor1: Tuple[Optional[int], Optional[int], Optional[int]],
           bgcolor2: Tuple[Optional[int], Optional[int], Optional[int]]) -> None:
    """
    Create a rendered image of the PCB using KiCAD's 3D Viewer
    """
    if platform.system() == "Windows":
        sys.exit("Render functionality is not available on Windows.")

    from .renderer import (GuiPuppetError, RenderAction, Side, postProcessCrop,
                       renderBoard, validateExternalPrerequisites)

    try:
        validateExternalPrerequisites()

        app = fakeKiCADGui()

        bc1 = processColor(bgcolor1)
        bc2 = processColor(bgcolor2)

        plan = [RenderAction(
            side=Side.FRONT if side == "front" else Side.BACK,
            components=not no_components,
            raytraced=renderer == "raytrace",
            orthographic=projection == "orthographic",
            postprocess=postProcessCrop(input, mm2ki(padding), mm2ki(padding), transparent)
        )]
        if transparent:
            if bc1 is not None or bc2 is not None:
                print("Transparent background was specified, ignoring colors")
            bc2 = bc1 = (200, 100, 100)
        images = renderBoard(input, plan, baseResolution=(baseresolution, baseresolution),
                            bgColor1=bc1, bgColor2=bc2)
        save(image=images[0][0], filename=output)
    except GuiPuppetError as e:
        img_save_msg = ""
        if e.img is not None and isinstance(e.img, Image.Image):
            e.img.save("error.png")
            img_save_msg = "; image saved in error.png"
        raise RuntimeError(f"The following GUI error ocurred{img_save_msg}:\n{e}")

@click.group()
@click.version_option(__version__)
def run() -> None:
    """
    PcbDraw generates images of KiCAD PCBs
    """
    pass

run.add_command(render)
run.add_command(plot)
run.add_command(populate)

if __name__ == "__main__":
    run()
