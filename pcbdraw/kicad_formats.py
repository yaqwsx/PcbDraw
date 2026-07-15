"""Parsers and Python domain records for stable KiCad export formats."""

from __future__ import annotations

import math
import re
import shlex
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple


MM_PER_INCH = 25.4


def _mm(value: float) -> float:
    """Round to KiCad's nanometre coordinate resolution, expressed in mm."""
    return round(value, 6)


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Size:
    width: float
    height: float


@dataclass(frozen=True)
class Bounds:
    x: float
    y: float
    width: float
    height: float


class BoardSide(Enum):
    FRONT = "front"
    BACK = "back"


@dataclass(frozen=True)
class Component:
    library: str
    footprint: str
    reference: str
    value: str
    position: Point
    rotation_degrees: float
    side: BoardSide


@dataclass(frozen=True)
class DrillHole:
    position: Point
    orientation_degrees: float
    size: Size


@dataclass(frozen=True)
class BoardData:
    components: Tuple[Component, ...]
    holes: Tuple[DrillHole, ...]
    bounds: Bounds


@dataclass
class _GenCadComponentState:
    reference: str
    device: str = ""
    shape: str = ""
    value: str = ""
    place: Tuple[float, float] = (0.0, 0.0)
    rotation_degrees: float = 0.0
    layer: str = "TOP"
    text_count: int = 0


def _quoted_fields(line: str) -> List[str]:
    try:
        return shlex.split(line, posix=True)
    except ValueError as exc:
        raise ValueError(f"Cannot parse KiCad export line: {line!r}") from exc


def _split_footprint_id(identifier: str) -> Tuple[str, str]:
    library, separator, footprint = identifier.partition(":")
    return (library, footprint) if separator else ("", library)


def parse_gencad(content: str) -> Tuple[Tuple[Component, ...], Bounds]:
    """Parse the component and board records emitted by KiCad's GenCAD export."""
    device_packages: Dict[str, str] = {}
    device_section = ""
    current_device: Optional[str] = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("$"):
            device_section = line
            continue
        if device_section != "$DEVICES":
            continue
        fields = _quoted_fields(line)
        if fields and fields[0].upper() == "DEVICE" and len(fields) >= 2:
            current_device = fields[1]
        elif (fields and fields[0].upper() == "PACKAGE" and len(fields) >= 2
              and current_device is not None):
            device_packages[current_device] = fields[1]

    units = MM_PER_INCH
    section = ""
    board_points: List[Tuple[float, float]] = []
    components: List[Component] = []
    current: Optional[_GenCadComponentState] = None

    def finish_component() -> None:
        nonlocal current
        if current is None:
            return
        identifier = device_packages.get(current.device, current.shape)
        library, footprint = _split_footprint_id(identifier)
        x, y = current.place
        components.append(Component(
            library=library.strip(),
            footprint=footprint.strip(),
            reference=current.reference.strip(),
            value=current.value.strip(),
            position=Point(_mm(x * units), _mm(-y * units)),
            rotation_degrees=current.rotation_degrees,
            side=(BoardSide.BACK if current.layer.upper() == "BOTTOM"
                  else BoardSide.FRONT),
        ))
        current = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("$"):
            if line == "$ENDCOMPONENTS":
                finish_component()
            section = line
            continue
        # KiCad does not escape quotes in the descriptive SHEET line. The
        # value is available in the second escaped TEXT record.
        if section == "$COMPONENTS" and line.startswith("SHEET "):
            continue
        fields = _quoted_fields(line)
        if not fields:
            continue
        command = fields[0].upper()
        if section == "$HEADER" and command == "UNITS" and len(fields) >= 2:
            units = 1.0 if fields[1].upper() in {"MM", "MILLIMETER"} else MM_PER_INCH
        elif section == "$BOARD":
            numbers: List[float] = []
            for field in fields[1:]:
                try:
                    numbers.append(float(field))
                except ValueError:
                    pass
            for index in range(0, len(numbers) - 1, 2):
                board_points.append((numbers[index] * units, -numbers[index + 1] * units))
        elif section == "$COMPONENTS":
            if command == "COMPONENT":
                finish_component()
                current = _GenCadComponentState(
                    reference=fields[1] if len(fields) > 1 else ""
                )
            elif current is not None and command == "PLACE" and len(fields) >= 3:
                current.place = (float(fields[1]), float(fields[2]))
            elif current is not None and command == "LAYER" and len(fields) >= 2:
                current.layer = fields[1]
            elif current is not None and command == "ROTATION" and len(fields) >= 2:
                current.rotation_degrees = float(fields[1])
            elif current is not None and command == "DEVICE" and len(fields) >= 2:
                current.device = fields[1]
            elif current is not None and command == "SHAPE" and len(fields) >= 2:
                current.shape = fields[1]
            elif current is not None and command == "TEXT" and len(fields) >= 8:
                current.text_count += 1
                if current.text_count == 2:
                    current.value = fields[7]
    finish_component()

    if board_points:
        xs = [point[0] for point in board_points]
        ys = [point[1] for point in board_points]
        x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
    elif components:
        xs = [component.position.x for component in components]
        ys = [component.position.y for component in components]
        x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
    else:
        x1 = x2 = y1 = y2 = 0.0
    return tuple(components), Bounds(
        _mm(x1), _mm(y1), _mm(x2 - x1), _mm(y2 - y1)
    )


_XY_RE = re.compile(r"X([+-]?\d+(?:\.\d+)?)Y([+-]?\d+(?:\.\d+)?)")


def parse_excellon(content: str) -> Tuple[DrillHole, ...]:
    """Parse decimal Excellon generated by PcbDraw's KiCad command."""
    tools: Dict[str, float] = {}
    current_tool: Optional[str] = None
    holes: List[DrillHole] = []
    unit_scale = 1.0

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line == "INCH":
            unit_scale = MM_PER_INCH
            continue
        if line == "METRIC":
            unit_scale = 1.0
            continue
        tool_definition = re.fullmatch(r"T(\d+)C([0-9.]+)", line)
        if tool_definition:
            tools[tool_definition.group(1)] = float(tool_definition.group(2)) * unit_scale
            continue
        tool_selection = re.fullmatch(r"T(\d+)", line)
        if tool_selection:
            current_tool = tool_selection.group(1)
            continue
        if current_tool is None or current_tool not in tools:
            continue
        points = [(float(x) * unit_scale, -float(y) * unit_scale)
                  for x, y in _XY_RE.findall(line)]
        if not points:
            continue
        diameter = tools[current_tool]
        if "G85" in line and len(points) >= 2:
            start, end = points[0], points[1]
            dx, dy = end[0] - start[0], end[1] - start[1]
            position = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
            orientation = -math.degrees(math.atan2(dy, dx))
            size = (math.hypot(dx, dy) + diameter, diameter)
        else:
            position = points[-1]
            orientation = 0.0
            size = (diameter, diameter)
        holes.append(DrillHole(
            position=Point(_mm(position[0]), _mm(position[1])),
            orientation_degrees=orientation,
            size=Size(_mm(size[0]), _mm(size[1])),
        ))
    return tuple(holes)
