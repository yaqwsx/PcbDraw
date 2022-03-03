import platform
import subprocess
import textwrap

if platform.system() == "Windows":
    from pcbdraw.convert_windows import detectInkscape
else:
    from pcbdraw.convert_unix import detectInkscape

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
        r = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
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
