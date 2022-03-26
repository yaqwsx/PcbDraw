import subprocess
from typing import List

def isValidInkscape(executable: str) -> bool:
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

def chooseInkscapeCandidate(candidates: List[str]) -> str:
    for candidate in candidates:
        if isValidInkscape(candidate):
            return candidate
    raise RuntimeError("No Inkscape executable found. Please check:\n" +
                       "- if Inkscape is installed\n" +
                       "- if it is version at least 1.0\n" +
                       "If the conditions above are true, please ensure Inkscape is in PATH or\n" +
                       "ensure there is environmental variable 'PCBDRAW_INKSCAPE' pointing to the Inkscape executable\n\n" +
                       "Checked paths: \n" +
                       "\n".join([f"- {x}" for x in candidates]))
