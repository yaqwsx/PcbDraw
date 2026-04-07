"""
Thin compatibility shim for KiCAD 9 and 10 pcbnew API differences.

Replaces pcbnewTransition. Only supports KiCAD 9 and 10.
"""

import pcbnew  # type: ignore

KICAD_VERSION = tuple(int(x) for x in pcbnew.GetMajorMinorVersion().split("."))

if KICAD_VERSION[0] < 9:
    raise RuntimeError(
        f"PcbDraw requires KiCAD 9 or newer, found {pcbnew.GetMajorMinorVersion()}"
    )


def _attr(name: str, fallback: str) -> object:
    """Resolve a pcbnew attribute that may have been renamed between v9 and v10."""
    v = getattr(pcbnew, name, None)
    if v is not None:
        return v
    return getattr(pcbnew, fallback)


# KiCAD 10 shortened some enum names
EDA_UNITS_MM = _attr("EDA_UNITS_MM", "EDA_UNITS_MILLIMETRES")
