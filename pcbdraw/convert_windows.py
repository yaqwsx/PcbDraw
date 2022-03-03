import os
import subprocess
import LnkParse3

def detectInkscape():
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

    for candidate in candidates:
        if isValidInkscape(candidate):
            return candidate
    raise RuntimeError("No Inkscape executable found. Please check:\n" + 
                       "- if Inkscape is installed\n" +
                       "- if it is version at least 1.0\n" +
                       "If the conditions above are true, please ensure Inkscape is in PATH or\n" +
                       "ensure there is environmental variable 'PCBDRAW_INKSCAPE' pointing to the Inkscape executable\n\n" +
                       "Checked paths: \n" +
                       "\n".join([f"- {x}" for x in candates]))

def readInkscapeFromStartMenu():
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

def isValidInkscape(executable):
    try:
        out = subprocess.check_output([executable, "--version"]).decode("utf-8")
        parts = out.split(" ")
        if parts[0] != "Inkscape":
            return False
        version = parts[1].split(".")
        return int(version[0]) == 1
    except FileNotFoundError as e:
        return False
    except subprocess.CalledProcessError as e:
        return False

if __name__ == "__main__":
    print(detectInkscape())