"""Unit tests for pure functions in pcbdraw.plot (no KiCAD dependency)."""

import re
import pytest
from lxml import etree

from pcbdraw.plot import (
    SvgPathItem,
    get_board_polygon,
    get_closest,
    pseudo_distance,
    ki2mm,
    mm2ki,
    to_trans_matrix,
    to_kicad_basic_units,
    load_style,
    merge_bbox,
    strip_style_svg,
    extract_svg_content,
    make_XML_identifier,
)


class TestSvgPathItem:
    def test_parse_line(self):
        item = SvgPathItem("M 10 20 L 30 40")
        assert item.start == (10.0, 20.0)
        assert item.end == (30.0, 40.0)
        assert item.type == "L"

    def test_parse_arc(self):
        item = SvgPathItem("M 10 20 A 5 5 0 0 1 30 40")
        assert item.start == (10.0, 20.0)
        assert item.end == (30.0, 40.0)
        assert item.type == "A"
        assert item.args == [5.0, 5.0, 0.0, 0.0, 1.0]

    def test_unsupported_element(self):
        with pytest.raises(SyntaxError):
            SvgPathItem("M 10 20 C 1 2 3 4 5 6")

    def test_relative_path_rejected(self):
        with pytest.raises(SyntaxError):
            SvgPathItem("m 10 20 l 30 40")

    def test_is_same_identical(self):
        assert SvgPathItem.is_same((1.0, 2.0), (1.0, 2.0))

    def test_is_same_close(self):
        assert SvgPathItem.is_same((1.0, 2.0), (1.005, 2.005))

    def test_is_same_far(self):
        assert not SvgPathItem.is_same((1.0, 2.0), (10.0, 20.0))

    def test_flip_line(self):
        item = SvgPathItem("M 10 20 L 30 40")
        item.flip()
        assert item.start == (30.0, 40.0)
        assert item.end == (10.0, 20.0)

    def test_flip_arc(self):
        item = SvgPathItem("M 10 20 A 5 5 0 0 1 30 40")
        item.flip()
        assert item.args[4] == 0  # sweep flag toggled

    def test_format_line(self):
        item = SvgPathItem("M 10 20 L 30 40")
        s = item.format(first=True)
        assert "M" in s
        assert "10" in s
        assert "L" in s


class TestGetClosest:
    def test_exact_match(self):
        pts = [(0, 0), (1, 1), (2, 2)]
        assert get_closest((1, 1), pts) == 1

    def test_closest_by_distance(self):
        pts = [(0, 0), (10, 10), (2, 2)]
        assert get_closest((3, 3), pts) == 2


class TestUnitConversions:
    def test_ki2mm(self):
        assert ki2mm(1000000) == 1.0

    def test_mm2ki(self):
        assert mm2ki(1.0) == 1000000

    def test_roundtrip(self):
        assert ki2mm(mm2ki(5.5)) == pytest.approx(5.5, abs=0.001)

    def test_to_kicad_basic_units_mm(self):
        assert to_kicad_basic_units("1mm") == mm2ki(1.0)

    def test_to_kicad_basic_units_cm(self):
        assert to_kicad_basic_units("1cm") == mm2ki(10.0)


class TestTransformMatrix:
    def test_identity(self):
        m = to_trans_matrix(None)
        assert m[0][0] == pytest.approx(1.0)
        assert m[1][1] == pytest.approx(1.0)

    def test_translate(self):
        m = to_trans_matrix("translate(10, 20)")
        assert m[0][2] == pytest.approx(10.0)
        assert m[1][2] == pytest.approx(20.0)

    def test_scale(self):
        m = to_trans_matrix("scale(2)")
        assert m[0][0] == pytest.approx(2.0)
        assert m[1][1] == pytest.approx(1.0)  # scale(x) only scales x, y defaults to 1


class TestMergeBbox:
    def test_merge(self):
        result = merge_bbox((0, 10, 0, 10), (5, 20, 5, 20))
        assert result == (0, 20, 0, 20)

    def test_same(self):
        result = merge_bbox((0, 10, 0, 10), (0, 10, 0, 10))
        assert result == (0, 10, 0, 10)


class TestStripStyleSvg:
    def test_removes_fill_and_stroke(self):
        root = etree.fromstring('<g style="fill:#ff0000; stroke:#00ff00; opacity:0.5"></g>')
        strip_style_svg(root, keys=["fill", "stroke"], forbidden_colors=[])
        style = root.attrib["style"]
        assert "fill" not in style
        assert "stroke" not in style
        assert "opacity" in style

    def test_removes_forbidden_color_elements(self):
        root = etree.fromstring('<g><rect style="fill:#ffffff; stroke:#000000"/></g>')
        strip_style_svg(root, keys=[], forbidden_colors=["#ffffff"])
        assert len(root) == 0  # rect was removed

    def test_converts_fill_none_to_opacity(self):
        root = etree.fromstring('<g style="fill: none; stroke: none"></g>')
        strip_style_svg(root, keys=[], forbidden_colors=[])
        style = root.attrib["style"]
        assert "fill-opacity: 0" in style
        assert "stroke-opacity: 0" in style


class TestMakeXMLIdentifier:
    def test_strips_invalid(self):
        assert make_XML_identifier("foo-bar.baz") == "foobarbaz"

    def test_strips_leading_digits(self):
        assert make_XML_identifier("123abc") == "abc"


class TestGetBoardPolygon:
    def _wrap_svg(self, path_d: str) -> list:
        """Create SVG content structure matching what extract_svg_content returns."""
        group = etree.Element("g")
        path = etree.SubElement(group, "path", d=path_d)
        return [group]

    def test_simple_lines(self):
        elements = self._wrap_svg("M 0 0 L 10 0")
        elements += self._wrap_svg("M 10 0 L 10 10")
        result = get_board_polygon(elements)
        assert result.tag == "path"
        assert "d" in result.attrib

    def test_closed_polygon_comma_separated(self):
        """KiCad 7.0.1+ emits closed polygon paths like 'M x,y x,y Z'."""
        elements = self._wrap_svg("M 0.0,0.0 10.0,0.0 10.0,10.0 0.0,10.0 Z")
        result = get_board_polygon(elements)
        d = result.attrib["d"]
        assert "L" in d  # decomposed into line segments

    def test_closed_polygon_negative_coords(self):
        elements = self._wrap_svg("M -5.0,10.0 15.0,10.0 15.0,-10.0 -5.0,-10.0 Z")
        result = get_board_polygon(elements)
        d = result.attrib["d"]
        assert "L" in d

    def test_closed_polygon_integers(self):
        elements = self._wrap_svg("M 0,0 10,0 10,10 0,10 Z")
        result = get_board_polygon(elements)
        d = result.attrib["d"]
        assert "L" in d

    def test_regular_line_not_treated_as_polygon(self):
        """M ... L ... paths should not be decomposed."""
        elements = self._wrap_svg("M 0 0 L 10 0")
        result = get_board_polygon(elements)
        d = result.attrib["d"]
        # Should contain exactly one M and one L from the original path
        assert d.count("M") == 1
