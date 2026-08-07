"""Read the annotation subset of KiCad's IPC-2581 board export.

IPC-2581 is produced by ``kicad-cli pcb export ipc2581``.  Keeping this
parser here makes PcbDraw's public annotation API independent of KiCad's
unstable Python bindings.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

from .annotations import (
    BoardScene, Bounds, ComponentAnnotation, PadAnnotation, Point,
    TrackAnnotation, ViaAnnotation, ZoneAnnotation,
)
from .kicad_formats import BoardData, BoardSide


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> Iterable[ET.Element]:
    return (child for child in element if _tag(child) == name)


def _first(element: ET.Element, name: str) -> Optional[ET.Element]:
    return next(_children(element, name), None)


def _float(element: ET.Element, name: str, default: float = 0) -> float:
    return float(element.get(name, str(default)))


def _point(element: ET.Element, x: str = "x", y: str = "y") -> Point:
    # IPC-2581 uses an upwards-positive Y axis; PcbDraw uses KiCad board Y.
    return (_float(element, x), -_float(element, y))


def _bounds(points: Iterable[Point]) -> Bounds:
    values = tuple(points)
    if not values:
        return Bounds(0, 0, 0, 0)
    xs, ys = zip(*values)
    return Bounds(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _rotate(point: Point, degrees: float) -> Point:
    radians = math.radians(degrees)
    x, y = point
    return (x * math.cos(radians) - y * math.sin(radians),
            x * math.sin(radians) + y * math.cos(radians))


def _circle(diameter: float, steps: int = 24) -> Tuple[Point, ...]:
    radius = diameter / 2
    return tuple((radius * math.cos(2 * math.pi * i / steps),
                  radius * math.sin(2 * math.pi * i / steps))
                 for i in range(steps))


def _rect(width: float, height: float) -> Tuple[Point, ...]:
    return ((-width / 2, -height / 2), (width / 2, -height / 2),
            (width / 2, height / 2), (-width / 2, height / 2))


def _oval(width: float, height: float) -> Tuple[Point, ...]:
    if abs(width - height) < 1e-9:
        return _circle(width)
    major, minor = (width, height) if width >= height else (height, width)
    radius = minor / 2
    straight = (major - minor) / 2
    points: List[Point] = []
    for index in range(12):
        angle = math.pi / 2 + math.pi * index / 11
        points.append((straight + radius * math.cos(angle), radius * math.sin(angle)))
    for index in range(12):
        angle = -math.pi / 2 + math.pi * index / 11
        points.append((-straight + radius * math.cos(angle), radius * math.sin(angle)))
    if height > width:
        return tuple((y, x) for x, y in points)
    return tuple(points)


def _primitive_shapes(root: ET.Element) -> Dict[str, Tuple[Point, ...]]:
    result: Dict[str, Tuple[Point, ...]] = {}
    for entry in root.iter():
        if _tag(entry) not in {"EntryStandard", "EntryUser"}:
            continue
        identifier = entry.get("id")
        if not identifier:
            continue
        primitive = next((item for item in entry.iter()
                          if _tag(item) in {"Circle", "RectCenter", "Oval"}), None)
        if primitive is None:
            continue
        if _tag(primitive) == "Circle":
            result[identifier] = _circle(_float(primitive, "diameter"))
        elif _tag(primitive) == "RectCenter":
            result[identifier] = _rect(_float(primitive, "width"), _float(primitive, "height"))
        else:
            result[identifier] = _oval(_float(primitive, "width"), _float(primitive, "height"))
    return result


def _padstack_layers(step: ET.Element) -> Dict[str, Tuple[Tuple[str, str], ...]]:
    result = {}
    for definition in _children(step, "PadStackDef"):
        values = []
        for pad in _children(definition, "PadstackPadDef"):
            ref = _first(pad, "StandardPrimitiveRef") or _first(pad, "UserPrimitiveRef")
            if ref is not None and ref.get("id"):
                values.append((pad.get("layerRef", ""), ref.get("id", "")))
        result[definition.get("name", "")] = tuple(values)
    return result


def _line_widths(root: ET.Element) -> Dict[str, float]:
    result = {}
    for entry in root.iter():
        if _tag(entry) != "EntryLineDesc":
            continue
        descriptor = _first(entry, "LineDesc")
        if descriptor is not None:
            result[entry.get("id", "")] = _float(descriptor, "lineWidth")
    return result


def _polyline(element: ET.Element) -> Tuple[Point, ...]:
    begin = _first(element, "PolyBegin")
    if begin is None:
        return ()
    points = [_point(begin)]
    points.extend(_point(item) for item in _children(element, "PolyStepSegment"))
    return tuple(points)


def _transform(outline: Tuple[Point, ...], location: Point, rotation: float) -> Tuple[Point, ...]:
    # The outline was converted into board Y coordinates.  IPC rotation is in
    # its original coordinate system, so invert its sign before applying it.
    return tuple((location[0] + x, location[1] + y)
                 for x, y in (_rotate(point, -rotation) for point in outline))


def _component_boxes(step: ET.Element) -> Dict[str, Bounds]:
    packages = {}
    for package in _children(step, "Package"):
        outline = _first(package, "Outline")
        polygon = _first(outline, "Polygon") if outline is not None else None
        if polygon is not None:
            packages[package.get("name", "")] = _polyline(polygon)
    result = {}
    for component in _children(step, "Component"):
        location = _first(component, "Location")
        if location is None:
            continue
        transform = _first(component, "Xform")
        outline = packages.get(component.get("packageRef", ""), ())
        result[component.get("refDes", "")] = _bounds(_transform(
            outline, _point(location), _float(transform, "rotation") if transform is not None else 0))
    return result


def parse_ipc2581(content: bytes, board: BoardData) -> BoardScene:
    """Parse annotations from an IPC-2581 document produced by KiCad CLI."""
    root = ET.fromstring(content)
    step = next((item for item in root.iter() if _tag(item) == "Step" and item.get("type") == "BOARD"), None)
    if step is None:
        raise ValueError("IPC-2581 document does not contain a board step")
    primitives = _primitive_shapes(root)
    padstacks = _padstack_layers(step)
    line_widths = _line_widths(root)
    package_boxes = _component_boxes(step)
    component_data = {component.reference: component for component in board.components}
    pads: Dict[Tuple[str, str], PadAnnotation] = {}
    tracks: List[TrackAnnotation] = []
    zones: List[ZoneAnnotation] = []
    vias: List[ViaAnnotation] = []

    for layer_feature in _children(step, "LayerFeature"):
        layer = layer_feature.get("layerRef", "")
        copper = layer.endswith(".Cu")
        for feature_set in _children(layer_feature, "Set"):
            net = feature_set.get("net") or None
            for pad in _children(feature_set, "Pad"):
                pin = _first(pad, "PinRef")
                location = _first(pad, "Location")
                if pin is None or location is None:
                    continue
                reference, name = pin.get("componentRef", ""), pin.get("pin", "")
                if not reference or not name:
                    continue
                transform = _first(pad, "Xform")
                rotation = _float(transform, "rotation") if transform is not None else 0
                primitive_ref = _first(pad, "StandardPrimitiveRef") or _first(pad, "UserPrimitiveRef")
                stack = padstacks.get(pad.get("padstackDefRef", ""), ())
                layers = tuple(sorted({item[0] for item in stack if item[0].endswith(".Cu")}))
                shape_id = primitive_ref.get("id") if primitive_ref is not None else None
                if shape_id is None and stack:
                    shape_id = stack[0][1]
                outline = _transform(primitives.get(shape_id or "", ()), _point(location), rotation)
                if not outline:
                    continue
                key = (reference, name)
                existing = pads.get(key)
                merged_layers = tuple(sorted(set((existing.layers if existing else ()) + layers)))
                pads[key] = PadAnnotation(reference, name, net or (existing.net if existing else None),
                    merged_layers, _point(location), outline, _bounds(outline),
                    bool(any(item[0] == "F.Cu" for item in stack) and any(item[0] == "B.Cu" for item in stack)))
            if not copper:
                continue
            features = _first(feature_set, "Features")
            if features is not None:
                # KiCad wraps routed copper in UserSpecial.  Iterating below
                # Features also handles future IPC exporters that omit it.
                for line in (item for item in features.iter() if _tag(item) == "Line"):
                    tracks.append(TrackAnnotation(net, layer, _float(line, "lineWidth"),
                        (_point(line, "startX", "startY"), _point(line, "endX", "endY"))))
                for line in (item for item in features.iter() if _tag(item) == "Polyline"):
                    width_ref = _first(line, "LineDescRef")
                    width = line_widths.get(width_ref.get("id", "") if width_ref is not None else "", 0)
                    tracks.append(TrackAnnotation(net, layer, width, _polyline(line)))
                for polygon in (item for item in features.iter() if _tag(item) == "Polygon"):
                    zones.append(ZoneAnnotation(net, layer, _polyline(polygon)))
            for hole in _children(feature_set, "Hole"):
                location = _point(hole)
                stack = padstacks.get(feature_set.get("geometry", ""), ())
                layers = tuple(sorted({item[0] for item in stack if item[0].endswith(".Cu")}))
                diameter = max((_bounds(primitives.get(shape, ())).width for _, shape in stack), default=_float(hole, "diameter"))
                vias.append(ViaAnnotation(net, layers, location, diameter, _float(hole, "diameter")))

    component_pads: Dict[str, List[str]] = defaultdict(list)
    net_index: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for key, pad in pads.items():
        component_pads[pad.component].append(pad.name)
        if pad.net:
            net_index[pad.net].append(key)
    components = {}
    for reference, component in component_data.items():
        side = "back" if component.side == BoardSide.BACK else "front"
        bbox = package_boxes.get(reference)
        if bbox is None or (bbox.width == 0 and bbox.height == 0):
            bbox = Bounds(0, 0, 0, 0)
        # Components with no package outline use their pad extents.
        if bbox.width == 0 and bbox.height == 0:
            bbox = _bounds(point for pad in pads.values() if pad.component == reference for point in pad.outline)
        components[reference] = ComponentAnnotation(reference, component.value, component.footprint,
            side, (component.position.x, component.position.y), component.rotation_degrees, bbox,
            tuple(sorted(component_pads[reference])))
    return BoardScene(Bounds(board.bounds.x, board.bounds.y, board.bounds.width, board.bounds.height),
        components, pads, tuple(tracks), tuple(zones), tuple(vias),
        {name: tuple(values) for name, values in net_index.items()})
