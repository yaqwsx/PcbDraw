import os
# Reports false error on Linux as LnkParse3 is Windows-only dependency
import LnkParse3 # type: ignore
from typing import List
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
    candidates += readInkscapeFromStartMenu()

    return chooseInkscapeCandidate(candidates)

def readInkscapeFromStartMenu() -> List[str]:
    candidates = []
    for profile in [os.environ.get("ALLUSERSPROFILE", ""), os.environ.get("USERPROFILE", "")]:
        path = os.path.join(profile, "Microsoft", "Windows", "Start Menu",
                            "Programs", "Inkscape", "Inkscape.lnk")
        try:
            with open(path, "rb") as f:
                lnk = LnkParse3.lnk_file(f)
                abspath = os.path.realpath(lnk.string_data.relative_path())
                # The .com version provides CLI interface
                abspath = os.path.splitext(abspath)[0] + ".com"
                candidates.append(abspath)
        except FileNotFoundError as e:
            continue
    return candidates

if __name__ == "__main__":
    print(detectInkscape())
