
from ._version import get_versions
__version__ = get_versions()['version'] # type: ignore
del get_versions

from . import _version
__version__ = _version.get_versions()['version']
