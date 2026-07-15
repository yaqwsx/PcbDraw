import pytest

from pcbdraw.kicad_cli import canonical_layer
from pcbdraw.kicad_formats import (
    BoardSide, Bounds, Point, Size, parse_excellon, parse_gencad,
)
from pcbdraw.ui import KiCadLayerParam


GENCAD = '''
$HEADER
GENCAD 1.4
UNITS INCH
$ENDHEADER
$BOARD
LINE 1 -2 3 -2
LINE 3 -2 3 -4
$ENDBOARD
$COMPONENTS
COMPONENT "R1"
DEVICE "DEV_Resistor_SMD:R_0603"
PLACE 1.5 -2.5
LAYER BOTTOM
ROTATION 90
SHAPE "Resistor_SMD:R_0603" MIRRORX FLIP
TEXT 0 0 1 0 MIRRORX SILKSCREEN_BOTTOM "R1" 0 0 1 1
TEXT 0 0 1 0 MIRRORX SILKSCREEN_BOTTOM "4.7 kΩ, 1%" 0 0 1 1
SHEET "RefDes: R1, Value: 4.7 kΩ, 1%"
$ENDCOMPONENTS
$DEVICES
DEVICE "DEV_Resistor_SMD:R_0603"
PART "4.7 kΩ, 1%"
PACKAGE "Resistor_SMD:R_0603"
$ENDDEVICES
'''


EXCELLON = '''
M48
METRIC
T1C0.800
%
G90
T1
X10.0Y-20.0
X11.0Y-20.0G85X13.0Y-20.0
M30
'''


def test_parse_gencad_component_and_bounds():
    components, bounds = parse_gencad(GENCAD)
    assert len(components) == 1
    component = components[0]
    assert (component.library, component.footprint) == ("Resistor_SMD", "R_0603")
    assert component.reference == "R1"
    assert component.value == "4.7 kΩ, 1%"
    assert component.position == Point(38.1, 63.5)
    assert component.rotation_degrees == pytest.approx(90)
    assert component.side is BoardSide.BACK
    assert bounds == Bounds(25.4, 50.8, 50.8, 50.8)


def test_parse_excellon_round_hole_and_slot():
    holes = parse_excellon(EXCELLON)
    assert len(holes) == 2
    assert holes[0].position == Point(10, 20)
    assert holes[0].size == Size(0.8, 0.8)
    assert holes[1].position == Point(12, 20)
    assert holes[1].size == Size(2.8, 0.8)


def test_canonical_layer_preserves_names_and_legacy_numbers():
    assert canonical_layer("F.Cu") == "F.Cu"
    assert canonical_layer(44) == "Edge.Cuts"
    assert canonical_layer("F.SilkS") == "F.Silkscreen"


def test_layer_parameter_accepts_official_names_and_legacy_numbers():
    parameter = KiCadLayerParam()
    assert parameter.convert("F.Silkscreen", None, None) == "F.Silkscreen"
    assert parameter.convert("User.Comments", None, None) == "User.Comments"
    assert parameter.convert("User.9", None, None) == "User.9"
    assert parameter.convert("In1.Cu", None, None) == "In1.Cu"
    assert parameter.convert("44", None, None) == "Edge.Cuts"


def test_gencad_device_package_removes_exporter_shape_suffixes():
    suffixed = GENCAD.replace(
        'SHAPE "Resistor_SMD:R_0603" MIRRORX FLIP',
        'SHAPE "Resistor_SMD:R_0603_6" MIRRORX FLIP',
    ).replace(
        'DEVICE "DEV_Resistor_SMD:R_0603"',
        'DEVICE "DEV_Resistor_SMD:R_0603_6"',
    )
    components, _ = parse_gencad(suffixed)
    assert components[0].footprint == "R_0603"
