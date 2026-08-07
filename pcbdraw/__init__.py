
from ._version import get_versions
__version__ = get_versions()['version'] # type: ignore
del get_versions

from . import _version
__version__ = _version.get_versions()['version']

# Public, pcbnew-free board-inspection API.
from .kicad_cli import load_board_scene
from .annotations import BoardScene

__all__ = ["BoardScene", "load_board_scene"]
