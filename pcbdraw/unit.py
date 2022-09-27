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

    This function can raise a ValueError if the value is invalid
    """
    p_value = erase(value, ["Ω", "Ohms", "Ohm"]).strip()
    p_value = p_value.replace(" ", "") # Sometimes there are spaces after decimal place
    unit_prefixes = {
        "m": Decimal('1e-3'),
        "R": Decimal('1'),
        "K": Decimal('1e3'),
        "k": Decimal('1e3'),
        "M": Decimal('1e6'),
        "G": Decimal('1e9')
    }
    try:
        numerical_value = None
        for prefix, table in unit_prefixes.items():
            if prefix in p_value:
                # Example: 4k7 will have the 4 converted to Decimal(4) and 7 to Decimal(0.7)
                # Then each gets multiplied by the factor and added, so 4000 + 700
                # This method ensures that 4k7 and 4k700 for example yields the same result
                split = p_value.split(prefix)
                n_whole = Decimal(split[0]) if split[0] != "" else Decimal(0)
                n_dec = Decimal('.'+split[1]) if split[1] != "" else Decimal(0)
                numerical_value = n_whole * table + n_dec * table
                break
        if numerical_value is None:
            # If this fails, a decimal.InvalidOperation is raised which is handled by the Exception catch
            numerical_value = Decimal(p_value)
        return numerical_value
    except Exception:
        pass
    raise ValueError(f"Cannot parse '{value}' to resistance")
