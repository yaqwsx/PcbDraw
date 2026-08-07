# Board annotations API

PcbDraw can expose electrical and placement data from a KiCad board without
importing KiCad's Python bindings. It invokes `kicad-cli pcb export ipc2581`
and returns a stable, Python-native scene in board millimetres.

```python
from pcbdraw import load_board_scene

scene = load_board_scene("controller.kicad_pcb")
connector = scene.components["J1"]
pin_one = scene.pads[("J1", "1")]
ground = list(scene.features_for_net("GND"))
```

`BoardScene` contains components, pads, tracks, zones, vias, and an index of
pads by net. Components are keyed by reference and pads by `(reference, name)`.
Tracks are centre lines with widths; zones and pads are filled outlines. This
distinction keeps the data useful to both vector renderers and interactive
tools.

All coordinates use millimetres in KiCad board space: X increases to the
right and Y increases down. These coordinates are independent of the output
image. A caller that overlays data on a 2D PcbDraw plot must use the plot's
board-to-image transform; a perspective 3D render has no exact planar overlay
transform.

The API requires KiCad 9 or 10's `kicad-cli`, found on `PATH` or selected with
the `KICAD_CLI` environment variable. It does not require `pcbnew`.

## Geometry fidelity

Standard circular, rectangular, and oval pad primitives are tessellated into
outlines. The scene preserves track centre lines and zone contours, including
their net and copper-layer association. Unsupported IPC primitives are omitted
rather than guessed; consumers should treat a missing outline as an unsupported
source feature and report it to users when selection is required.
