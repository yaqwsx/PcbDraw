"""Board annotations exported through :program:`kicad-cli`.

This module is deliberately independent of PcbDraw's SVG implementation.
Coordinates are millimetres in KiCad board coordinates (X increases right,
Y increases down).  Consumers can therefore use the scene with either an SVG
plot, a bitmap, or their own renderer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Optional, Tuple


Point = Tuple[float, float]
Polygon = Tuple[Point, ...]


@dataclass(frozen=True)
class Bounds:
    """An axis-aligned rectangle in board millimetres."""
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class ComponentAnnotation:
    reference: str
    value: str
    footprint: str
    side: str
    position: Point
    rotation_degrees: float
    bbox: Bounds
    pads: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PadAnnotation:
    component: str
    name: str
    net: Optional[str]
    layers: Tuple[str, ...]
    position: Point
    outline: Polygon
    bbox: Bounds
    through_hole: bool = False


@dataclass(frozen=True)
class TrackAnnotation:
    net: Optional[str]
    layer: str
    width: float
    path: Tuple[Point, ...]


@dataclass(frozen=True)
class ZoneAnnotation:
    net: Optional[str]
    layer: str
    outline: Polygon
    holes: Tuple[Polygon, ...] = ()


@dataclass(frozen=True)
class ViaAnnotation:
    net: Optional[str]
    layers: Tuple[str, ...]
    position: Point
    diameter: float
    drill: float


@dataclass(frozen=True)
class BoardScene:
    """Electrical and placement annotations for a board.

    ``components`` is keyed by reference and ``pads`` by ``(reference, name)``.
    Tracks and zones are intentionally represented separately: a track is a
    stroked centreline, while a zone is a filled region.
    """
    bounds: Bounds
    components: Mapping[str, ComponentAnnotation]
    pads: Mapping[Tuple[str, str], PadAnnotation]
    source_path: str = ""
    tracks: Tuple[TrackAnnotation, ...] = ()
    zones: Tuple[ZoneAnnotation, ...] = ()
    vias: Tuple[ViaAnnotation, ...] = ()
    nets: Mapping[str, Tuple[Tuple[str, str], ...]] = field(default_factory=dict)

    def features_for_net(self, name: str) -> Iterable[object]:
        """Yield pads, tracks, zones and vias belonging to ``name``."""
        yield from (pad for pad in self.pads.values() if pad.net == name)
        yield from (track for track in self.tracks if track.net == name)
        yield from (zone for zone in self.zones if zone.net == name)
        yield from (via for via in self.vias if via.net == name)
