"""Utilities for working with KiCad component references."""

import re
from typing import Iterable, List


_REFERENCE_RANGE = re.compile(
    r"(?P<prefix>[A-Za-z]+)(?P<start>\d+)-(?P=prefix)(?P<end>\d+)"
)


def expand_reference_ranges(references: Iterable[str]) -> List[str]:
    """Expand ranges such as ``R1-R3`` while preserving input order.

    Tokens that are not unambiguous, ascending ranges with a shared prefix
    are returned unchanged so existing reference names keep their meaning.
    Numeric padding is preserved when both ends use the same width.
    """
    expanded: List[str] = []
    for reference in references:
        match = _REFERENCE_RANGE.fullmatch(reference)
        if match is None:
            expanded.append(reference)
            continue

        start_text = match.group("start")
        end_text = match.group("end")
        start = int(start_text)
        end = int(end_text)
        if start > end:
            expanded.append(reference)
            continue

        prefix = match.group("prefix")
        width = len(start_text) if len(start_text) == len(end_text) else 0
        expanded.extend(
            f"{prefix}{number:0{width}d}" if width else f"{prefix}{number}"
            for number in range(start, end + 1)
        )
    return expanded
