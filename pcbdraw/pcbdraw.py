#!/usr/bin/env python3

import argparse
import json
import math
import os
import re
import sys
import tempfile
import sysconfig
import numpy as np
import svgpathtools
import engineering_notation
import decimal

from pcbnewTransition import pcbnew, KICAD_VERSION, isV6
from lxml import etree, objectify

from pcbdraw import convert


# Give more priority to local modules than installed versions
PKG_BASE = os.path.dirname(__file__)
sys.path.insert(0, os.path.dirname(os.path.abspath(PKG_BASE)))
from pcbdraw import __version__

etree.register_namespace("xlink", "http://www.w3.org/1999/xlink")

STYLES_SUBDIR = 'styles'
FOOTPRINTS_SUBDIR = 'footprints'
data_path = [PKG_BASE]

default_style = {
    "copper": "#417e5a",
    "board": "#4ca06c",
    "silk": "#f0f0f0",
    "pads": "#b5ae30",
    "outline": "#000000",
    "clad": "#9c6b28",
    "vcut": "#bf2600",
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
    return val * 1000000

# KiCAD 5 and KiCAD 6 use different units of the SVG
ki2svg = (lambda x: x) if isV6(KICAD_VERSION) else ki2dmil
svg2ki = (lambda x: x) if isV6(KICAD_VERSION) else dmil2ki

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

def read_svg_unique(filename, return_prefix = False):
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
    if return_prefix:
        return root, prefix
    return root

def extract_svg_content(root):
    # Remove SVG namespace to ease our lives and change ids
    for el in root.getiterator():
        if '}' in str(el.tag):
            el.tag = el.tag.split('}', 1)[1]
    return [ x for x in root if x.tag and x.tag not in ["title", "desc"]]

def strip_fill_svg(root, forbidden_colors):
    keys = ["fill", "stroke"]
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

def process_board_substrate_layer(container, defs, name, source, colors, boardsize):
    layer = etree.SubElement(container, "g", id="substrate-" + name,
        style="fill:{0}; stroke:{0};".format(colors[name]))
    if name == "pads":
        layer.attrib["mask"] = "url(#pads-mask)"
    if name == "silk":
        layer.attrib["mask"] = "url(#pads-mask-silkscreen)"
    for element in extract_svg_content(read_svg_unique(source)):
        # Forbidden colors = workaround - KiCAD plots vias white
        # See https://gitlab.com/kicad/code/kicad/-/issues/10491
        if not strip_fill_svg(element, forbidden_colors=["#ffffff"]):
            layer.append(element)

def process_board_substrate_base(container, defs, name, source, colors, boardsize):
    clipPath = etree.SubElement(defs, "clipPath")
    clipPath.attrib["id"] = "cut-off"
    clipPath.append(get_board_polygon(extract_svg_content(read_svg_unique(source))))

    layer = etree.SubElement(container, "g", id="substrate-"+name,
        style="fill:{0}; stroke:{0};".format(colors[name]))
    layer.append(get_board_polygon(extract_svg_content(read_svg_unique(source))))
    outline = etree.SubElement(layer, "g",
        style="fill:{0}; stroke: {0};".format(colors["outline"]))
    for element in extract_svg_content(read_svg_unique(source)):
        # Forbidden colors = workaround - KiCAD plots vias white
        # See https://gitlab.com/kicad/code/kicad/-/issues/10491
        if not strip_fill_svg(element, forbidden_colors=["#ffffff"]):
            layer.append(element)

def process_board_substrate_mask(container, defs, name, source, colors, boardsize):
    mask = etree.SubElement(defs, "mask")
    mask.attrib["id"] = name
    for element in extract_svg_content(read_svg_unique(source)):
        for item in element.getiterator():
            if "style" in item.attrib:
                # KiCAD plots in black, for mask we need white
                item.attrib["style"] = item.attrib["style"].replace("#000000", "#ffffff")
        mask.append(element)
    silkMask = etree.SubElement(defs, "mask")
    silkMask.attrib["id"] = name + "-silkscreen"
    bg = etree.SubElement(silkMask, "rect", attrib={
        "x": str(ki2svg(boardsize.GetX())),
        "y": str(ki2svg(boardsize.GetY())),
        "width": str(ki2svg(boardsize.GetWidth())),
        "height": str(ki2svg(boardsize.GetHeight())),
        "fill": "white"
    })
    for element in extract_svg_content(read_svg_unique(source)):
        # KiCAD plots black, no need to change fill
        silkMask.append(element)

def get_layers(board, colors, defs, toPlot):
    """
    Plot given layers, process them and return them as <g>
    """
    container = etree.Element('g')
    with tempfile.TemporaryDirectory() as tmp:
        pctl = pcbnew.PLOT_CONTROLLER(board)
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
        for f, layers, _ in toPlot:
            pctl.OpenPlotfile(f, pcbnew.PLOT_FORMAT_SVG, f)
            for l in layers:
                pctl.SetColorMode(False)
                pctl.SetLayer(l)
                pctl.PlotLayer()
        pctl.ClosePlot()
        boardsize = board.ComputeBoundingBox()
        for f, _, process in toPlot:
            for svg_file in os.listdir(tmp):
                if svg_file.endswith("-" + f + ".svg"):
                    process(container, defs, f, os.path.join(tmp, svg_file), colors, boardsize)
    return container

def get_board_substrate(board, colors, defs, holes, back):
    """
    Plots all front layers from the board and arranges them in a visually appealing style.
    return SVG g element with the board substrate
    """
    toPlot = []
    if back:
        toPlot = [
            ("board", [pcbnew.Edge_Cuts], process_board_substrate_base),
            ("clad", [pcbnew.B_Mask], process_board_substrate_layer),
            ("copper", [pcbnew.B_Cu], process_board_substrate_layer),
            ("pads", [pcbnew.B_Cu], process_board_substrate_layer),
            ("pads-mask", [pcbnew.B_Mask], process_board_substrate_mask),
            ("silk", [pcbnew.B_SilkS], process_board_substrate_layer),
            ("outline", [pcbnew.Edge_Cuts], process_board_substrate_layer)]
    else:
        toPlot = [
            ("board", [pcbnew.Edge_Cuts], process_board_substrate_base),
            ("clad", [pcbnew.F_Mask], process_board_substrate_layer),
            ("copper", [pcbnew.F_Cu], process_board_substrate_layer),
            ("pads", [pcbnew.F_Cu], process_board_substrate_layer),
            ("pads-mask", [pcbnew.F_Mask], process_board_substrate_mask),
            ("silk", [pcbnew.F_SilkS], process_board_substrate_layer),
            ("outline", [pcbnew.Edge_Cuts], process_board_substrate_layer)]
    container = etree.Element('g')
    container.attrib["clip-path"] = "url(#cut-off)"

    with tempfile.TemporaryDirectory() as tmp:
        pctl = pcbnew.PLOT_CONTROLLER(board)
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
        for f, layers, _ in toPlot:
            pctl.OpenPlotfile(f, pcbnew.PLOT_FORMAT_SVG, f)
            for l in layers:
                pctl.SetColorMode(False)
                pctl.SetLayer(l)
                pctl.PlotLayer()
        pctl.ClosePlot()
        boardsize = board.ComputeBoundingBox()
        for f, _, process in toPlot:
            for svg_file in os.listdir(tmp):
                if svg_file.endswith("-" + f + ".svg"):
                    process(container, defs, f, os.path.join(tmp, svg_file), colors, boardsize)
    if holes:
        get_hole_mask(board, defs)
        container.attrib["mask"] = "url(#hole-mask)"
    return container

def walk_components(board, back, export):
    for module in board.GetFootprints():
        # Top is for Eagle boards imported to KiCAD
        if (str(module.GetLayerName()) in ["Back", "B.Cu"] and not  back) or \
           (str(module.GetLayerName()) in ["Top", "F.Cu"]  and      back):
            continue
        lib = str(module.GetFPID().GetLibNickname()).strip()
        try:
            name = str(module.GetFPID().GetFootprintName()).strip()
        except AttributeError:
            # it seems we are working on Kicad >4.0.6, which has a changed method name
            name = str(module.GetFPID().GetLibItemName()).strip()
        value = module.GetValue().strip()
        ref = module.GetReference().strip()
        center = module.GetPosition()
        orient = math.radians(module.GetOrientation() / 10)
        pos = (center.x, center.y, orient)
        export(lib, name, value, ref, pos)

def get_hole_mask(board, defs):
    mask = etree.SubElement(defs, "mask", id="hole-mask")
    container = etree.SubElement(mask, "g")

    bb = board.ComputeBoundingBox()
    bg = etree.SubElement(container, "rect", x="0", y="0", fill="white")
    bg.attrib["x"] = str(ki2svg(bb.GetX()))
    bg.attrib["y"] = str(ki2svg(bb.GetY()))
    bg.attrib["width"] = str(ki2svg(bb.GetWidth()))
    bg.attrib["height"] = str(ki2svg(bb.GetHeight()))

    toPlot = [] # Tuple: position, orientation, drillsize
    for module in board.GetFootprints():
        if module.GetPadCount() == 0:
            continue
        for pad in module.Pads():
            toPlot.append((
                pad.GetPosition(),
                pad.GetOrientation(),
                pad.GetDrillSize()
            ))
    for track in board.GetTracks():
        if not isinstance(track, pcbnew.PCB_VIA) or not isV6(KICAD_VERSION):
            continue
        toPlot.append((
            track.GetPosition(),
            0,
            (track.GetDrillValue(), track.GetDrillValue())
        ))
    for pos, padOrientation, drillSize in toPlot:
        pos.x = ki2svg(pos.x)
        pos.y = ki2svg(pos.y)
        size = list(map(ki2svg, drillSize))
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
                pos.x, pos.y, -padOrientation / 10)

def get_model_file(paths, lib, name, ref, remapping):
    """ Find model file in library considering component remapping """
    for path in paths:
        if ref in remapping:
            lib, new_name = tuple(remapping[ref].split(":"))
            if name.endswith(".back"):
                name = new_name + ".back"
            else:
                name = new_name
        f = os.path.join(path, lib, name + ".svg")
        if os.path.isfile(f):
            return f
    return None

def print_component(paths, lib, name, value, ref, pos, remapping={}):
    f = get_model_file(paths, lib, name, ref, remapping)
    msg = "{} with package {}:{} at [{},{},{}] -> {}".format(
        ref, lib, name, pos[0], pos[1], math.degrees(pos[2]), f if f else "Not found")
    print(msg)

def component_to_board_scale(svg):
    width = ki2svg(to_kicad_basic_units(svg.attrib["width"]))
    height = ki2svg(to_kicad_basic_units(svg.attrib["height"]))
    x, y, vw, vh = [float(x) for x in svg.attrib["viewBox"].split()]
    return width / vw, height / vh

def get_resistance_from_value(value, ref, style, silent):
    res, tollerance = None, '5%'
    try:
        value = value.split(' ')
        res = engineering_notation.EngNumber(value[0])
        res = res.number
        if len(value) > 1:
            if '%' in value[1]:
                if value[1] not in style["tht-resistor-band-colors"]:
                    raise UserWarning("Resistor's tolerance is invalid")
                tollerance = value[1]
    except decimal.InvalidOperation:
        if not silent:
            print("Resistor {}'s value is invalid".format(ref))
    except UserWarning:
        if not silent:
            print("Resistor {}'s tollerance ({}) is invalid, assuming 5%".format(ref, value[1]))

    return res, tollerance

def color_resistor(ref, svg_prefix, res, tolerance, style, tht_resistor_settings, componentElement):
    if res is not None:
        power = math.floor(res.log10())-1
        res = int(res / 10**power)
        resistor_colors = [
            style["tht-resistor-band-colors"][int(str(res)[0])],
            style["tht-resistor-band-colors"][int(str(res)[1])],
            style["tht-resistor-band-colors"][int(power)],
            style["tht-resistor-band-colors"][tolerance],
        ]
        if tht_resistor_settings is not None:
            if ref in tht_resistor_settings:
                if 'flip' in tht_resistor_settings[ref]:
                    if tht_resistor_settings[ref]['flip']:
                        resistor_colors.reverse()

        for res_i, res_c in enumerate(resistor_colors):
            band = componentElement.find(".//*[@id='{}res_band{}']".format(svg_prefix, res_i+1))
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

def component_from_library(lib, name, value, ref, pos, usedComponents, comp,
                           highlight, silent, no_warn_back, style, tht_resistor_settings):

    if not name:
        return
    if comp["filter"] is not None and ref not in comp["filter"]:
        return

    # If the part is a THT resistor, change it's value if the parameter custom_res_color has
    if tht_resistor_settings is not None:
        if ref in tht_resistor_settings:
            if 'override_val' in tht_resistor_settings[ref]:
                value = tht_resistor_settings[ref]['override_val']

    unique_name = f"{lib}__{name}_{value}"
    if unique_name in usedComponents:
        componentInfo = usedComponents[unique_name]
        componentElement = etree.Element("use", attrib={"{http://www.w3.org/1999/xlink}href": "#" + componentInfo["id"]})
    else:
        f = get_model_file(comp["libraries"], lib, name, ref, comp["remapping"])
        if not f:
            if not silent:
                if name[-5:] != '.back' or not no_warn_back:
                    print("Warning: component '{}' for footprint '{}' from library '{}' was not found".format(name, ref, lib))
            if comp["placeholder"]:
                etree.SubElement(comp["container"], "rect", x=str(ki2svg(pos[0] - mm2ki(0.5))), y=str(ki2svg(pos[1] - mm2ki(0.5))),
                                width=str(ki2svg(mm2ki(1))), height=str(ki2svg(mm2ki(1))), style="fill:red;")
            return
        xml_id = make_XML_identifier(unique_name)
        componentElement = etree.Element("g", attrib={"id": xml_id})
        svg_tree, svg_prefix = read_svg_unique(f, True)
        for x in extract_svg_content(svg_tree):
            if x.tag in ["namedview", "metadata"]:
                continue
            componentElement.append(x)
        origin_x = 0
        origin_y = 0
        origin = componentElement.find(".//*[@id='origin']")
        if origin is not None:
            origin_x, origin_y = element_position(origin, root=componentElement)
            origin.getparent().remove(origin)
        else:
            print("Warning: component '{}' from library '{}' has no ORIGIN".format(name, lib))
        svg_scale_x, svg_scale_y = component_to_board_scale(svg_tree)
        componentInfo = {
            "id": xml_id,
            "origin_x": origin_x,
            "origin_y": origin_y,
            "scale_x": svg_scale_x,
            "scale_y": svg_scale_y,
            "width": svg_tree.attrib["width"],
            "height": svg_tree.attrib["height"]
        }
        usedComponents[unique_name] = componentInfo

        # If the library used is the THT resistor one, attempt to change the band colors if they exsist
        if componentElement.find(".//*[@id='{}res_band1']".format(svg_prefix)) is not None:
            res, tolerance = get_resistance_from_value(value, ref, style, value)
            if res is not None:
                color_resistor(ref, svg_prefix, res, tolerance, style, tht_resistor_settings, componentElement)

    comp["container"].append(etree.Comment("{}:{}".format(lib, name)))
    r = etree.SubElement(comp["container"], "g")
    r.append(componentElement)
    svg_scale_x = componentInfo["scale_x"]
    svg_scale_y = componentInfo["scale_y"]
    origin_x = componentInfo["origin_x"]
    origin_y = componentInfo["origin_y"]
    width = componentInfo["width"]
    height = componentInfo["height"]

    r.attrib["transform"] = \
        f"translate({ki2svg(pos[0])} {ki2svg(pos[1])}) " + \
        f"scale({svg_scale_x} {svg_scale_y}) " + \
        f"rotate({-math.degrees(pos[2])}) " + \
        f"translate({-origin_x}, {-origin_y})"
    if ref in highlight["items"]:
        w = ki2svg(to_kicad_basic_units(width))
        h = ki2svg(to_kicad_basic_units(height))
        build_highlight(highlight, w, h, pos, (origin_x, origin_y), (svg_scale_x, svg_scale_y), ref)

def build_highlight(preset, width, height, pos, origin, scale, ref):
    h = etree.SubElement(preset["container"], "rect")
    h.attrib["style"] = preset["style"]
    h.attrib["x"] = str(-preset["padding"])
    h.attrib["y"] = str(-preset["padding"])
    h.attrib["width"] = str(width / scale[0] + 2 * preset["padding"])
    h.attrib["height"] = str(height / scale[1] + 2 * preset["padding"])
    h.attrib["transform"] = \
        f"translate({ki2svg(pos[0])} {ki2svg(pos[1])}) " + \
        f"scale({scale[0]} {scale[1]}) " + \
        f"rotate({-math.degrees(pos[2])}) " + \
        f"translate({-origin[0]}, {-origin[1]})"
    h.attrib["id"] = "h_" + ref

def find_data_file(name, ext, subdir):
    if os.path.isfile(name):
        return name
    # Not a file here, needs extension?
    ln = len(ext)
    if name[-ln:] != ext:
        name += ext
        if os.path.isfile(name):
            return name
    # Try in the data path
    for p in data_path:
        fn = os.path.join(p, subdir, name)
        if os.path.isfile(fn):
            return fn
    raise RuntimeError("Missing '" + subdir + "' " + name)

def load_style(style_file):
    if style_file.startswith("builtin:"):
        STYLES = os.path.join(PKG_BASE, "styles")
        style_file = os.path.join(STYLES, style_file[len("builtin:"):])
    else:
        style_file = find_data_file(style_file, '.json', STYLES_SUBDIR)
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
    extra = set(style.keys()) - required
    for x in extra:
        print("Warning: extra key '" + x + "' in style")
    # ToDo: Check validity of colors (SVG compatible format)
    return style

def load_remapping(remap_file):
    if not remap_file:
        return {}
    try:
        with open(remap_file, "r") as f:
            return json.load(f)
    except IOError:
        raise RuntimeError("Cannot open remapping file " + remap_file)

def adjust_lib_path(path):
    if path == "default" or path == "kicad-default":
        return [os.path.join(p, FOOTPRINTS_SUBDIR, "KiCAD-base") for p in data_path]
    if path == "eagle-default":
        return [os.path.join(p, FOOTPRINTS_SUBDIR, "Eagle-export") for p in data_path]
    return [path]

def setup_data_path():
    global data_path
    share = os.path.join('share', 'pcbdraw')
    entries = len(data_path)
    scheme_names = sysconfig.get_scheme_names()
    if os.name == 'posix':
        if 'posix_user' in scheme_names:
            data_path.append(os.path.join(sysconfig.get_path('data', 'posix_user'), share))
        if 'posix_prefix' in scheme_names:
            data_path.append(os.path.join(sysconfig.get_path('data', 'posix_prefix'), share))
    elif os.name == 'nt':
        if 'nt_user' in scheme_names:
            data_path.append(os.path.join(sysconfig.get_path('data', 'nt_user'), share))
        if 'nt' in scheme_names:
            data_path.append(os.path.join(sysconfig.get_path('data', 'nt'), share))
    if len(data_path) == entries:
        data_path.append(os.path.join(sysconfig.get_path('data'), share))

def merge_bbox(left, right):
    """
    Merge bounding boxes in format (xmin, xmax, ymin, ymax)
    """
    return tuple([
        f(l, r) for l, r, f in zip(left, right, [min, max, min, max])
    ])

def shrink_svg(svgfilepath, shrinkBorder):
    """
    Shrink the SVG canvas to the size of the drawing
    """
    document = svgpathtools.Document(svgfilepath)
    paths = document.paths()
    if len(paths) == 0:
        return
    bbox = paths[0].bbox()
    for x in paths:
        bbox = merge_bbox(bbox, x.bbox())
    bbox = list(bbox)
    bbox[0] -= ki2svg(mm2ki(shrinkBorder))
    bbox[1] += ki2svg(mm2ki(shrinkBorder))
    bbox[2] -= ki2svg(mm2ki(shrinkBorder))
    bbox[3] += ki2svg(mm2ki(shrinkBorder))
    svg = document.tree
    root = svg.getroot()
    root.attrib["viewBox"] = "{} {} {} {}".format(
        bbox[0], bbox[2],
        bbox[1] - bbox[0], bbox[3] - bbox[2]
    )
    root.attrib["width"] = str(ki2mm(svg2ki(bbox[1] - bbox[0]))) + "mm"
    root.attrib["height"] = str(ki2mm(svg2ki(bbox[3] - bbox[2]))) + "mm"
    document.save(svgfilepath)

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

def postprocess_svg(svgfilepath, shrinkBorder):
    if shrinkBorder is not None:
        shrink_svg(svgfilepath, shrinkBorder)
    # TBA: Add compression and optimization

def main():
    setup_data_path()
    epilog = "Searching for styles on: "
    c = len(data_path)
    for i, path in enumerate(data_path):
        epilog += "'"+os.path.join(path, 'styles')+"'"
        if i == c-2:
            epilog += " and "
        elif i != c-1:
            epilog += ", "

    parser = argparse.ArgumentParser(epilog=epilog)
    parser.add_argument("--version", action="version", version=f"PcbDraw {__version__}")
    parser.add_argument("-s", "--style", help="JSON file with board style")
    parser.add_argument("board", help=".kicad_pcb file to draw")
    parser.add_argument("output", help="destination for final SVG or PNG file")
    parser.add_argument("-l", "--libs", help="comma separated list of libraries; use default, kicad-default or eagle-default for built-in libraries", default="default")
    parser.add_argument("-p", "--placeholder", action="store_true",
                        help="show placeholder for missing components")
    parser.add_argument("-m", "--remap",
                        help="JSON file with map part reference to <lib>:<model> to remap packages")
    parser.add_argument("-c", "--list-components", action="store_true",
                        help="Dry run, just list the components")
    parser.add_argument("--no-drillholes", action="store_true", help="Do not make holes transparent")
    parser.add_argument("-b","--back", action="store_true", help="render the backside of the board")
    parser.add_argument("--mirror", action="store_true", help="mirror the board")
    parser.add_argument("-a", "--highlight", help="comma separated list of components to highlight")
    parser.add_argument("-f", "--filter", help="comma separated list of components to show")
    parser.add_argument("-v", "--vcuts", action="store_true", help="Render V-CUTS on the Cmts.User layer")
    parser.add_argument("--silent", action="store_true", help="Silent warning messages about missing footprints")
    parser.add_argument("--dpi", help="DPI for bitmap output", type=int, default=300)
    parser.add_argument("--no-warn-back", action="store_true", help="Don't show warnings about back footprints")
    parser.add_argument("--shrink", type=float, help="Shrink the canvas size to the size of the board. Specify border in millimeters")
    parser.add_argument("--resistor-values", help="A comma seperated list of what value to set to each resistor for the band colors. For example, \"R1:10k,R2:470\"")
    parser.add_argument("--resistor-flip", help="A comma seperated list of throughole resistors to flip the bands")

    args = parser.parse_args()
    libs = []
    for path in args.libs.split(','):
        libs.extend(adjust_lib_path(path))
    args.libs = libs
    args.highlight = args.highlight.split(',') if args.highlight is not None else []
    args.filter = args.filter.split(',') if args.filter is not None else None

    try:
        if args.style:
            style = load_style(args.style)
        else:
            style = default_style
        remapping = load_remapping(args.remap)
    except RuntimeError as e:
        print(e)
        sys.exit(1)

    # Check if there any keys in the given style that aren't in the default style (all valid keys)
    for s in style:
        if s not in default_style:
            raise UserWarning(f"Key {s} from the given style is invalid")
    # If some keys aren't in the loaded style compared to the default style, copy it from the default style
    for s in default_style:
        if s not in style:
            style[s] = default_style[s]

    tht_resistor_settings = extract_resistor_settings(args)

    if os.path.splitext(args.output)[-1].lower() not in [".svg", ".png"]:
        print("Output can be either an SVG or PNG")
        sys.exit(1)

    try:
        board = pcbnew.LoadBoard(args.board)
    except IOError:
        print("Cannot open board " + args.board)
        sys.exit(1)

    if args.list_components:
        walk_components(board, args.back,lambda lib, name, val, ref, pos:
                        print_component(args.libs, lib, name, val, ref, pos,
                                        remapping=remapping))
        sys.exit(0)

    bb = board.ComputeBoundingBox()
    transform_string = ""
    # Let me briefly explain what's going on. KiCAD outputs SVG in user units,
    # where 1 unit is 1/10 of an inch (in v5) or KiCAD native unit (v6). So to
    # make our life easy, we respect it and make our document also in the
    # corresponding units. Therefore we specify the outer dimensions in
    # millimeters and specify the board area.
    document = empty_svg(
            width=f"{ki2mm(bb.GetWidth())}mm",
            height=f"{ki2mm(bb.GetHeight())}mm",
            viewBox=f"{ki2svg(bb.GetX())} {ki2svg(bb.GetY())} {ki2svg(bb.GetWidth())} {ki2svg(bb.GetHeight())}")
    if(args.back ^ args.mirror):
        transform_string = "scale(-1,1)"
        document = empty_svg(
            width=f"{ki2mm(bb.GetWidth())}mm",
            height=f"{ki2mm(bb.GetHeight())}mm",
            viewBox=f"{ki2svg(-bb.GetWidth() - bb.GetX())} {ki2svg(bb.GetY())} {ki2svg(bb.GetWidth())} {ki2svg(bb.GetHeight())}")

    defs = etree.SubElement(document.getroot(), "defs")
    board_cont = etree.SubElement(document.getroot(), "g", transform=transform_string)
    if style["highlight-on-top"]:
        comp_cont = etree.SubElement(document.getroot(), "g", transform=transform_string)
        high_cont = etree.SubElement(document.getroot(), "g", transform=transform_string)
    else:
        high_cont = etree.SubElement(document.getroot(), "g", transform=transform_string)
        comp_cont = etree.SubElement(document.getroot(), "g", transform=transform_string)

    board_cont.attrib["id"] = "boardContainer"
    comp_cont.attrib["id"] = "componentContainer"
    high_cont.attrib["id"] = "highlightContainer"

    components = {
        "container": comp_cont,
        "placeholder": args.placeholder,
        "remapping": remapping,
        "libraries": args.libs,
        "filter": args.filter
    }

    highlight = {
        "container": high_cont,
        "items": args.highlight,
        "style": style["highlight-style"],
        "padding": style["highlight-padding"]
    }

    board_cont.append(get_board_substrate(board, style, defs, not args.no_drillholes, args.back))
    if args.vcuts:
        board_cont.append(get_layers(board, style, defs, [("vcut", [pcbnew.Cmts_User], process_board_substrate_layer)]))

    usedComponents = {}
    walk_components(board, args.back, lambda lib, name, val, ref, pos:
        component_from_library(lib, name, val, ref, pos, usedComponents,
                               components, highlight, args.silent, args.no_warn_back, style, tht_resistor_settings))

    # make another pass for search, and if found, render the back side of the component
    # the function will search for file with extension ".back.svg"
    walk_components(board, not args.back, lambda lib, name, val, ref, pos:
        component_from_library(lib, name+".back", val, ref, pos, usedComponents,
                                components, highlight, args.silent, args.no_warn_back, style, tht_resistor_settings))

    remove_empty_elems(document.getroot())
    remove_inkscape_annotation(document.getroot())

    if args.output.endswith(".svg") or args.output.endswith(".SVG"):
        document.write(args.output)
        postprocess_svg(args.output, args.shrink)
    else:
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp_f:
            document.write(tmp_f)
            tmp_f.flush()
            postprocess_svg(tmp_f.name, args.shrink)
            tmp_f.flush()
            convert.svgToPng(tmp_f.name, args.output, dpi=args.dpi)
            tmp_f.close()
            os.unlink(tmp_f.name)

if __name__ == '__main__':
    main()
