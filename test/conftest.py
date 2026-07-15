import os
import pytest

from pcbdraw.kicad_cli import (
    SUPPORTED_KICAD_MAJORS, find_kicad_cli, kicad_version,
)

TEST_DIR = os.path.dirname(__file__)
RESOURCES_DIR = os.path.join(TEST_DIR, "resources")
EXAMPLES_DIR = os.path.join(os.path.dirname(TEST_DIR), "examples")


def get_board_path(version: str) -> str:
    return os.path.join(RESOURCES_DIR, f"ArduinoLearningKitStarter-v{version}.kicad_pcb")


def _loadable_boards():
    """Select the fixture matching the installed kicad-cli major version."""
    try:
        find_kicad_cli()
        major = str(kicad_version()[0])
    except RuntimeError:
        return []
    supported = {str(version) for version in SUPPORTED_KICAD_MAJORS}
    return [major] if major in supported and os.path.isfile(get_board_path(major)) else []


AVAILABLE_BOARDS = _loadable_boards()


@pytest.fixture(params=AVAILABLE_BOARDS, ids=[f"kicad-v{v}" for v in AVAILABLE_BOARDS])
def board_path(request):
    """Parametrized fixture providing board paths for each available KiCAD version."""
    return get_board_path(request.param)


@pytest.fixture
def examples_dir():
    return EXAMPLES_DIR


@pytest.fixture
def remap_path():
    return os.path.join(EXAMPLES_DIR, "resources", "remap.json")
