from decimal import Decimal
from typing import List


def erase(string: str, what: List[str]) -> str:
    """
    Given a  string and a list of string, removes all occurrences of items from
    what in the string
    """
    for x in what:
        string = string.replace(x, "")
    return string


def read_resistance(value: str) -> Decimal:
    """
    Given a string, try to parse resistance and return it as Ohms (Decimal)
    """
    p_value = erase(value, ["Ω", "Ohms", "Ohm"]).strip()
    p_value = p_value.replace(" ", "") # Sometimes there are spaces after decimal place
    unit_prefixes = {
        "m": [Decimal(1e-3), Decimal(1e-6)],
        "K": [Decimal(1e3), Decimal(1)],
        "k": [Decimal(1e3), Decimal(1)],
        "M": [Decimal(1e6), Decimal(1e3)],
        "G": [Decimal(1e9), Decimal(1e6)]
    }
    try:
        numerical_value = None
        for prefix, table in unit_prefixes.items():
            if prefix in p_value:
                split = [Decimal(x) if x != "" else Decimal(0) for x in p_value.split(prefix)]
                numerical_value = split[0] * table[0] + split[1] * table[1]
                break
        if numerical_value is not None:
            return numerical_value
    except Exception:
        pass
    raise ValueError(f"Cannot parse '{value}' to resistance")
