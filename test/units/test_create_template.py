from pathlib import Path

from pcbdraw.create_template import extract_board_footprints
from pcbdraw.kicad_sexpr import (
    component_footprint_ids, component_properties, normalize_embedded_footprint,
    prepare_footprint_for_export,
)


def test_extract_embedded_footprints_preserves_forms():
    board = '''(kicad_pcb
      (version 20240108)
      (footprint "Lib:One"
        (layer "F.Cu")
        (property "Reference" "U1")
        (fp_text user "parentheses: (test)" (layer "F.SilkS")))
      (footprint "Lib:Two" (layer "B.Cu"))
    )'''
    footprints = extract_board_footprints(board)
    assert set(footprints) == {("Lib", "One"), ("Lib", "Two")}
    assert 'parentheses: (test)' in footprints[("Lib", "One")]
    assert "(version 20240108)" in footprints[("Lib", "One")]


def test_extract_board_fixture_uses_last_instance_per_id():
    board = Path("test/resources/ArduinoLearningKitStarter-v10.kicad_pcb").read_text()
    footprints = extract_board_footprints(board)
    assert ("yaqwsx", "arduino_nano") in footprints
    assert len(footprints) < 80


def test_board_footprint_ids_are_read_without_gencad_suffixes():
    board = Path("test/resources/ArduinoLearningKitStarter-v10.kicad_pcb").read_text()
    identifiers = component_footprint_ids(board)
    assert identifiers["C3"] == ("Capacitors_SMD", "C_1206_HandSoldering")


def test_board_component_properties_are_indexed_by_reference():
    board = '''(kicad_pcb
      (footprint "Resistor_THT:R_Axial"
        (property "Reference" "R1")
        (property "Value" "12k3")
        (property "ToL" "1%")
        (property "Description" "precision resistor")))'''

    assert component_properties(board) == {
        "R1": {"tol": "1%", "description": "precision resistor"}
    }


def test_legacy_component_properties_use_fp_text_reference():
    board = '''(kicad_pcb
      (footprint "Resistor_THT:R_Axial"
        (property "tol" "2%")
        (fp_text reference "R2" (at 0 0) (layer "F.SilkS"))))'''

    assert component_properties(board) == {"R2": {"tol": "2%"}}


def test_extract_back_footprint_restores_library_orientation():
    board = Path("test/resources/ArduinoLearningKitStarter-v10.kicad_pcb").read_text()
    footprint = extract_board_footprints(board)[
        ("Capacitors_SMD", "C_1206_HandSoldering")
    ]
    assert '(generator "pcbdraw")' in footprint
    assert '(layer "F.Cu")' in footprint
    assert '(layer "B.Cu")' not in footprint
    assert "(start 1 -1.025)" in footprint
    assert "(at -2 0 0)" in footprint
    assert footprint.count("(hide yes)") >= 2


def test_prepare_footprint_hides_reference_and_value():
    footprint = '''(footprint "Example"
      (property "Reference" "REF**" (at 0 0 0) (layer "F.SilkS"))
      (property "Value" "Example" (at 0 1 0) (layer "F.Fab")))'''
    prepared = prepare_footprint_for_export(footprint)
    assert prepared.count("(hide yes)") == 2


def test_backside_arc_normalization_reverses_arc_direction():
    footprint = '''(footprint "Arc"
      (layer "B.Cu")
      (at 10 20 90)
      (fp_arc (start 1 2) (mid 3 4) (end 5 6) (layer "B.SilkS")))'''
    normalized = normalize_embedded_footprint(footprint)
    assert '(layer "F.Cu")' in normalized
    assert '(layer "F.SilkS")' in normalized
    assert "(start 5 -6)" in normalized
    assert "(mid 3 -4)" in normalized
    assert "(end 1 -2)" in normalized
