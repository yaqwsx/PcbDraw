from pcbdraw.unit import read_resistance
from decimal import Decimal as D


def test_read_resistance():
    assert read_resistance("4k7") == D("4700")
    assert read_resistance("4k7") == D("4700")
    assert read_resistance("4.7R") == D("4.7")
    assert read_resistance("4R7") == D("4.7")
    assert read_resistance("0R47") == D("0.47")
    assert read_resistance("4700k") == D("47000000")
    assert read_resistance("470m") == D("0.47")
    assert read_resistance("470M") == D("470000000")
    assert read_resistance("4M7") == D("4700000")
    assert read_resistance("470") == D("470")
