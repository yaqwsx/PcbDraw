"""3D board rendering through ``kicad-cli pcb render``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from tempfile import TemporaryDirectory
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .kicad_cli import KiCadCliError, run_kicad_cli


class Side(Enum):
    FRONT = "top"
    BACK = "bottom"


@dataclass
class RenderAction:
    side: Side = Side.FRONT
    raytraced: bool = False
    orthographic: bool = True
    transparent: bool = False
    padding: int = 30  # pixels of padding around the board after crop
    width: int = 1600
    height: int = 900


def _find_board_bbox(image: Image.Image) -> Optional[Tuple[int, int, int, int]]:
    """
    Detect the board region in the rendered image using edge detection.
    Returns (left, top, right, bottom) or None if nothing found.
    """
    edges = image.convert("L") \
        .filter(ImageFilter.FIND_EDGES) \
        .point(lambda p: 255 if p > 127 else 0)
    # Trim a small border to avoid edge artifacts from the image boundary
    margin = 5
    edges = edges.crop((margin, margin, edges.width - margin, edges.height - margin))
    box = edges.getbbox()
    if box is None:
        return None
    a, b, c, d = box
    return a + margin, b + margin, c + margin + 1, d + margin + 1


def _make_transparent(image: Image.Image) -> Image.Image:
    """
    Make the background of a rendered board image transparent.
    Uses flood fill from corners with a color threshold.
    """
    image = image.convert("RGBA")
    pixel = np.array(image.getpixel((1, 1)))

    np_image = np.array(image)
    for rId, row in enumerate(np_image):
        for cId, elem in enumerate(row):
            fPix = np.array([int(x) for x in elem])
            distance = np.linalg.norm(fPix - pixel)
            if distance < 20:
                ImageDraw.floodfill(image, (cId, rId), (0, 0, 0, 0), thresh=30)
    return image


def renderBoard(
    boardFile: str,
    plan: RenderAction,
) -> Image.Image:
    """
    Render a KiCad board to a PNG image using kicad-cli.

    The image is cropped to the board bounds with padding, matching the
    behavior of the old GUI-automation renderer.

    Returns a PIL Image.
    """
    with TemporaryDirectory() as tmp:
        output = os.path.join(tmp, "render.png")

        cmd: List[str] = [
            "pcb", "render",
            "--output", output,
            "--side", plan.side.value,
            "--width", str(plan.width),
            "--height", str(plan.height),
            "--quality", "high" if plan.raytraced else "basic",
        ]

        if not plan.transparent:
            cmd += ["--background", "opaque"]

        if not plan.orthographic:
            cmd += ["--perspective"]

        cmd.append(boardFile)

        run_kicad_cli(cmd, timeout=300)

        if not os.path.isfile(output):
            raise KiCadCliError("kicad-cli did not produce a rendered image")

        image = Image.open(output).copy()

    # Apply transparency before cropping so that _make_transparent can
    # detect background pixels even when padding is zero.
    if plan.transparent:
        image = _make_transparent(image)

    # Crop to board bounds
    bbox = _find_board_bbox(image)
    if bbox is not None:
        left, top, right, bottom = bbox
        pad = plan.padding
        left = max(0, left - pad)
        top = max(0, top - pad)
        right = min(image.width, right + pad)
        bottom = min(image.height, bottom + pad)
        image = image.crop((left, top, right, bottom))

    return image
