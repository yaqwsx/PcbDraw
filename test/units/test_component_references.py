"""Tests for component-reference range handling."""

import pytest

from pcbdraw.component_references import expand_reference_ranges
from pcbdraw.ui import CommaList, ComponentList, plot


def test_expands_ranges_in_place():
    assert expand_reference_ranges(["C1", "R3-R5", "D2", "U7-U8"]) == [
        "C1", "R3", "R4", "R5", "D2", "U7", "U8",
    ]


def test_preserves_zero_padding():
    assert expand_reference_ranges(["R001-R003"]) == ["R001", "R002", "R003"]


@pytest.mark.parametrize("reference", [
    "R5-R3",
    "R1-C3",
    "1-3",
    "R1-r3",
    "R1-Rx",
    "R1-R2-R3",
])
def test_leaves_non_ranges_unchanged(reference):
    assert expand_reference_ranges([reference]) == [reference]


def test_component_list_strips_commas_and_expands_ranges():
    assert ComponentList().convert("R1-R3, C7", None, None) == [
        "R1", "R2", "R3", "C7",
    ]


def test_component_options_use_range_aware_type():
    options = {parameter.name: parameter for parameter in plot.params}

    assert isinstance(options["filter"].type, ComponentList)
    assert isinstance(options["highlight"].type, ComponentList)
    assert isinstance(options["resistor_flip"].type, ComponentList)
    assert type(options["resistor_values"].type) is CommaList
