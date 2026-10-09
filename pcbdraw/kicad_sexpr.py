"""Small, token-preserving helpers for KiCad footprint S-expressions."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple


_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_FORM_NAME_RE = re.compile(r"\s*([^\s()]+)")
_AT_RE = re.compile(
    rf"\(at\s+({_NUMBER})\s+({_NUMBER})(?:\s+({_NUMBER}))?(\s+unlocked)?\)"
)
_POINT_RE = re.compile(
    rf"\((start|mid|end|center|xy|offset|rect_delta)\s+({_NUMBER})\s+({_NUMBER})\)"
)


def _forms_with_spans(document: str, form_name: str) -> List[Tuple[int, int]]:
    """Return spans for matching forms at any nesting depth."""
    stack: List[Tuple[int, Optional[str]]] = []
    spans: List[Tuple[int, int]] = []
    in_string = False
    escaped = False

    for index, character in enumerate(document):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "(":
            match = _FORM_NAME_RE.match(document, index + 1)
            stack.append((index, match.group(1) if match else None))
        elif character == ")" and stack:
            start, name = stack.pop()
            if name == form_name:
                spans.append((start, index + 1))
    return spans


def top_level_forms(document: str, form_name: str) -> Iterable[str]:
    """Yield matching direct child forms without rewriting their contents."""
    all_spans = _forms_with_spans(document, form_name)
    direct_children = set(_direct_child_spans(document))
    for start, end in all_spans:
        if (start, end) in direct_children:
            yield document[start:end]


def _direct_child_spans(document: str) -> Iterable[Tuple[int, int]]:
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, character in enumerate(document):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "(":
            if depth == 1:
                start = index
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 1 and start >= 0:
                yield start, index + 1
                start = -1


def _format_number(value: float) -> str:
    if abs(value) < 1e-12:
        return "0"
    return f"{value:.12g}"


def _swap_front_back_layers(document: str) -> str:
    placeholder = "__PCBDRAW_FRONT_LAYER__"
    document = re.sub(r'"F\.([^"\s]+)"', rf'"{placeholder}.\1"', document)
    document = re.sub(r'"B\.([^"\s]+)"', r'"F.\1"', document)
    document = document.replace(f'"{placeholder}.', '"B.')
    return document


def _mirror_arc_endpoints(document: str) -> str:
    spans = (_forms_with_spans(document, "fp_arc")
             + _forms_with_spans(document, "gr_arc"))
    for start, end in sorted(spans, reverse=True):
        arc = document[start:end]
        start_match = re.search(rf"\(start\s+({_NUMBER})\s+({_NUMBER})\)", arc)
        end_match = re.search(rf"\(end\s+({_NUMBER})\s+({_NUMBER})\)", arc)
        if start_match is None or end_match is None:
            continue
        replacement = arc[:start_match.start()] + (
            f"(start {end_match.group(1)} {end_match.group(2)})"
        ) + arc[start_match.end():end_match.start()] + (
            f"(end {start_match.group(1)} {start_match.group(2)})"
        ) + arc[end_match.end():]
        document = document[:start] + replacement + document[end:]
    return document


def _hide_fields(document: str) -> str:
    """Hide Reference and Value fields, matching the legacy template builder."""
    for property_form in list(top_level_forms(document, "property")):
        match = re.match(r'\(property\s+"(Reference|Value)"', property_form)
        if match is None or re.search(r"\(hide\s+yes\)", property_form):
            continue
        hidden = property_form[:-1] + "\n\t\t(hide yes)\n\t)"
        document = document.replace(property_form, hidden, 1)

    for text_form in list(top_level_forms(document, "fp_text")):
        if not re.match(r"\(fp_text\s+(reference|value)\b", text_form):
            continue
        if re.search(r"(?:^|\s)hide(?:\s|\))", text_form):
            continue
        layer = re.search(r"\(layer\s+[^)]+\)", text_form)
        if layer is None:
            continue
        hidden = text_form[:layer.end()] + " hide" + text_form[layer.end():]
        document = document.replace(text_form, hidden, 1)
    return document


def prepare_footprint_for_export(document: str) -> str:
    """Hide fields that must not become part of a reusable drawing template."""
    return _hide_fields(document)


def component_footprint_ids(document: str) -> Dict[str, Tuple[str, str]]:
    """Return authoritative reference-to-footprint IDs from a board file."""
    result = {}
    for footprint in top_level_forms(document, "footprint"):
        identifier_match = re.match(
            r'\(footprint\s+"((?:\\.|[^"\\])*)"', footprint
        )
        if identifier_match is None:
            continue
        reference = None
        for property_form in top_level_forms(footprint, "property"):
            property_match = re.match(
                r'\(property\s+"Reference"\s+"((?:\\.|[^"\\])*)"',
                property_form,
            )
            if property_match is not None:
                reference = property_match.group(1)
                break
        if reference is None:
            for text_form in top_level_forms(footprint, "fp_text"):
                text_match = re.match(
                    r'\(fp_text\s+reference\s+(?:"((?:\\.|[^"\\])*)"|([^\s()]+))',
                    text_form,
                )
                if text_match is not None:
                    reference = text_match.group(1) or text_match.group(2)
                    break
        if reference is None:
            continue
        identifier = re.sub(r'\\(["\\])', r'\1', identifier_match.group(1))
        reference = re.sub(r'\\(["\\])', r'\1', reference)
        library, separator, name = identifier.partition(":")
        result[reference] = (library, name) if separator else ("", library)
    return result


def component_properties(document: str) -> Dict[str, Dict[str, str]]:
    """Return custom footprint properties indexed by component reference."""
    result = {}
    for footprint in top_level_forms(document, "footprint"):
        properties = {}
        for property_form in top_level_forms(footprint, "property"):
            match = re.match(
                r'\(property\s+"((?:\\.|[^"\\])*)"\s+"((?:\\.|[^"\\])*)"',
                property_form,
            )
            if match is None:
                continue
            name = re.sub(r'\\(["\\])', r'\1', match.group(1))
            value = re.sub(r'\\(["\\])', r'\1', match.group(2))
            properties[name.lower()] = value
        reference = properties.get("reference")
        if reference is None:
            for text_form in top_level_forms(footprint, "fp_text"):
                match = re.match(
                    r'\(fp_text\s+reference\s+(?:"((?:\\.|[^"\\])*)"|([^\s()]+))',
                    text_form,
                )
                if match is not None:
                    reference = match.group(1) or match.group(2)
                    reference = re.sub(r'\\(["\\])', r'\1', reference)
                    break
        if reference is not None:
            result[reference] = {
                name: value for name, value in properties.items()
                if name not in {"reference", "value", "footprint"}
            }
    return result


def normalize_embedded_footprint(document: str) -> str:
    """Return a board footprint in front-side, zero-rotation library orientation.

    Board files store child text and pad angles in board orientation and mirror
    back-side geometry.  The old pcbnew implementation undid those transforms
    before creating a template; this function applies the same normalization to
    the serialized footprint.
    """
    root_at = next(iter(top_level_forms(document, "at")), None)
    orientation = 0.0
    if root_at is not None:
        match = _AT_RE.fullmatch(root_at)
        if match is not None and match.group(3) is not None:
            orientation = float(match.group(3))
        document = document.replace(root_at, "", 1)

    root_layer = next(iter(top_level_forms(document, "layer")), None)
    on_back = root_layer is not None and "B.Cu" in root_layer
    if on_back:
        document = _swap_front_back_layers(document)

    def normalize_at(match: re.Match[str]) -> str:
        x = float(match.group(1))
        y = float(match.group(2))
        angle = float(match.group(3) or 0) - orientation
        if on_back:
            y = -y
            angle = -angle
        suffix = match.group(4) or ""
        return (f"(at {_format_number(x)} {_format_number(y)} "
                f"{_format_number(angle % 360)}{suffix})")

    document = _AT_RE.sub(normalize_at, document)
    if on_back:
        def mirror_point(match: re.Match[str]) -> str:
            return (f"({match.group(1)} {match.group(2)} "
                    f"{_format_number(-float(match.group(3)))})")

        document = _POINT_RE.sub(mirror_point, document)
        document = _mirror_arc_endpoints(document)

        def remove_mirror(match: re.Match[str]) -> str:
            values = [value for value in match.group(1).split() if value != "mirror"]
            return f"(justify {' '.join(values)})" if values else ""

        document = re.sub(r"\(justify\s+([^)]+)\)", remove_mirror, document)

    return _hide_fields(document)
