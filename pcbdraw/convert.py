import platform
import subprocess
import textwrap
import os
from typing import Union
from tempfile import TemporaryDirectory
from PIL import Image
from lxml.etree import _ElementTree # type: ignore

# Converting SVG to bitmap is a hard problem. We used Wand (and thus
# imagemagick) to do the conversion. However, imagemagick is really hard to
# configure properly and it breaks often. Therefore, we provide a custom module
# that has several conversion strategies that reflect the platform. We also try
# to provide descriptive enough message so the user can detect what is wrong.

if platform.system() == "Windows":
    from pcbdraw.convert_windows import detectInkscape
else:
    from pcbdraw.convert_unix import detectInkscape, rsvgSvgToPng

def inkscapeSvgToPng(inputFilename: str, outputFilename: str, dpi: int) -> None:
    """
    A strategy to convert an SVG file into a PNG file using Inkscape
    """
    command = [detectInkscape(), "--export-type=png", f"--export-dpi={dpi}",
         f"--export-filename={outputFilename}", inputFilename]
    def reportError(message: str) -> None:
        raise RuntimeError(f"Cannot convert {inputFilename} to {outputFilename}. Inkscape failed with:\n"
                            + textwrap.indent(message, "    "))
    try:
        r = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = r.stdout.decode("utf-8") + "\n" + r.stderr.decode("utf-8")
        # Inkscape doesn't respect error codes
        if "Can't open file" in output:
            reportError(output)
    except subprocess.CalledProcessError as e:
        output = e.stdout.decode("utf-8") + "\n" + e.stderr.decode("utf-8")
        reportError(output)

def svgToPng(inputFilename: str, outputFilename: str, dpi: int=300) -> None:
    """
    Convert SVG file into a PNG file based on platform-dependent strategies
    """
    if platform.system() == "Windows":
        strategies = {
            "Inkscape": inkscapeSvgToPng
        }
    else:
        strategies = {
            "RSVG": rsvgSvgToPng, # We prefer it over Inkscape as it is much faster
            "Inkscape": inkscapeSvgToPng
        }

    errors = {}
    for name, strategy in strategies.items():
        try:
            strategy(inputFilename, outputFilename, dpi)
            return
        except Exception as e:
            errors[name] = str(e)
    message = "Cannot convert PNG to SVG; all strategies failed:\n"
    for name, error in errors.items():
        m = f"- Strategy '{name}' failed with: {textwrap.indent(error, '  ')}\n"
        message += textwrap.indent(m, "  ")
    raise RuntimeError(message)

def save(image: Union[_ElementTree, Image.Image], filename: str, dpi: int=600) -> None:
    """
    Given an SVG tree or an image, save to a filename. The format is deduced
    from the extension.
    """
    ftype = os.path.splitext(filename)[1][1:].lower()
    if isinstance(image, Image.Image):
        if ftype not in ["jpg", "jpeg", "png", "bmp"]:
            raise TypeError(f"Cannot save bitmap image into {ftype}")
        image.save(filename)
        return
    if isinstance(image, _ElementTree):
        if ftype == "svg":
            image.write(filename)
            return
        with TemporaryDirectory() as d:
            svg_filename = os.path.join(d, "image.svg")
            if ftype == "png":
                png_filename = filename
            else:
                png_filename = os.path.join(d, "image.png")
            image.write(svg_filename)
            svgToPng(svg_filename, png_filename, dpi=dpi)
            if ftype == "png":
                return
            Image.open(png_filename).convert("RGB").save(filename)
            return
    raise TypeError(f"Unknown image type: {type(image)}")
