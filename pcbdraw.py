#!/usr/bin/env python

import argparse
import json
import math
import os
import re
import shutil
import sys
import tempfile
import numpy as np

import pcbnew
from lxml import etree

default_style = {
    "copper": "#417e5a",
    "board": "#4ca06c",
    "silk": "#f0f0f0",
    "pads": "#b5ae30",
    "outline": "#000000",
    "highlight-on-top": False,
    "highlight-style": "stroke:none;fill:#ff0000;opacity:0.5;",
    "highlight-padding": 1.5,
    "highlight-offset": 0
}

float_re = r'([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)'

class SvgPathItem:
    def __init__(self, path):
        path = re.sub(r"([MLA])(\d+)", r"\1 \2", path)
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
            args = map(float, path[1:8])
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
    return val / 2540

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

def read_svg_unique(filename):
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
    if (sys.version_info > (3, 0)):
        root = etree.fromstring(bytes(content, 'utf-8'))
    else:
        root = etree.fromstring(content_byte)
    for el in root.getiterator():
        if "id" in el.attrib and el.attrib["id"] != "origin":
            el.attrib["id"] = prefix + el.attrib["id"]
    return root

def extract_svg_content(root):
    # Remove SVG namespace to ease our lifes and change ids
    for el in root.getiterator():
        if '}' in str(el.tag):
            el.tag = el.tag.split('}', 1)[1]
    return [ x for x in root if x.tag and x.tag not in ["title", "desc"]]

def strip_fill_svg(root):
    keys = ["fill", "stroke"]
    for el in root.getiterator():
        if "style" in el.attrib:
            s = el.attrib["style"].split(";")
            s = filter(lambda x: x.strip().split(":")[0] not in keys, s)
            el.attrib["style"] = ";".join(s).replace("  ", " ").strip()

def empty_svg(**attrs):
    document = etree.ElementTree(etree.fromstring(
        """<?xml version="1.0" standalone="no"?>
        <!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"
            "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
        <svg xmlns="http://www.w3.org/2000/svg" version="1.1"
            width="29.7002cm" height="21.0007cm" viewBox="0 0 116930 82680 ">
            <title>Picture generated by pcb2svg</title>
            <desc>Picture generated by pcb2svg</desc>
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
    outline = [elements[0]]
    elements = elements[1:]
    while True:
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
        if size == len(outline):
            first = True
            for x in outline:
                path += x.format(first)
                first = False
            if elements:
                outline = [elements[0]]
                elements = elements[1:]
            else:
                e = etree.Element("path", d=path, style="fill-rule=evenodd;")
                return e

def process_board_substrate_layer(container, name, source, colors):
    layer = etree.SubElement(container, "g", id="substrate-"+name,
        style="fill:{0}; stroke:{0};".format(colors[name]))
    if name == "pads":
        layer.attrib["mask"] = "url(#pads-mask)"
    for element in extract_svg_content(read_svg_unique(source)):
        strip_fill_svg(element)
        layer.append(element)

def process_board_substrate_base(container, name, source, colors):
    clipPath = etree.SubElement(etree.SubElement(container, "defs"), "clipPath")
    clipPath.attrib["id"] = "cut-off"
    clipPath.append(get_board_polygon(extract_svg_content(read_svg_unique(source))))

    layer = etree.SubElement(container, "g", id="substrate-"+name,
        style="fill:{0}; stroke:{0};".format(colors[name]))
    layer.append(get_board_polygon(extract_svg_content(read_svg_unique(source))))
    outline = etree.SubElement(layer, "g",
        style="fill:{0}; stroke: {0};".format(colors["outline"]))
    for element in extract_svg_content(read_svg_unique(source)):
        strip_fill_svg(element)
        outline.append(element)

def process_board_substrate_mask(container, name, source, colors):
    mask = etree.SubElement(etree.SubElement(container, "defs"), "mask")
    mask.attrib["id"] = name
    for element in extract_svg_content(read_svg_unique(source)):
        for item in element.getiterator():
            if "style" in item.attrib:
                # KiCAD plots in black, for mask we need white
                item.attrib["style"] = item.attrib["style"].replace("#000000", "#ffffff");
            mask.append(element)

def get_board_substrate(board, colors, holes, back):
    """
    Plots all front layers from the board and arranges them in a visually appealing style.
    return SVG g element with the board substrate
    """
    toPlot = []
    if(back):
        toPlot = [
            ("board", [pcbnew.Edge_Cuts], process_board_substrate_base),
            ("copper", [pcbnew.B_Cu], process_board_substrate_layer),
            ("pads", [pcbnew.B_Cu], process_board_substrate_layer),
            ("pads-mask", [pcbnew.B_Mask], process_board_substrate_mask),
            ("silk", [pcbnew.B_SilkS], process_board_substrate_layer),
            ("outline", [pcbnew.Edge_Cuts], process_board_substrate_layer)]
    else:
        toPlot = [
            ("board", [pcbnew.Edge_Cuts], process_board_substrate_base),
            ("copper", [pcbnew.F_Cu], process_board_substrate_layer),
            ("pads", [pcbnew.F_Cu], process_board_substrate_layer),
            ("pads-mask", [pcbnew.F_Mask], process_board_substrate_mask),
            ("silk", [pcbnew.F_SilkS], process_board_substrate_layer),
            ("outline", [pcbnew.Edge_Cuts], process_board_substrate_layer)]
    container = etree.Element('g')
    container.attrib["clip-path"] = "url(#cut-off)";
    tmp = tempfile.mkdtemp()
    pctl = pcbnew.PLOT_CONTROLLER(board)
    popt = pctl.GetPlotOptions()
    popt.SetOutputDirectory(tmp)
    popt.SetScale(1)
    popt.SetMirror(False)
    try:
        popt.SetPlotOutlineMode(False)
    except:
        # Method does not exist in older versions of KiCad
        pass
    popt.SetTextMode(pcbnew.PLOTTEXTMODE_STROKE)
    for f, layers, _ in toPlot:
        pctl.OpenPlotfile(f, pcbnew.PLOT_FORMAT_SVG, f)
        for l in layers:
            pctl.SetColorMode(False)
            pctl.SetLayer(l)
            pctl.PlotLayer()
    pctl.ClosePlot()
    for f, _, process in toPlot:
        for svg_file in os.listdir(tmp):
            if svg_file.endswith("-" + f + ".svg"):
                process(container, f, os.path.join(tmp, svg_file), colors)
    shutil.rmtree(tmp)

    if holes:
        container.append(get_hole_mask(board))
        container.attrib["mask"] = "url(#hole-mask)";
    return container

def walk_components(board, back, export):
    module = board.GetModules()
    while True:
        if not module:
            return
        # Top is for Eagle boards imported to KiCAD
        if (str(module.GetLayerName()) in ["Back", "B.Cu"] and not  back) or \
           (str(module.GetLayerName()) in ["Top", "F.Cu"]  and      back):
            module = module.Next()
            continue
        lib = str(module.GetFPID().GetLibNickname()).strip()
        try:
            name = str(module.GetFPID().GetFootprintName()).strip()
        except AttributeError:
            # it seems we are working on Kicad >4.0.6, which has a changed method name
            name = str(module.GetFPID().GetLibItemName()).strip()

        if (sys.version_info > (3, 0)):
            value = str(module.GetValue()).strip()
            ref = str(module.GetReference()).strip()
        else:
            value = unicode(module.GetValue()).strip()
            ref = unicode(module.GetReference()).strip()

        center = module.GetCenter()
        orient = math.radians(module.GetOrientation() / 10)
        pos = (center.x, center.y, orient)
        export(lib, name, value, ref, pos)
        module = module.Next()

def get_hole_mask(board):
    defs = etree.Element("defs")
    mask = etree.SubElement(defs, "mask", id="hole-mask")
    container = etree.SubElement(mask, "g")

    bb = board.ComputeBoundingBox();
    bg = etree.SubElement(container, "rect", x="0", y="0", fill="white")
    bg.attrib["x"] = str(ki2dmil(bb.GetX()))
    bg.attrib["y"] = str(ki2dmil(bb.GetY()))
    bg.attrib["width"] = str(ki2dmil(bb.GetWidth()))
    bg.attrib["height"] = str(ki2dmil(bb.GetHeight()))

    module = board.GetModules()
    while module:
        if module.GetPadCount() == 0:
            module = module.Next()
            continue
        pad = module.Pads()
        try:
            pad.GetPosition()
        except:
            # Newest nightly renames Pads to PadList
            pad = module.PadsList()
        orient = module.GetOrientation()
        while pad:
            pos = pad.GetPosition()
            pos.x = ki2dmil(pos.x)
            pos.y = ki2dmil(pos.y)
            size = map(ki2dmil, pad.GetDrillSize())
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
                    pos.x, pos.y, -orient)
            pad = pad.Next()
        module = module.Next()
    return defs

def get_model_file(paths, lib, name, ref, remapping):
    """ Find model file in library considering component remapping """
    for path in paths:
        if ref in remapping:
            lib, name = tuple(remapping[ref].split(":"))
        f = os.path.join(path, lib, name + ".svg")
        if os.path.isfile(f):
            return f
    return None

def print_component(paths, lib, name, value, ref, pos, remapping={}):
    f = get_model_file(paths, lib, name, ref, remapping)
    msg = "{} with package {}:{} at [{},{},{}] -> {}".format(
        ref, lib, name, pos[0], pos[1], math.degrees(pos[2]), f if f else "Not found")
    print(msg)

def component_from_library(lib, name, value, ref, pos, comp, highlight):
    if not name:
        return
    if comp["filter"] is not None and ref not in comp["filter"]:
        return
    f = get_model_file(comp["libraries"], lib, name, ref, comp["remapping"])
    if not f:
        print("Warning: component '{}' for footprint '{}' from library '{}' was not found".format(name, ref, lib))
        if comp["placeholder"]:
            etree.SubElement(comp["container"], "rect", x=str(ki2dmil(pos[0]) - 150), y=str(ki2dmil(pos[1]) - 150),
                             width="300", height="300", style="fill:red;")
        return
    comp["container"].append(etree.Comment("{}:{}".format(lib, name)))
    r = etree.SubElement(comp["container"], "g")
    svg_tree = read_svg_unique(f)
    for x in extract_svg_content(svg_tree):
        r.append(x)
    origin_x = 0
    origin_y = 0
    origin = r.find(".//*[@id='origin']")
    if origin is not None:
        origin_x, origin_y = element_position(origin, root=r)
        origin.getparent().remove(origin)
    else:
        print("Warning: component '{}' from library '{}' has no ORIGIN".format(name, lib))
    r.attrib["transform"] = "translate({} {}) scale(393.700787402) rotate({}) translate({}, {})".format(
            ki2dmil(pos[0]), ki2dmil(pos[1]),
            -math.degrees(pos[2]), -origin_x, -origin_y)
    if ref in highlight["items"]:
        if "width" in svg_tree.attrib and "height" in svg_tree.attrib:
            w = to_user_units(svg_tree.attrib["width"])
            h = to_user_units(svg_tree.attrib["height"])
            build_highlight(highlight, w, h, pos, (origin_x, origin_y), ref)
        elif "viewBox" in svg_tree.attrib:
            viewbox = re.split(" |,", svg_tree.attrib["viewBox"])
            w = to_user_units(viewbox[2])
            h = to_user_units(viewbox[3])
            build_highlight(highlight, w, h, pos, (origin_x, origin_y), ref)
        else:
            print("Warning: component '{}' from library '{}' has no viewBox. Cannot highlight".format(name, lib))

def build_highlight(preset, width, height, pos, origin, ref):
    h = etree.SubElement(preset["container"], "rect")
    scale = 393.700787402
    h.attrib["style"] = preset["style"]
    h.attrib["x"] = str(-preset["padding"])
    h.attrib["y"] = str(-preset["padding"])
    h.attrib["width"] = str(width + 2 * preset["padding"])
    h.attrib["height"] = str(height + 2 * preset["padding"])
    h.attrib["transform"] = "translate({} {}) scale(393.700787402) rotate({}) translate({}, {})".format(
        ki2dmil(pos[0]), ki2dmil(pos[1]),
        -math.degrees(pos[2]), -origin[0], -origin[1])
    h.attrib["id"] = "h_" + ref

def load_style(style_file):
    try:
        with open(style_file, "r") as f:
            style = json.load(f)
    except IOError:
        raise RuntimeError("Cannot open style " + style_file)
    required = set(["copper", "board", "silk", "pads", "outline",
        "highlight-style", "highlight-offset", "highlight-on-top"])
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--style", help="JSON file with board style")
    parser.add_argument("libraries", help="directories containing SVG footprints")
    parser.add_argument("board", help=".kicad_pcb file to draw")
    parser.add_argument("output", help="destination for final SVG")
    parser.add_argument("-p", "--placeholder", action="store_true",
                        help="show placeholder for missing components")
    parser.add_argument("-m", "--remap",
                        help="JSON file with map part reference to <lib>:<model> to remap packages")
    parser.add_argument("-l", "--list-components", action="store_true",
                        help="Dry run, just list the components")
    parser.add_argument("--no-drillholes", action="store_true", help="Do not make holes transparent")
    parser.add_argument("-b","--back", action="store_true", help="render the backside of the board")
    parser.add_argument("--mirror", action="store_true", help="mirror the board")
    parser.add_argument("-a", "--highlight", help="comma separated list of components to highlight")
    parser.add_argument("-f", "--filter", help="comma separated list of components to show")

    args = parser.parse_args()
    args.libraries = args.libraries.split(',')
    args.highlight = args.highlight.split(',') if args.highlight is not None else []
    args.filter = args.filter.split(',') if args.filter is not None else None

    try:
        if args.style:
            style = load_style(args.style)
        else:
            style = default_style
        remapping = load_remapping(args.remap)
    except RuntimeError as e:
        print(e.message)
        sys.exit(1)
    try:
        print("Please ignore following debug output of KiCAD Python API")
        board = pcbnew.LoadBoard(args.board)
        print("End of KiCAD debug output")
    except IOError:
        print("Cannot open board " + args.board)
        sys.exit(1)

    if args.list_components:
        walk_components(board, args.back,lambda lib, name, val, ref, pos:
                        print_component(args.libraries, lib, name, val, ref, pos,
                                        remapping=remapping))
        sys.exit(0)

    bb = board.ComputeBoundingBox()
    transform_string = ""
    if(args.back ^ args.mirror):
        transform_string = "translate({}, {}) scale(-1,1)".format(ki2dmil(bb.GetX()+bb.GetWidth()), ki2dmil(-bb.GetY()))
    else:
        transform_string = "translate({}, {})".format(ki2dmil(-bb.GetX()), ki2dmil(-bb.GetY()))
    document = empty_svg(
        width="{}cm".format(bb.GetWidth()/10000000.0),
        height="{}cm".format(bb.GetHeight()/10000000.0),
        viewBox="0 0 {} {}".format(ki2dmil(bb.GetWidth()), ki2dmil(bb.GetHeight())))

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
        "libraries": args.libraries,
        "filter": args.filter
    }

    highlight = {
        "container": high_cont,
        "items": args.highlight,
        "style": style["highlight-style"],
        "padding": style["highlight-padding"]
    }

    board_cont.append(get_board_substrate(board, style, not args.no_drillholes, args.back))

    walk_components(board, args.back, lambda lib, name, val, ref, pos:
        component_from_library(lib, name, val, ref, pos, components, highlight))

    #make another pass for search, and if found, render the back side of the component
    #the function will search for file with extension ".back.svg"
    walk_components(board, not args.back, lambda lib, name, val, ref, pos:
        component_from_library(lib, name+".back", val, ref, pos, components, highlight))

    document.write(args.output)
