import subprocess
import os
import textwrap
from pcbdraw.convert_common import chooseInkscapeCandidate

def detectInkscape() -> str:
    """
    Return path to working Inkscape >v1.0 executable
    """
    candidates = []
    if "PCBDRAW_INKSCAPE" in os.environ:
        # Ensure there is the .com extension needed for CLI interface
        path = os.path.splitext(os.environ["PCBDRAW_INKSCAPE"])[0] + ".com"
        candidates.append(path)
    candidates.append("inkscape") # Inkscape in path
    return chooseInkscapeCandidate(candidates)

def rsvgSvgToPng(inputFilename: str, outputFilename: str, dpi: int) -> None:
    tool = os.environ.get("PCBDRAW_RSVG", "rsvg-convert")
    command = [tool, "--dpi-x", str(dpi), "--dpi-y", str(dpi),
               "--output", outputFilename, "--format", "png", inputFilename]
    def reportError(message: str) -> None:
        raise RuntimeError(f"Cannot convert {inputFilename} to {outputFilename}. RSVG failed with:\n"
                            + textwrap.indent(message, "    "))
    try:
        r = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            output = r.stdout.decode("utf-8") + "\n" + r.stderr.decode("utf-8")
            reportError(output)
    except subprocess.CalledProcessError as e:
        output = e.stdout.decode("utf-8") + "\n" + e.stderr.decode("utf-8")
        reportError(output)
    except FileNotFoundError as e:
        reportError("rsvg-convert is not available. Please make sure it is installed.\n" +
                    f"It was executed via invoking '{tool}'")
