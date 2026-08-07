"""Stable, subprocess-based access to KiCad's command-line interface."""

from __future__ import annotations

from collections import OrderedDict
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .kicad_formats import (
    BoardData, DrillHole, parse_excellon, parse_gencad,
)
from .kicad_sexpr import component_footprint_ids, prepare_footprint_for_export
from .kicad_sexpr import component_properties
from .annotations import BoardScene


SUPPORTED_KICAD_MAJORS = (9, 10)

# Legacy pcbnew numeric layer identifiers accepted by PcbDraw's public CLI.
LAYER_NAMES: Dict[int, str] = {
    0: "F.Cu", 31: "B.Cu", 32: "B.Adhesive", 33: "F.Adhesive",
    34: "B.Paste", 35: "F.Paste", 36: "B.Silkscreen", 37: "F.Silkscreen",
    38: "B.Mask", 39: "F.Mask", 40: "User.Drawings", 41: "User.Comments",
    42: "User.Eco1", 43: "User.Eco2", 44: "Edge.Cuts", 45: "Margin",
    46: "B.Courtyard", 47: "F.Courtyard", 48: "B.Fab", 49: "F.Fab",
}

LAYER_ALIASES = {
    "B.Adhes": "B.Adhesive",
    "F.Adhes": "F.Adhesive",
    "B.SilkS": "B.Silkscreen",
    "F.SilkS": "F.Silkscreen",
    "Dwgs.User": "User.Drawings",
    "Cmts.User": "User.Comments",
    "Eco1.User": "User.Eco1",
    "Eco2.User": "User.Eco2",
    "B.CrtYd": "B.Courtyard",
    "F.CrtYd": "F.Courtyard",
}


def canonical_layer(layer: Any) -> str:
    if isinstance(layer, str):
        return LAYER_ALIASES.get(layer, layer)
    try:
        numeric = int(layer)
    except (TypeError, ValueError) as exc:
        raise KiCadCliError(f"Unsupported KiCad layer: {layer!r}") from exc
    try:
        return LAYER_NAMES[numeric]
    except KeyError as exc:
        raise KiCadCliError(f"Unsupported KiCad layer number: {numeric}") from exc


def is_canonical_layer(layer: str) -> bool:
    """Return whether a name follows KiCad's untranslated layer naming."""
    if layer in LAYER_NAMES.values():
        return True
    if re.fullmatch(r"In(?:[1-9]|[12]\d|30)\.Cu", layer):
        return True
    return re.fullmatch(r"User\.[1-9]", layer) is not None


class KiCadCliError(RuntimeError):
    """Raised when kicad-cli cannot be found or an export fails."""


@dataclass(frozen=True)
class FootprintSvgExport:
    layers: Dict[str, bytes]
    origin: Tuple[float, float]
    canvas: bytes


def find_kicad_cli() -> str:
    override = os.environ.get("KICAD_CLI")
    if override:
        if os.path.isfile(override) and os.access(override, os.X_OK):
            return override
        raise KiCadCliError(f"KICAD_CLI does not point to an executable: {override}")

    path = shutil.which("kicad-cli")
    if path is not None:
        return path

    candidates = [
        "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
        "/usr/bin/kicad-cli",
        "/usr/local/bin/kicad-cli",
    ]
    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    raise KiCadCliError(
        "kicad-cli not found. Install KiCad 9 or 10, or set KICAD_CLI "
        "to the executable path."
    )


def run_kicad_cli(
    arguments: Sequence[str], *, timeout: int = 120,
    executable: Optional[str] = None,
) -> bytes:
    command = [executable or find_kicad_cli(), *arguments]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise KiCadCliError(
            f"kicad-cli timed out after {timeout} seconds: {shlex.join(arguments)}"
        ) from exc
    except OSError as exc:
        raise KiCadCliError(f"Cannot run kicad-cli: {exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        stdout = result.stdout.decode("utf-8", errors="replace").strip()
        detail = stderr or stdout or "no diagnostic output"
        raise KiCadCliError(
            f"kicad-cli {shlex.join(arguments[:3])} failed "
            f"(exit code {result.returncode}):\n{detail}"
        )
    return result.stdout


@lru_cache(maxsize=4)
def _kicad_version(executable: str) -> Tuple[int, ...]:
    output = run_kicad_cli(
        ["version"], executable=executable
    ).decode("utf-8", errors="replace")
    match = re.search(r"\d+(?:\.\d+)+", output)
    if match is None:
        raise KiCadCliError(f"Cannot parse KiCad version from: {output.strip()!r}")
    version = tuple(int(part) for part in match.group(0).split("."))
    if version[0] not in SUPPORTED_KICAD_MAJORS:
        supported = " and ".join(str(major) for major in SUPPORTED_KICAD_MAJORS)
        raise KiCadCliError(
            f"PcbDraw supports KiCad {supported}; found {match.group(0)}"
        )
    return version


def kicad_version() -> Tuple[int, ...]:
    return _kicad_version(find_kicad_cli())


def _board_cache_key(board: str) -> Tuple[str, str, int, int]:
    path = os.path.realpath(board)
    stat = os.stat(path)
    return find_kicad_cli(), path, stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=16)
def _load_board_data_cached(
    executable: str, path: str, mtime_ns: int, size: int
) -> BoardData:
    del mtime_ns, size
    _kicad_version(executable)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        gencad = tmp_path / "board.cad"
        run_kicad_cli(
            ["pcb", "export", "gencad", "-o", str(gencad), path],
            executable=executable,
        )
        components, bounds = parse_gencad(gencad.read_text(encoding="utf-8"))
        board_text = Path(path).read_text(encoding="utf-8")
        footprint_ids = component_footprint_ids(board_text)
        properties = component_properties(board_text)
        components = tuple(
            replace(
                component,
                library=footprint_ids.get(
                    component.reference,
                    (component.library, component.footprint),
                )[0],
                footprint=footprint_ids.get(
                    component.reference,
                    (component.library, component.footprint),
                )[1],
                properties=properties.get(component.reference, {}),
            )
            for component in components
        )

        drill_dir = tmp_path / "drill"
        drill_dir.mkdir()
        run_kicad_cli([
            "pcb", "export", "drill",
            "--format", "excellon",
            "--excellon-units", "mm",
            "--excellon-zeros-format", "decimal",
            "--excellon-oval-format", "alternate",
            "--excellon-separate-th",
            "-o", str(drill_dir), path,
        ], executable=executable)
        holes: List[DrillHole] = []
        for drill_file in sorted(drill_dir.glob("*.drl")):
            holes.extend(parse_excellon(drill_file.read_text(encoding="utf-8")))
    return BoardData(components, tuple(holes), bounds)


def load_board_data(board: str) -> BoardData:
    return _load_board_data_cached(*_board_cache_key(board))


@lru_cache(maxsize=16)
def _load_board_scene_cached(
    executable: str, path: str, mtime_ns: int, size: int
) -> BoardScene:
    """Load reusable board annotations using only stable KiCad CLI exports."""
    del mtime_ns, size
    from .ipc2581 import parse_ipc2581

    _kicad_version(executable)
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "board.xml"
        run_kicad_cli([
            "pcb", "export", "ipc2581", "--units", "mm",
            "--output", str(output), path,
        ], executable=executable)
        if not output.is_file():
            raise KiCadCliError("kicad-cli did not produce an IPC-2581 export")
        return parse_ipc2581(output.read_bytes(), load_board_data(path))


def load_board_scene(board: str) -> BoardScene:
    """Return components, pads, nets, tracks, zones and vias for ``board``.

    The returned coordinates are millimetres in KiCad board space.  This API
    intentionally does not require or import KiCad's ``pcbnew`` bindings.
    """
    return _load_board_scene_cached(*_board_cache_key(board))


def _export_svg_layers(
    executable: str, path: str, mtime_ns: int, size: int,
    layers: Tuple[str, ...]
) -> Tuple[Tuple[str, bytes], ...]:
    del mtime_ns, size
    if not layers:
        return ()
    _kicad_version(executable)
    with tempfile.TemporaryDirectory() as tmp:
        run_kicad_cli([
            "pcb", "export", "svg",
            "--mode-multi",
            "--layers", ",".join(layers),
            "--page-size-mode", "1",
            "--exclude-drawing-sheet",
            "--black-and-white",
            "--subtract-soldermask",
            "--drill-shape-opt", "0",
            "-o", tmp,
            path,
        ], executable=executable)
        result: List[Tuple[str, bytes]] = []
        files = list(Path(tmp).glob("*.svg"))
        for layer in layers:
            suffix = "-" + layer.replace(".", "_") + ".svg"
            matches = [file for file in files if file.name.endswith(suffix)]
            if len(matches) != 1:
                raise KiCadCliError(
                    f"kicad-cli did not produce an unambiguous SVG for layer {layer}"
                )
            result.append((layer, matches[0].read_bytes()))
        return tuple(result)


_SVG_LAYER_CACHE: OrderedDict[Tuple[str, str, int, int, str], bytes] = OrderedDict()
_SVG_CACHE_LOCK = RLock()


def export_pcb_svg_layers(board: str, layers: Iterable[str]) -> Dict[str, bytes]:
    unique_layers = tuple(dict.fromkeys(layers))
    board_key = _board_cache_key(board)
    with _SVG_CACHE_LOCK:
        missing = tuple(
            layer for layer in unique_layers
            if (*board_key, layer) not in _SVG_LAYER_CACHE
        )
        if missing:
            for layer, content in _export_svg_layers(*board_key, missing):
                _SVG_LAYER_CACHE[(*board_key, layer)] = content
            while len(_SVG_LAYER_CACHE) > 128:
                _SVG_LAYER_CACHE.popitem(last=False)
        result = {}
        for layer in unique_layers:
            key = (*board_key, layer)
            result[layer] = _SVG_LAYER_CACHE[key]
            _SVG_LAYER_CACHE.move_to_end(key)
        return result


_ORIGIN_RADII = (0.123456, 0.234567)
_SVG_ROUNDING_TOLERANCE = 0.0001


def _marker_origin(content: bytes) -> Tuple[float, float]:
    circles = []
    for element in ET.fromstring(content).iter():
        if not element.tag.endswith("circle"):
            continue
        circles.append((
            float(element.get("r", "0")),
            float(element.get("cx", "0")),
            float(element.get("cy", "0")),
        ))
    for radius, x, y in circles:
        if abs(radius - _ORIGIN_RADII[0]) > _SVG_ROUNDING_TOLERANCE:
            continue
        if any(abs(other_radius - _ORIGIN_RADII[1]) <= _SVG_ROUNDING_TOLERANCE
               and abs(other_x - x) <= _SVG_ROUNDING_TOLERANCE
               and abs(other_y - y) <= _SVG_ROUNDING_TOLERANCE
               for other_radius, other_x, other_y in circles):
            return x, y
    raise KiCadCliError("Cannot locate the footprint origin in kicad-cli output")


def export_footprints_svg(
    footprints: Dict[str, str], layers: Iterable[str]
) -> Dict[str, FootprintSvgExport]:
    """Export multiple footprints with one KiCad process per requested layer."""
    if not footprints:
        return {}
    kicad_version()
    requested = tuple(dict.fromkeys(layers))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        library = root / "PcbDraw.pretty"
        library.mkdir()
        prepared: Dict[str, Tuple[str, str]] = {}
        used_user_layers = set()
        for index, (key, footprint) in enumerate(footprints.items()):
            text = prepare_footprint_for_export(
                Path(footprint).read_text(encoding="utf-8")
            )
            if text.rfind(")") < 0:
                raise KiCadCliError(f"Invalid footprint file: {footprint}")
            used_user_layers.update(re.findall(r'"(User\.[1-9])"', text))
            prepared[key] = (f"footprint_{index}", text)

        marker_layer = next(
            (f"User.{number}" for number in range(9, 0, -1)
             if f"User.{number}" not in used_user_layers
             and f"User.{number}" not in requested),
            None,
        )
        if marker_layer is None:
            raise KiCadCliError(
                "Cannot reserve a user layer for the temporary footprint origin marker"
            )
        origin_marker = "".join(
            '  (fp_circle (center 0 0) '
            f'(end {radius} 0) '
            '(stroke (width 0.017) (type default)) (fill none) '
            f'(layer "{marker_layer}"))\n'
            for radius in _ORIGIN_RADII
        )
        for stem, text in prepared.values():
            closing = text.rfind(")")
            (library / f"{stem}.kicad_mod").write_text(
                text[:closing] + origin_marker + text[closing:],
                encoding="utf-8",
            )

        def export_layer(layer: str) -> Tuple[str, Dict[str, bytes]]:
            output = root / layer.replace(".", "_")
            output.mkdir()
            run_kicad_cli([
                "fp", "export", "svg",
                "--layers", layer,
                "--black-and-white",
                "-o", str(output),
                str(library),
            ])
            result = {}
            for key, (stem, _) in prepared.items():
                svg = output / f"{stem}.svg"
                if not svg.is_file():
                    raise KiCadCliError(
                        f"kicad-cli did not produce an SVG for {key} on layer {layer}"
                    )
                result[key] = svg.read_bytes()
            return layer, result

        export_layers = (*requested, marker_layer)
        with ThreadPoolExecutor(max_workers=min(4, len(export_layers))) as executor:
            exported_by_layer = dict(executor.map(export_layer, export_layers))

        result = {}
        for key in footprints:
            canvas = exported_by_layer[marker_layer][key]
            result[key] = FootprintSvgExport(
                layers={layer: exported_by_layer[layer][key]
                        for layer in requested},
                origin=_marker_origin(canvas),
                canvas=canvas,
            )
        return result


def export_footprint_svg(
    footprint: str, layers: Iterable[str]
) -> FootprintSvgExport:
    """Export one standalone footprint."""
    return export_footprints_svg({"footprint": footprint}, layers)["footprint"]
