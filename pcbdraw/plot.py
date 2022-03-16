#!/usr/bin/env python3

from __future__ import annotations

import decimal
import json
import math
import os
import re
import sysconfig
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple

import engineering_notation
import numpy as np
import svgpathtools
from lxml import etree, objectify
from pcbnewTransition import KICAD_VERSION, isV6, pcbnew

# Give more priority to local modules than installed versions
PKG_BASE = os.path.dirname(__file__)

etree.register_namespace("xlink", "http://www.w3.org/1999/xlink")

default_style = {
    "copper": "#417e5a",
    "board": "#4ca06c",
    "silk": "#f0f0f0",
    "pads": "#b5ae30",
    "outline": "#000000",
    "clad": "#9c6b28",
    "vcut": "#bf2600",
    "paste": "#8a8a8a",
    "highlight-on-top": False,
    "highlight-style": "stroke:none;fill:#ff0000;opacity:0.5;",
    "highlight-padding": 1.5,
    "highlight-offset": 0,
    "tht-resistor-band-colors": {
        0: '#000000',
        1: '#805500',
        2: '#ff0000',
        3: '#ff8000',
        4: '#ffff00',
        5: '#00cc11',
        6: '#0000cc',
        7: '#cc00cc',
        8: '#666666',
        9: '#cccccc',
        '1%': '#805500',
        '2%': '#ff0000',
        '0.5%': '#00cc11',
        '0.25%': '#0000cc',
        '0.1%': '#cc00cc',
        '0.05%': '#666666',
        '5%': '#ffc800',
        '10%': '#d9d9d9',
    }
}

float_re = r'([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)'

class SvgPathItem:
    def __init__(self, path):
        path = re.sub(r"([MLA])(-?\d+)", r"\1 \2", path)
        path = re.split("[, ]", path)
        path = list(filter(lambda x: x, path))
        if path[0] != "M":
            raise SyntaxError("Only paths with absolute position are supported")
        self.start = tuple(map(float, path[1:3]))
        path = path[3:]
        if path[0] == "L":
            x = float(path[1])
            y = float(path[2])
            self.end = (x, y)
            self.type = path[0]
            self.args = None
        elif path[0] == "A":
            args = list(map(float, path[1:8]))
            self.end = (args[5], args[6])
            self.args = args[0:5]
            self.type = path[0]
        else:
            raise SyntaxError("Unsupported path element " + path[0])

    @staticmethod
    def is_same(p1, p2):
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]
        return math.sqrt(dx*dx+dy*dy) < 5

    def format(self, first):
        ret = ""
        if first:
            ret += " M {} {} ".format(*self.start)
        ret += self.type
        if self.args:
            ret += " " + " ".join(map(lambda x: str(x).rstrip('0').rstrip('.'), self.args))
        ret += " {} {} ".format(*self.end)
        return ret

    def flip(self):
        self.start, self.end = self.end, self.start
        if self.type == "A":
            self.args[4] = 1 if self.args[4] < 0.5 else 0

def unique_prefix():
    unique_prefix.counter += 1
    return "pref_" + str(unique_prefix.counter)
unique_prefix.counter = 0

def matrix(data):
    return np.array(data, dtype=np.float32)

def extract_arg(args, index, default=None):
    """
    Return n-th element of array or default if out of range
    """
    if index >= len(args):
        return default
    return args[index]

def to_trans_matrix(transform):
    """
    Given SVG transformation string returns corresponding matrix
    """
    m = matrix([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    if transform is None:
        return m
    trans = re.findall(r'[a-z]+?\(.*?\)', transform)
    for t in trans:
        op, args = t.split('(')
        args = [float(x) for x in re.findall(float_re, args)]
        if op == 'matrix':
            m = np.matmul(m, matrix([
                [args[0], args[2], args[4]],
                [args[1], args[3], args[5]],
                [0, 0, 1]]))
        if op == 'translate':
            x = args[0]
            y = extract_arg(args, 1, 0)
            m = np.matmul(m, matrix([
                [1, 0, x],
                [0, 1, y],
                [0, 0, 1]]))
        if op == 'scale':
            x = args[0]
            y = extract_arg(args, 1, 1)
            m = np.matmul(m, matrix([
                [x, 0, 0],
                [0, y, 0],
                [0, 0, 1]]))
        if op == 'rotate':
            cosa = np.cos(np.radians(args[0]))
            sina = np.sin(np.radians(args[0]))
            if len(args) != 1:
                x, y = args[1:3]
                m = np.matmul(m, matrix([
                    [1, 0, x],
                    [0, 1, y],
                    [0, 0, 1]]))
            m = np.matmul(m, matrix([
                [cosa, -sina, 0],
                [sina, cosa, 0],
                [0, 0, 1]]))
            if len(args) != 1:
                m = np.matmul(m, matrix([
                    [1, 0, -x],
                    [0, 1, -y],
                    [0, 0, 1]]))
        if op == 'skewX':
            tana = np.tan(np.radians(args[0]))
            m = np.matmul(m, matrix([
                [1, tana, 0],
                [0, 1, 0],
                [0, 0, 1]]))
        if op == 'skewY':
            tana = np.tan(np.radians(args[0]))
            m = np.matmul(m, matrix([
                [1, 0, 0],
                [tana, 1, 0],
                [0, 0, 1]]))
    return m

def collect_transformation(element, root=None):
    """
    Collect all the transformation applied to an element and return it as matrix
    """
    if root is None:
        if element.getparent() is not None:
            m = collect_transformation(element.getparent(), root)
        else:
            m = matrix([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    else:
        if element.getparent() != root:
            m = collect_transformation(element.getparent(), root)
        else:
            m = matrix([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    if "transform" not in element.attrib:
        return m
    trans = element.attrib["transform"]
    return np.matmul(m, to_trans_matrix(trans))

def element_position(element, root=None):
    position = matrix([
        [element.attrib["x"]],
        [element.attrib["y"]],
        [1]])
    r = root
    trans = collect_transformation(element, root=r)
    position = np.matmul(trans, position)
    return position[0][0] / position[2][0], position[1][0] / position[2][0]

def ki2dmil(val):
    return val // 2540

def dmil2ki(val):
    return val * 2540

def ki2mm(val):
    return val / 1000000.0

def mm2ki(val):
    return int(val * 1000000)

# KiCAD 5 and KiCAD 6 use different units of the SVG
ki2svg = (lambda x: int(x)) if isV6(KICAD_VERSION) else ki2dmil
svg2ki = (lambda x: int(x)) if isV6(KICAD_VERSION) else dmil2ki

def to_kicad_basic_units(val):
    """
    Read string value and return it as KiCAD base units
    """
    x = float_re + r'\s*(pt|pc|mm|cm|in)?'
    value, unit = re.findall(x, val)[0]
    value = float(value)
    if unit == "" or unit == "px":
        return mm2ki(value * 25.4 / 96)
    if unit == "pt":
        return mm2ki(value * 25.4 / 72)
    if unit == "pc":
        return mm2ki(value * 25.4 / 6)
    if unit == "mm":
        return mm2ki(value)
    if unit == "cm":
        return mm2ki(value * 10)
    if unit == "in":
        return mm2ki(25.4 * value)

def to_user_units(val):
    x = float_re + r'\s*(pt|pc|mm|cm|in)?'
    value, unit = re.findall(x, val)[0]
    value = float(value)
    if unit == "" or unit == "px":
        return value
    if unit == "pt":
        return 1.25 * value
    if unit == "pc":
        return 15 * value
    if unit == "mm":
        return 3.543307 * value
    if unit == "cm":
        return 35.43307 * value
    if unit == "in":
        return 90

def make_XML_identifier(s):
    """
    Given a name, strip invalid characters from XML identifier
    """
    s = re.sub('[^0-9a-zA-Z_]', '', s)
    s = re.sub('^[^a-zA-Z_]+', '', s)
    return s

def extract_resistor_settings(args):
    tht_resistor_settings = {}
    if args.resistor_values:
        split_list = args.resistor_values.split(",")
        for r in split_list:
            r_s = r.split(":")
            tht_resistor_settings[r_s[0]] = {'override_val': r_s[1]}
    if args.resistor_flip:
        for r in args.resistor_flip.split(","):
            if r in tht_resistor_settings:
                tht_resistor_settings[r]['flip'] = True
            else:
                tht_resistor_settings[r] = {'flip': True}
    return tht_resistor_settings

def read_svg_unique(filename: str) -> etree.Element:
    root, _ = read_svg_unique2(filename)
    return root

def read_svg_unique2(filename: str) -> etree.Element:
    prefix = unique_prefix() + "_"
    root = etree.parse(filename).getroot()
    # We have to ensure all Ids in SVG are unique. Let's make it nasty by
    # collecting all ids and doing search & replace
    # Potentially dangerous (can break user text)
    ids = []
    for el in root.getiterator():
        if "id" in el.attrib and el.attrib["id"] != "origin":
            ids.append(el.attrib["id"])
    with open(filename) as f:
        content = f.read()
    for i in ids:
        content = content.replace("#"+i, "#" + prefix + i)
    root = etree.fromstring(str.encode(content))
    for el in root.getiterator():
        if "id" in el.attrib and el.attrib["id"] != "origin":
            el.attrib["id"] = prefix + el.attrib["id"]
    return root, prefix

def extract_svg_content(root):
    # Remove SVG namespace to ease our lives and change ids
    for el in root.getiterator():
        if '}' in str(el.tag):
            el.tag = el.tag.split('}', 1)[1]
    return [ x for x in root if x.tag and x.tag not in ["title", "desc"]]

def strip_style_svg(root, keys, forbidden_colors):
    elements_to_remove = []
    for el in root.getiterator():
        if "style" in el.attrib:
            s = el.attrib["style"].strip().split(";")
            styles = {}
            for x in s:
                if len(x) == 0:
                    continue
                key, val = tuple(x.split(":"))
                key = key.strip()
                val = val.strip()
                styles[key] = val
            fill = styles.get("fill", "").lower()
            stroke = styles.get("stroke", "").lower()
            if fill in forbidden_colors or stroke in forbidden_colors:
                elements_to_remove.append(el)
            el.attrib["style"] = ";" \
                .join([f"{key}: {val}" for key, val in styles.items() if key not in keys]) \
                .replace("  ", " ") \
                .strip()
    for el in elements_to_remove:
        el.getparent().remove(el)
    return root in elements_to_remove

def empty_svg(**attrs):
    document = etree.ElementTree(etree.fromstring(
        """<?xml version="1.0" standalone="no"?>
        <!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"
            "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
        <svg xmlns="http://www.w3.org/2000/svg" version="1.1"
            width="29.7002cm" height="21.0007cm" viewBox="0 0 116930 82680 ">
            <title>Picture generated by PcbDraw </title>
            <desc>Picture generated by PcbDraw</desc>
        </svg>"""))
    root = document.getroot()
    for key, value in attrs.items():
        root.attrib[key] = value
    return document

def get_board_polygon(svg_elements):
    """
    Try to connect independents segments on Edge.Cuts and form a polygon
    return SVG path element with the polygon
    """
    elements = []
    path = ""
    for group in svg_elements:
        for svg_element in group:
            if svg_element.tag == "path":
                elements.append(SvgPathItem(svg_element.attrib["d"]))
            elif svg_element.tag == "circle":
                # Convert circle to path
                att = svg_element.attrib
                s = " M {0} {1} m-{2} 0 a {2} {2} 0 1 0 {3} 0 a {2} {2} 0 1 0 -{3} 0 ".format(
                    att["cx"], att["cy"], att["r"], 2 * float(att["r"]))
                path += s
    while len(elements) > 0:
        # Initiate seed for the outline
        outline = [elements[0]]
        elements = elements[1:]
        size = 0
        # Append new segments to the ends of outline until there is none to append.
        while size != len(outline):
            size = len(outline)
            for i, e in enumerate(elements):
                if SvgPathItem.is_same(outline[0].start, e.end):
                    outline.insert(0, e)
                elif SvgPathItem.is_same(outline[0].start, e.start):
                    e.flip()
                    outline.insert(0, e)
                elif SvgPathItem.is_same(outline[-1].end, e.start):
                    outline.append(e)
                elif SvgPathItem.is_same(outline[-1].end, e.end):
                    e.flip()
                    outline.append(e)
                else:
                    continue
                del elements[i]
                break
        # ...then, append it to path.
        first = True
        for x in outline:
            path += x.format(first)
            first = False
    e = etree.Element("path", d=path, style="fill-rule: evenodd;")
    return e

def component_to_board_scale(svg):
    width = ki2svg(to_kicad_basic_units(svg.attrib["width"]))
    height = ki2svg(to_kicad_basic_units(svg.attrib["height"]))
    x, y, vw, vh = [float(x) for x in svg.attrib["viewBox"].split()]
    return width / vw, height / vh

def load_style(style_file):
    try:
        with open(style_file, "r") as f:
            style = json.load(f)
    except IOError:
        raise RuntimeError("Cannot open style " + style_file)
    required = set(["copper", "board", "clad", "silk", "pads", "outline",
        "vcut", "highlight-style", "highlight-offset", "highlight-on-top",
        "highlight-padding"])
    missing = required - set(style.keys())
    if missing:
        raise RuntimeError("Missing following keys in style {}: {}"
                                .format(style_file, ", ".join(missing)))
    return style

def load_remapping(remap_file):
    if remap_file is None:
        return {}
    try:
        with open(remap_file, "r") as f:
            f = json.load(f)
            return {ref: tuple(val.split(":")) for ref, val in f.items()}
    except IOError:
        raise RuntimeError("Cannot open remapping file " + remap_file)

def merge_bbox(left, right):
    """
    Merge bounding boxes in format (xmin, xmax, ymin, ymax)
    """
    return tuple([
        f(l, r) for l, r, f in zip(left, right, [min, max, min, max])
    ])


def shrink_svg(svg: etree.ElementTree, margin: float):
    """
    Shrink the SVG canvas to the size of the drawing. Add margin in
    KiCAD units.
    """
    # We have to overcome the limitation of different base types between
    # PcbDraw and svgpathtools
    from xml.etree.ElementTree import fromstring as xmlParse

    from lxml.etree import tostring as serializeXml
    paths = svgpathtools.document.flattened_paths(xmlParse(serializeXml(svg)))

    if len(paths) == 0:
        return
    bbox = paths[0].bbox()
    for x in paths:
        bbox = merge_bbox(bbox, x.bbox())
    bbox = list(bbox)
    bbox[0] -= ki2svg(margin)
    bbox[1] += ki2svg(margin)
    bbox[2] -= ki2svg(margin)
    bbox[3] += ki2svg(margin)

    root = svg.getroot()
    root.attrib["viewBox"] = "{} {} {} {}".format(
        bbox[0], bbox[2],
        bbox[1] - bbox[0], bbox[3] - bbox[2]
    )
    root.attrib["width"] = str(ki2mm(svg2ki(bbox[1] - bbox[0]))) + "mm"
    root.attrib["height"] = str(ki2mm(svg2ki(bbox[3] - bbox[2]))) + "mm"

def remove_empty_elems(tree):
    """
    Given SVG tree, remove empty groups and defs
    """
    for elem in tree:
        remove_empty_elems(elem)
    toDel = []
    for elem in tree:
        if elem.tag in ["g", "defs"] and len(elem.getchildren()) == 0:
            toDel.append(elem)
    for elem in toDel:
        tree.remove(elem)

def remove_inkscape_annotation(tree):
    for elem in tree:
        remove_inkscape_annotation(elem)
    for key in tree.attrib.keys():
        if "inkscape" in key:
            tree.attrib.pop(key)
    # Comments have callable tag...
    if not callable(tree.tag):
        objectify.deannotate(tree, cleanup_namespaces=True)

@dataclass
class Hole:
    position: Tuple[int, int]
    orientation: int
    drillsize: Tuple[int, int]

    def get_svg_path_d(self) -> str:
        w, h = [ki2svg(x) for x in self.drillsize]
        if w > h:
            ew = w - h
            eh = h
            commands = f"M {-ew / 2} {-eh / 2} "
            commands += f"A {eh / 2} {eh / 2} 0 1 1 {-ew / 2} {eh / 2} "
            commands += f"L {ew / 2} {eh / 2} "
            commands += f"A {eh / 2} {eh / 2} 0 1 1 {ew / 2} {-eh / 2} "
            commands += f"Z"
            return commands
        else:
            ew = w
            eh = h - w
            commands = f"M {-ew / 2} {eh / 2} "
            commands += f"A {ew / 2} {ew / 2} 0 1 1 {ew / 2} {eh / 2} "
            commands += f"L {ew / 2} {-eh / 2} "
            commands += f"A {ew / 2} {ew / 2} 0 1 1 {-ew / 2} {-eh / 2} "
            commands += f"Z"
            return commands

@dataclass
class PlotAction:
    name: str
    layers: List[int]
    action: Callable[[str, str], None]

@dataclass
class ResistorValue:
    value: Optional[str] = None
    flip_bands: bool=False


def collect_holes(board: pcbnew.BOARD) -> List[Hole]:
    holes: List[Hole] = [] # Tuple: position, orientation, drillsize
    for module in board.GetFootprints():
        if module.GetPadCount() == 0:
            continue
        for pad in module.Pads():
            pos = pad.GetPosition()
            holes.append(Hole(
                position=(pos[0], pos[1]),
                orientation=pad.GetOrientation(),
                drillsize=(pad.GetDrillSizeX(), pad.GetDrillSizeY())
            ))
    for track in board.GetTracks():
        if not isinstance(track, pcbnew.PCB_VIA) or not isV6(KICAD_VERSION):
            continue
        pos = track.GetPosition()
        holes.append(Hole(
            position=(pos[0], pos[1]),
            orientation=0,
            drillsize=(track.GetDrillValue(), track.GetDrillValue())
        ))
    return holes


@dataclass
class PlotSubstrate:
    drill_holes: bool = True
    outline_width: int = mm2ki(0.1)

    def render(self, plotter: PcbPlotter):
        self._plotter = plotter # ...so we don't have to pass it explicitly

        to_plot: List[PlotAction] = []
        if plotter.render_back:
            to_plot = [
                PlotAction("board", [pcbnew.Edge_Cuts], self._process_baselayer),
                PlotAction("clad", [pcbnew.B_Mask], self._process_layer),
                PlotAction("copper", [pcbnew.B_Cu], self._process_layer),
                PlotAction("pads", [pcbnew.B_Cu], self._process_layer),
                PlotAction("pads-mask", [pcbnew.B_Mask], self._process_mask),
                PlotAction("silk", [pcbnew.B_SilkS], self._process_layer),
                PlotAction("outline", [pcbnew.Edge_Cuts], self._process_outline)
            ]
        else:
            to_plot = [
                PlotAction("board", [pcbnew.Edge_Cuts], self._process_baselayer),
                PlotAction("clad", [pcbnew.F_Mask], self._process_layer),
                PlotAction("copper", [pcbnew.F_Cu], self._process_layer),
                PlotAction("pads", [pcbnew.F_Cu], self._process_layer),
                PlotAction("pads-mask", [pcbnew.F_Mask], self._process_mask),
                PlotAction("silk", [pcbnew.F_SilkS], self._process_layer),
                PlotAction("outline", [pcbnew.Edge_Cuts], self._process_outline)
            ]

        self._container = etree.Element("g", id="substrate")
        self._container.attrib["clip-path"] = "url(#cut-off)"
        self._boardsize = self._plotter.board.ComputeBoundingBox()
        self._plotter.execute_plot_plan(to_plot)

        if self.drill_holes:
            self._build_hole_mask()
            self._container.attrib["mask"] = "url(#hole-mask)"
        self._plotter.append_board_element(self._container)

    def _process_layer(self,name: str, source_filename: str) -> None:
        layer = etree.SubElement(self._container, "g", id="substrate-" + name,
            style="fill:{0}; stroke:{0};".format(self._plotter.get_style(name)))
        if name == "pads":
            layer.attrib["mask"] = "url(#pads-mask)"
        if name == "silk":
            layer.attrib["mask"] = "url(#pads-mask-silkscreen)"
        for element in extract_svg_content(read_svg_unique(source_filename)):
            # Forbidden colors = workaround - KiCAD plots vias white
            # See https://gitlab.com/kicad/code/kicad/-/issues/10491
            if not strip_style_svg(element, keys=["fill", "stroke"],
                                   forbidden_colors=["#ffffff"]):
                layer.append(element)

    def _process_outline(self, name: str, source_filename: str) -> None:
        if self.outline_width == 0:
            return
        layer = etree.SubElement(self._container, "g", id="substrate-" + name,
            style="fill:{0}; stroke:{0}; stroke-width: {1}".format(
                self._plotter.get_style(name),
                ki2svg(self.outline_width)))
        if name == "pads":
            layer.attrib["mask"] = "url(#pads-mask)"
        if name == "silk":
            layer.attrib["mask"] = "url(#pads-mask-silkscreen)"
        for element in extract_svg_content(read_svg_unique(source_filename)):
            # Forbidden colors = workaround - KiCAD plots vias white
            # See https://gitlab.com/kicad/code/kicad/-/issues/10491
            if not strip_style_svg(element, keys=["fill", "stroke", "stroke-width"],
                                   forbidden_colors=["#ffffff"]):
                layer.append(element)
        for hole in collect_holes(self._plotter.board):
            position = [ki2svg(coord) for coord in hole.position]
            size = [ki2svg(coord) for coord in hole.drillsize]
            if size[0] == 0 or size[1] == 0:
                continue
            el = etree.SubElement(layer, "path")
            el.attrib["d"] = hole.get_svg_path_d()
            el.attrib["transform"] = "translate({} {}) rotate({})".format(
                position[0], position[1], -hole.orientation / 10)

    def _process_baselayer(self, name: str, source_filename: str) -> None:
        clipPath = self._plotter.get_def_slot(tag_name="clipPath", id="cut-off")
        clipPath.append(
            get_board_polygon(
                extract_svg_content(
                    read_svg_unique(source_filename))))

        layer = etree.SubElement(self._container, "g", id="substrate-"+name,
            style="fill:{0}; stroke:{0};".format(self._plotter.get_style(name)))
        layer.append(
            get_board_polygon(
                extract_svg_content(
                    read_svg_unique(source_filename))))
        for element in extract_svg_content(read_svg_unique(source_filename)):
            # Forbidden colors = workaround - KiCAD plots vias white
            # See https://gitlab.com/kicad/code/kicad/-/issues/10491
            if not strip_style_svg(element, keys=["fill", "stroke"],
                                  forbidden_colors=["#ffffff"]):
                layer.append(element)

    def _process_mask(self, name: str, source_filename: str) -> None:
        mask = self._plotter.get_def_slot(tag_name="mask", id=name)
        for element in extract_svg_content(read_svg_unique(source_filename)):
            for item in element.getiterator():
                if "style" in item.attrib:
                    # KiCAD plots in black, for mask we need white
                    item.attrib["style"] = item.attrib["style"].replace("#000000", "#ffffff")
            mask.append(element)
        silkMask = self._plotter.get_def_slot(tag_name="mask", id=f"{name}-silkscreen")
        bg = etree.SubElement(silkMask, "rect", attrib={
            "x": str(ki2svg(self._boardsize.GetX())),
            "y": str(ki2svg(self._boardsize.GetY())),
            "width": str(ki2svg(self._boardsize.GetWidth())),
            "height": str(ki2svg(self._boardsize.GetHeight())),
            "fill": "white"
        })
        for element in extract_svg_content(read_svg_unique(source_filename)):
            # KiCAD plots black, no need to change fill
            silkMask.append(element)

    def _build_hole_mask(self) -> None:
        mask = self._plotter.get_def_slot(tag_name="mask", id="hole-mask")
        container = etree.SubElement(mask, "g")

        bb = self._plotter.board.ComputeBoundingBox()
        bg = etree.SubElement(container, "rect", x="0", y="0", fill="white")
        bg.attrib["x"] = str(ki2svg(bb.GetX()))
        bg.attrib["y"] = str(ki2svg(bb.GetY()))
        bg.attrib["width"] = str(ki2svg(bb.GetWidth()))
        bg.attrib["height"] = str(ki2svg(bb.GetHeight()))

        for hole in collect_holes(self._plotter.board):
            position = list(map(ki2svg, hole.position))
            size = list(map(ki2svg, hole.drillsize))
            if size[0] > 0 and size[1] > 0:
                if size[0] < size[1]:
                    stroke = size[0]
                    length = size[1] - size[0]
                    points = "{} {} {} {}".format(0, -length / 2, 0, length / 2)
                else:
                    stroke = size[1]
                    length = size[0] - size[1]
                    points = "{} {} {} {}".format(-length / 2, 0, length / 2, 0)
                el = etree.SubElement(container, "polyline")
                el.attrib["stroke-linecap"] = "round"
                el.attrib["stroke"] = "black"
                el.attrib["stroke-width"] = str(stroke)
                el.attrib["points"] = points
                el.attrib["transform"] = "translate({} {}) rotate({})".format(
                    position[0], position[1], -hole.orientation / 10)

@dataclass
class PlacedComponentInfo:
    id: str
    origin: Tuple[float, float]
    scale: Tuple[float, float]
    size: Tuple[float, float]

@dataclass
class PlotComponents:
    filter: Callable[[str], bool] = lambda x: True # Components to show
    highlight: Callable[[str], bool] = lambda x: False # References to highlight
    remapping: Callable[[str, str, str], Tuple[str, str]] = lambda ref, lib, name: (lib, name)
    resistor_values: Dict[str, ResistorValue] = field(default_factory=dict)

    def render(self, plotter: PcbPlotter) -> None:
        self._plotter = plotter
        self._prefix = unique_prefix()
        self._used_components: Dict[str, PlacedComponentInfo] = {}
        plotter.walk_components(invert_side=False, callback=self._append_component)
        plotter.walk_components(invert_side=True, callback=self._append_back_component)

    def _get_unique_name(self, lib, name, value):
        return f"{self._prefix}_{lib}__{name}_{value}"

    def _append_back_component(self, lib: str, name: str, ref: str, value: str,
                          position: Tuple[int, int, float]) -> None:
        return self._append_component(lib, name + ".back", ref, value, position)

    def _append_component(self, lib: str, name: str, ref: str, value: str,
                          position: Tuple[int, int, float]) -> None:
        if not self.filter(ref) or name == "":
            return
        # Override resistor values
        if ref in self.resistor_values and self.resistor_values[ref].value is not None:
            value = self.resistor_values[ref].value

        lib, name = self.remapping(ref, lib, name)

        unique_name = self._get_unique_name(lib, name, value)
        if unique_name in self._used_components:
            component_info = self._used_components[unique_name]
            component_element = etree.Element("use",
                attrib={"{http://www.w3.org/1999/xlink}href": "#" + component_info.id})
        else:
            ret = self._create_component(lib, name, ref, value)
            if ret is None:
                self._plotter.yield_warning("component", f"Component {lib}:{name} has not footprint.")
                return
            component_element, component_info = ret
            self._used_components[unique_name] = component_info

        self._plotter.append_component_element(etree.Comment(f"{lib}:{name}:{ref}"))
        group = etree.Element("g")
        group.append(component_element)
        ci = component_info
        group.attrib["transform"] = \
            f"translate({ki2svg(position[0])} {ki2svg(position[1])}) " + \
            f"scale({ci.scale[0]}, {ci.scale[1]}) " + \
            f"rotate({-math.degrees(position[2])}) " + \
            f"translate({-ci.origin[0]} {-ci.origin[1]})"
        self._plotter.append_component_element(group)

        if self.highlight(ref):
            self._build_highlight(ref, component_info, position)

    def _create_component(self, lib: str, name: str, ref: str, value: str) \
                             -> Optional[Tuple[etree.Element, PlacedComponentInfo]]:
        f = self._plotter._get_model_file(lib, name)
        if f is None:
            return None
        xml_id = make_XML_identifier(self._get_unique_name(lib, name, value))
        component_element = etree.Element("g", attrib={"id": xml_id})

        svg_tree, id_prefix = read_svg_unique2(f)
        for x in extract_svg_content(svg_tree):
            if x.tag in ["namedview", "metadata"]:
                continue
            component_element.append(x)
        origin_x = 0
        origin_y = 0
        origin = component_element.find(".//*[@id='origin']")
        if origin is not None:
            origin_x, origin_y = element_position(origin, root=component_element)
            origin.getparent().remove(origin)
        else:
            self._plotter.yield_warning(f"component: Component {lib}:{name} has not origin")
        svg_scale_x, svg_scale_y = component_to_board_scale(svg_tree)
        component_info = PlacedComponentInfo(
            id=xml_id,
            origin=(origin_x, origin_y),
            scale=(svg_scale_x, svg_scale_y),
            size=(to_kicad_basic_units(svg_tree.attrib["width"]), to_kicad_basic_units(svg_tree.attrib["height"]))
        )
        self._apply_resistor_code(component_element, id_prefix, ref, value)
        return component_element, component_info

    def _build_highlight(self, ref: str, info: PlacedComponentInfo,
                         position: Tuple[int, int, float]) -> None:
        padding = mm2ki(self._plotter.get_style("highlight-padding"))
        h = etree.Element("rect", id=f"h_{ref}",
            x=str(ki2svg(-padding / info.scale[0])),
            y=str(ki2svg(-padding /  info.scale[1])),
            width=str(ki2svg(info.size[0] + 2 * padding) / info.scale[0]),
            height=str(ki2svg(info.size[1] + 2 * padding) / info.scale[1]),
            style=self._plotter.get_style("highlight-style"))
        h.attrib["transform"] = \
            f"translate({ki2svg(position[0])} {ki2svg(position[1])}) " + \
            f"scale({info.scale[0]} {info.scale[1]}) " + \
            f"rotate({-math.degrees(position[2])}) " + \
            f"translate({-info.origin[0]}, {-info.origin[1]})"
        self._plotter.append_highlight_element(h)

    def _apply_resistor_code(self, root: etree.Element, id_prefix: str, ref: str, value: str) -> None:
        if root.find(f".//*[@id='{id_prefix}res_band1']") is None:
            return
        try:
            res, tolerance = get_resistance_from_value(value)
            power = math.floor(res.log10()) - 1
            res = int(res / 10 ** power)
            resistor_colors = [
                self._plotter._get_style("tht-resistor-band-colors", int(str(res)[0])),
                self._plotter._get_style("tht-resistor-band-colors", int(str(res)[1])),
                self._plotter._get_style("tht-resistor-band-colors", int(power)),
                self._plotter._get_style("tht-resistor-band-colors", tolerance)
            ]

            if ref in self.resistor_values:
                if self.resistor_values[ref].flip_bands:
                    resistor_colors.reverse()

            for res_i, res_c in enumerate(resistor_colors):
                band = root.find(f".//*[@id='{id_prefix}res_band{res_i+1}']")
                s = band.attrib["style"].split(";")
                for i in range(len(s)):
                    if s[i].startswith('fill:'):
                        s_split = s[i].split(':')
                        s_split[1] = res_c
                        s[i] = ':'.join(s_split)
                    elif s[i].startswith('display:'):
                        s_split = s[i].split(':')
                        s_split[1] = 'inline'
                        s[i] = ':'.join(s_split)
                band.attrib["style"] = ";".join(s)
        except UserWarning as e:
            self._plotter.yield_warning("resistor", f"Cannot color-code resistor {ref}: {e}")
            return

    def _get_resistance_from_value(self, value: str) -> Tuple[Decimal, str]:
        res, tolerance = None, "5%"
        try:
            value = value.split(" ", maxsplit=1)
            res = engineering_notation.EngNumber(value[0]).number
            if len(value) > 1:
                t_string = value[1].strip().replace(" ", "")
                if "%" in t_string:
                    if t_string.strip() in self._plotter.get_style("tht-resistor-band-colors"):
                        raise UserWarning(f"Invalid resistor tolerance {value[1]}")
                    tolerance = t_string
        except decimal.InvalidOperation:
            raise UserWarning(f"Invalid value {value}") from None
        return res, tolerance


@dataclass
class PlotPlaceholders:
    def render(self, plotter: PcbPlotter) -> None:
        self._plotter = plotter
        plotter.walk_components(invert_side=False, callback=self._append_placeholder)

    def _append_placeholder(self, lib: str, name: str, ref: str, value: str,
                          position: Tuple[int, int, float]) -> None:
        p = etree.Element("rect",
            x=str(ki2svg(position[0] - mm2ki(0.5))),
            y=str(ki2svg(position[1] - mm2ki(0.5))),
            width=str(ki2svg(mm2ki(1))), height=str(ki2svg(mm2ki(1))), style="fill:red;")
        self._plotter.append_component_element(p)

@dataclass
class PlotVCuts:
    layer: int = pcbnew.Cmts_User

    def render(self, plotter: PcbPlotter):
        self._plotter = plotter
        self._plotter.execute_plot_plan([
            PlotAction("vcuts", [self.layer], self._process_vcuts)
        ])

    def _process_vcuts(self, name: str, source_filename: str) -> None:
        layer = etree.Element("g", id="substrate-vcuts",
            style="fill:{0}; stroke:{0};".format(self._plotter.get_style("vcut")))
        for element in extract_svg_content(read_svg_unique(source_filename)):
            # Forbidden colors = workaround - KiCAD plots vias white
            # See https://gitlab.com/kicad/code/kicad/-/issues/10491
            if not strip_style_svg(element, keys=["fill", "stroke"],
                                   forbidden_colors=["#ffffff"]):
                layer.append(element)
        self._plotter.append_board_element(layer)

@dataclass
class PlotPaste:
    def render(self, plotter: PcbPlotter):
        plan: List[PlotAction] = []
        if plotter.render_back:
            plan = [PlotAction("paste", [pcbnew.B_Paste], self._process_paste)]
        else:
            plan = [PlotAction("paste", [pcbnew.F_Paste], self._process_paste)]
        self._plotter = plotter
        self._plotter.execute_plot_plan(plan)

    def _process_paste(self, name: str, source_filename: str) -> None:
        layer = etree.Element("g", id="substrate-paste",
            style="fill:{0}; stroke:{0};".format(self._plotter.get_style("paste")))
        for element in extract_svg_content(read_svg_unique(source_filename)):
            if not strip_style_svg(element, keys=["fill", "stroke"],
                                   forbidden_colors=["#ffffff"]):
                layer.append(element)
        self._plotter.append_board_element(layer)


class PcbPlotter():
    """
    PcbPlotter encapsulates all the machinery with PcbDraw plotting of SVG. It
    mainly serves as a builder (to step-by-step specify all options) and also to
    avoid passing many arguments between auxiliary functions
    """
    def __init__(self, boardFile: str):
        try:
            self.board = pcbnew.LoadBoard(boardFile)
        except IOError:
            raise IOError(f"Cannot open board '{boardFile}'") from None
        self.render_back = False
        self.mirror = False
        self.plot_plan = [
            PlotSubstrate(),
            PlotComponents(),
        ]

        self.data_path: List[str] = [] # Base paths for libraries lookup
        self.libs: List[str] = [] # Names of available libraries
        self._libs_path: List[str] = []
        self.style: any = {}     # Color scheme
        self.margin: float = 0 # Margin of the resulting document

        self.yield_warning: Callable[[str, str], None] = lambda tag, msg: None # Handle warnings

    def plot(self) -> etree.ElementTree:
        """
        Plot the board based on the arguments stored in this class. Returns
        SVG tree that you can either save or post-process as you wish.
        """
        self._build_libs_path()
        self._setup_document(self.render_back, self.mirror)
        for plotter in self.plot_plan:
            plotter.render(self)
        remove_empty_elems(self._document.getroot())
        remove_inkscape_annotation(self._document.getroot())
        shrink_svg(self._document, self.margin)
        return self._document


    def walk_components(self, invert_side: bool,
            callback: Callable[[str, str, str, str, Tuple[int, int, float]], None]) -> None:
        """
        Invokes callback on all components in the board. The callback takes:
        - library name of the component
        - footprint name of the component
        - reference of the component
        - value of the component
        - position of the component

        The position is adjusted based on what side we are rendering
        """
        render_back = not self.render_back if invert_side else self.render_back
        for footprint in self.board.GetFootprints():
            if (str(footprint.GetLayerName()) in ["Back", "B.Cu"] and not render_back) or \
               (str(footprint.GetLayerName()) in ["Top", "F.Cu"]  and     render_back):
                continue
            lib = str(footprint.GetFPID().GetLibNickname()).strip()
            name = str(footprint.GetFPID().GetLibItemName()).strip()
            value = footprint.GetValue().strip()
            ref = footprint.GetReference().strip()
            center = footprint.GetPosition()
            orient = math.radians(footprint.GetOrientation() / 10)
            pos = (center.x, center.y, orient)
            callback(lib, name, ref, value, pos)

    def get_def_slot(self, tag_name: str, id: str) -> etree.SubElement:
        """
        Creates a new definition slot and returns the tag
        """
        return etree.SubElement(self._defs, tag_name, id=id)

    def append_board_element(self, element: etree.Element) -> None:
        """
        Add new element into the board container
        """
        self._board_cont.append(element)

    def append_component_element(self, element: etree.Element) -> None:
        """
        Add new element into board container
        """
        self._comp_cont.append(element)

    def append_highlight_element(self, element: etree.Element) -> None:
        """
        Add new element into highlight container
        """
        self._high_cont.append(element)

    def setup_builtin_data_path(self):
        """
        Add PcbDraw built-in libraries to the search path for libraries
        """
        self.data_path.append(os.path.join(PKG_BASE, "footprints"))
        self.data_path.append(os.path.join(PKG_BASE, "styles"))

    def setup_global_data_path(self):
        """
        Add global installation paths to the search path for libraries.
        """
        share = os.path.join('share', 'pcbdraw')
        entries = len(self.data_path)
        scheme_names = sysconfig.get_scheme_names()
        if os.name == 'posix':
            if 'posix_user' in scheme_names:
                self.data_path.append(os.path.join(sysconfig.get_path('data', 'posix_user'), share))
            if 'posix_prefix' in scheme_names:
                self.data_path.append(os.path.join(sysconfig.get_path('data', 'posix_prefix'), share))
        elif os.name == 'nt':
            if 'nt_user' in scheme_names:
                self.data_path.append(os.path.join(sysconfig.get_path('data', 'nt_user'), share))
            if 'nt' in scheme_names:
                self.data_path.append(os.path.join(sysconfig.get_path('data', 'nt'), share))
        if len(self.data_path) == entries:
            self.data_path.append(os.path.join(sysconfig.get_path('data'), share))

    def setup_arbitrary_data_path(self, path: str) -> None:
        """
        Add an arbitrary data path
        """
        self.data_path.append(os.path.realpath(path))

    def setup_env_data_path(self) -> None:
        """
        Add search paths from the env variable PCBDRAW_LIB_PATH
        """
        paths = os.environ.get("PCBDRAW_LIB_PATH", "").split(":")
        self.data_path += filter(lambda x: len(x) > 0, paths)

    def resolve_style(self, name: str) -> None:
        """
        Given a name of style, find the corresponding file and load it
        """
        path = self._find_data_file(name, ".json")
        if path is None:
            raise RuntimeError(f"Cannot locate resource {name}; explored paths:\n"
                + "\n".join([f"- {x}" for x in self.data_path]))
        self.style = load_style(name)

    def _find_data_file(self, name: str, extension: str) -> Optional[str]:
        if not name.endswith(extension):
            name += extension
        if os.path.isfile(name):
            return name
        for path in self.data_path:
            fname = os.path.join(path, name)
            if os.path.isfile(fname):
                return fname
        return None

    def _build_libs_path(self) -> None:
        self._libs_path = []
        for l in self.libs:
            self._libs_path += [os.path.join(p, l) for p in self.data_path]
        self._libs_path = [x for x in self._libs_path if os.path.exists(x)]
        print(self.libs)
        print(self.data_path)
        print(self._libs_path)

    def _get_model_file(self, lib, name) -> Optional[str]:
        """
        Find model file in the configured libraries. If it doesn't exists,
        return None.
        """
        for path in self._libs_path:
            f = os.path.join(path, lib, name + ".svg")
            if os.path.isfile(f):
                return f

    def get_style(self, *args: List[str]) -> any:
        try:
            value = self.style
            for key in args:
                value = value[key]
            return value
        except KeyError:
            try:
                value = default_style
                for key in args:
                    value = value[key]
                return value
            except KeyError as e:
                raise e from None

    def execute_plot_plan(self, to_plot: List[PlotAction]) -> None:
        """
        Given a plotting plan, plots the layers and invokes a post-processing
        callback on the generated files
        """
        with tempfile.TemporaryDirectory() as tmp:
            pctl = pcbnew.PLOT_CONTROLLER(self.board)
            popt = pctl.GetPlotOptions()
            popt.SetOutputDirectory(tmp)
            popt.SetScale(1)
            popt.SetMirror(False)
            popt.SetSubtractMaskFromSilk(True)
            try:
                popt.SetPlotOutlineMode(False)
            except:
                # Method does not exist in older versions of KiCad
                pass
            popt.SetTextMode(pcbnew.PLOT_TEXT_MODE_STROKE)
            for action in to_plot:
                pctl.OpenPlotfile(action.name, pcbnew.PLOT_FORMAT_SVG, action.name)
                for l in action.layers:
                    pctl.SetColorMode(False)
                    pctl.SetLayer(l)
                    pctl.PlotLayer()
            pctl.ClosePlot()
            for action in to_plot:
                for svg_file in os.listdir(tmp):
                    if svg_file.endswith(f"-{action.name}.svg"):
                        action.action(action.name, os.path.join(tmp, svg_file))

    def _setup_document(self, render_back: bool, mirror: bool) -> None:
        bb = self.board.ComputeBoundingBox()
        transform_string = ""
        # Let me briefly explain what's going on. KiCAD outputs SVG in user units,
        # where 1 unit is 1/10 of an inch (in v5) or KiCAD native unit (v6). So to
        # make our life easy, we respect it and make our document also in the
        # corresponding units. Therefore we specify the outer dimensions in
        # millimeters and specify the board area.
        if(render_back ^ mirror):
            transform_string = "scale(-1,1)"
            self._document = empty_svg(
                width=f"{ki2mm(bb.GetWidth())}mm",
                height=f"{ki2mm(bb.GetHeight())}mm",
                viewBox=f"{ki2svg(-bb.GetWidth() - bb.GetX())} {ki2svg(bb.GetY())} {ki2svg(bb.GetWidth())} {ki2svg(bb.GetHeight())}")
        else:
            self._document = empty_svg(
                width=f"{ki2mm(bb.GetWidth())}mm",
                height=f"{ki2mm(bb.GetHeight())}mm",
                viewBox=f"{ki2svg(bb.GetX())} {ki2svg(bb.GetY())} {ki2svg(bb.GetWidth())} {ki2svg(bb.GetHeight())}")

        self._defs = etree.SubElement(self._document.getroot(), "defs")
        self._board_cont = etree.SubElement(self._document.getroot(), "g", transform=transform_string)
        if self.get_style("highlight-on-top"):
            self._comp_cont = etree.SubElement(self._document.getroot(), "g", transform=transform_string)
            self._high_cont = etree.SubElement(self._document.getroot(), "g", transform=transform_string)
        else:
            self._high_cont = etree.SubElement(self._document.getroot(), "g", transform=transform_string)
            self._comp_cont = etree.SubElement(self._document.getroot(), "g", transform=transform_string)

        self._board_cont.attrib["id"] = "boardContainer"
        self._comp_cont.attrib["id"] = "componentContainer"
        self._high_cont.attrib["id"] = "highlightContainer"

