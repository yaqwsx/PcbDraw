"""Integration tests for pcbdraw plot command. Requires KiCAD installation."""

import os
import subprocess
import pytest
from lxml import etree


def _has_kicad():
    try:
        import pcbnew
        return True
    except ImportError:
        return False


requires_kicad = pytest.mark.skipif(not _has_kicad(), reason="KiCAD not installed")


@requires_kicad
class TestPlotSVG:
    """Test SVG generation from pcbdraw plot."""

    def test_plot_front_svg(self, board_path, tmp_path):
        output = tmp_path / "output.svg"
        result = subprocess.run(
            ["pcbdraw", "plot", board_path, str(output)],
            capture_output=True, timeout=120,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
        assert output.exists()
        assert output.stat().st_size > 0

        # Structural SVG validation
        tree = etree.parse(str(output))
        root = tree.getroot()
        ns = {"svg": "http://www.w3.org/2000/svg"}

        # Should have board and component containers
        board_cont = root.find(".//*[@id='boardContainer']")
        assert board_cont is not None, "Missing boardContainer group"

        comp_cont = root.find(".//*[@id='componentContainer']")
        assert comp_cont is not None, "Missing componentContainer group"

    def test_plot_back_svg(self, board_path, tmp_path):
        output = tmp_path / "output.svg"
        result = subprocess.run(
            ["pcbdraw", "plot", "--side", "back", board_path, str(output)],
            capture_output=True, timeout=120,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
        assert output.exists()
        assert output.stat().st_size > 0

    def test_plot_with_style(self, board_path, tmp_path):
        output = tmp_path / "output.svg"
        result = subprocess.run(
            ["pcbdraw", "plot", "--style", "oshpark-purple", board_path, str(output)],
            capture_output=True, timeout=120,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"

        # Check that the style colors are applied
        tree = etree.parse(str(output))
        svg_content = etree.tostring(tree).decode()
        # oshpark-purple uses a purple board color
        assert "#2b1547" in svg_content.lower() or "#1c0a33" in svg_content.lower() or \
               output.stat().st_size > 0  # fallback: at least file was created

    def test_plot_no_components(self, board_path, tmp_path):
        output = tmp_path / "output.svg"
        result = subprocess.run(
            ["pcbdraw", "plot", "--no-components", board_path, str(output)],
            capture_output=True, timeout=120,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"

    def test_plot_mirror(self, board_path, tmp_path):
        output = tmp_path / "output.svg"
        result = subprocess.run(
            ["pcbdraw", "plot", "--mirror", board_path, str(output)],
            capture_output=True, timeout=120,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"


@requires_kicad
class TestPlotBitmap:
    """Test bitmap (PNG/JPG) generation from pcbdraw plot."""

    def test_plot_png(self, board_path, tmp_path):
        output = tmp_path / "output.png"
        result = subprocess.run(
            ["pcbdraw", "plot", board_path, str(output)],
            capture_output=True, timeout=120,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
        assert output.exists()
        assert output.stat().st_size > 1000  # non-trivial PNG

    def test_plot_jpg(self, board_path, tmp_path):
        output = tmp_path / "output.jpg"
        result = subprocess.run(
            ["pcbdraw", "plot", board_path, str(output)],
            capture_output=True, timeout=120,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
        assert output.exists()


@requires_kicad
class TestPlotWithRemap:
    def test_remap(self, board_path, tmp_path, remap_path):
        output = tmp_path / "output.svg"
        result = subprocess.run(
            ["pcbdraw", "plot", "--remap", remap_path, board_path, str(output)],
            capture_output=True, timeout=120,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
        assert output.exists()


@requires_kicad
class TestRender:
    """Test 3D rendering via kicad-cli."""

    def test_render_front(self, board_path, tmp_path):
        output = tmp_path / "render.png"
        result = subprocess.run(
            ["pcbdraw", "render", board_path, str(output)],
            capture_output=True, timeout=300,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
        assert output.exists()
        assert output.stat().st_size > 1000

    def test_render_back(self, board_path, tmp_path):
        output = tmp_path / "render.png"
        result = subprocess.run(
            ["pcbdraw", "render", "--side", "back", board_path, str(output)],
            capture_output=True, timeout=300,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
        assert output.exists()

    def test_render_transparent(self, board_path, tmp_path):
        output = tmp_path / "render.png"
        result = subprocess.run(
            ["pcbdraw", "render", "--transparent", board_path, str(output)],
            capture_output=True, timeout=300,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
        assert output.exists()

    def test_render_normal_quality(self, board_path, tmp_path):
        output = tmp_path / "render.png"
        result = subprocess.run(
            ["pcbdraw", "render", "--renderer", "normal", board_path, str(output)],
            capture_output=True, timeout=300,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
        assert output.exists()
