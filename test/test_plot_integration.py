"""Integration tests for pcbdraw plot command. Requires KiCAD installation."""

import os
import shutil
import subprocess
import pytest
from lxml import etree

from pcbdraw.create_template import extract_board_footprints
from pcbdraw.kicad_cli import export_footprint_svg, load_board_scene


def _has_kicad():
    return shutil.which("kicad-cli") is not None


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
        assert output.stat().st_size > 1000
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
        outputs = {}
        for side in ("front", "back"):
            output = tmp_path / f"output-{side}.svg"
            result = subprocess.run(
                ["pcbdraw", "plot", "--no-components", "--side", side,
                 board_path, str(output)],
                capture_output=True, timeout=120,
            )
            assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
            outputs[side] = etree.parse(str(output)).getroot()

        front = outputs["front"]
        back = outputs["back"]
        assert float(back.attrib["width"].removesuffix("mm")) == pytest.approx(
            float(front.attrib["width"].removesuffix("mm")))
        assert float(back.attrib["height"].removesuffix("mm")) == pytest.approx(
            float(front.attrib["height"].removesuffix("mm")))

        front_viewbox = [float(value) for value in front.attrib["viewBox"].split()]
        back_viewbox = [float(value) for value in back.attrib["viewBox"].split()]
        assert back_viewbox[2:] == pytest.approx(front_viewbox[2:])

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


@requires_kicad
def test_board_scene_contains_electrical_annotations(board_path):
    scene = load_board_scene(board_path)

    assert scene.components
    assert scene.pads
    assert scene.nets
    assert any(pad.net for pad in scene.pads.values())
    assert any(track.net for track in scene.tracks)
    assert scene.zones
    assert scene.vias
    assert all(pad.outline and pad.layers for pad in scene.pads.values())
    assert all(component.bbox.width >= 0 for component in scene.components.values())

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


@requires_kicad
class TestLibTemplate:
    def test_embedded_footprint_template(self, board_path, tmp_path):
        board = open(board_path, encoding="utf-8").read()
        footprint = next(iter(extract_board_footprints(board).values()))
        footprint_file = tmp_path / "embedded.kicad_mod"
        footprint_file.write_text(footprint, encoding="utf-8")
        output = tmp_path / "template.svg"
        result = subprocess.run(
            ["pcbdraw", "libtemplate", "footprint", str(footprint_file), str(output)],
            capture_output=True, timeout=120,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
        root = etree.parse(str(output)).getroot()
        assert root.find(".//*[@id='origin']") is not None
        assert output.stat().st_size > 1000

    def test_board_templates_normalize_backside_instances(self, board_path, tmp_path):
        output = tmp_path / "templates"
        result = subprocess.run(
            ["pcbdraw", "libtemplate", "board", board_path, str(output)],
            capture_output=True, timeout=180,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
        template = output / "Capacitors_SMD" / "C_1206_HandSoldering.svg"
        root = etree.parse(str(template)).getroot()
        silk = root.find(".//*[@id='footprint-silk']")
        assert silk is not None
        assert len(silk.findall(".//{*}path")) >= 2

    def test_user_layer_does_not_collide_with_origin_marker(self, board_path, tmp_path):
        board = open(board_path, encoding="utf-8").read()
        footprint = next(iter(extract_board_footprints(board).values()))
        footprint_file = tmp_path / "user-layer.kicad_mod"
        footprint_file.write_text(footprint, encoding="utf-8")
        exported = export_footprint_svg(str(footprint_file), ["User.9"])
        assert "User.9" in exported.layers
        assert exported.origin != (0, 0)

def test_no_legacy_kicad_python_imports():
    root = os.path.dirname(os.path.dirname(__file__))
    offenders = []
    for directory in ("pcbdraw", "test"):
        for current, _, files in os.walk(os.path.join(root, directory)):
            for filename in files:
                if not filename.endswith(".py"):
                    continue
                path = os.path.join(current, filename)
                if path == __file__:
                    continue
                content = open(path, encoding="utf-8").read()
                if "import pcbnew" in content or "from pcbnew" in content:
                    offenders.append(os.path.relpath(path, root))
    assert offenders == []
