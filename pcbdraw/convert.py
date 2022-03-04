import platform
import subprocess
import textwrap

# Converting SVG to bitmap is a hard problem. We used Wand (and thus
# imagemagick) to do the conversion. However, imagemagick is really hard to
# configure properly and it breaks often. Therefore, we provide a custom module
# that has several conversion strategies that reflect the platform. We also try
# to provide descriptive enough message so the user can detect what is wrong.

if platform.system() == "Windows":
    from pcbdraw.convert_windows import detectInkscape
else:
    from pcbdraw.convert_unix import detectInkscape, rsvgSvgToPng

def inkscapeSvgToPng(inputFilename, outputFilename, dpi):
    """
    A strategy to convert an SVG file into a PNG file using Inkscape
    """
    command = [detectInkscape(), "--export-type=png", f"--export-dpi={dpi}",
         f"--export-filename={outputFilename}", inputFilename]
    def reportError(message):
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

def svgToPng(inputFilename, outputFilename, dpi=300):
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

if __name__ == "__main__":
    import sys
    svgToPng(sys.argv[1], sys.argv[2])
