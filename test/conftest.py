import os
import pytest

TEST_DIR = os.path.dirname(__file__)
RESOURCES_DIR = os.path.join(TEST_DIR, "resources")
EXAMPLES_DIR = os.path.join(os.path.dirname(TEST_DIR), "examples")


def get_board_path(version: str) -> str:
    return os.path.join(RESOURCES_DIR, f"ArduinoLearningKitStarter-v{version}.kicad_pcb")


def _loadable_boards():
    """Detect which boards can actually be loaded by the installed KiCAD."""
    boards = []
    for v in ["9", "10"]:
        path = get_board_path(v)
        if not os.path.isfile(path):
            continue
        try:
            import pcbnew
            b = pcbnew.LoadBoard(path)
            if b is not None:
                boards.append(v)
        except Exception:
            pass
    return boards


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
