from decimal import Decimal as D

import pytest

from pcbdraw.unit import read_resistance


def test_read_resistance():
    assert read_resistance("4k7") == D("4700")
    assert read_resistance("4k7") == D("4700")
    assert read_resistance("4.7R") == D("4.7")
    assert read_resistance("4R7") == D("4.7")
    assert read_resistance("0R47") == D("0.47")
    assert read_resistance("4700k") == D("4700000")
    assert read_resistance("470m") == D("0.47")
    assert read_resistance("470M") == D("470000000")
    assert read_resistance("4M7") == D("4700000")
    assert read_resistance("470") == D("470")


@pytest.mark.parametrize("value", ["R", "K", "k", "M", "G", "m", "Ω", "Ohm", "Ohms"])
def test_read_resistance_rejects_unit_without_number(value):
    with pytest.raises(ValueError, match="Cannot parse"):
        read_resistance(value)


@pytest.mark.parametrize("value", ["0", "0R", "0R0", "0 Ohm"])
def test_read_resistance_accepts_zero(value):
    assert read_resistance(value) == D("0")
