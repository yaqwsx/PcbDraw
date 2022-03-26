from pcbnewTransition import pcbnew, isV6 # type: ignore
from pcbnew import wxRect # type: ignore
from itertools import chain
from typing import Optional, List
import wx # type: ignore
import os

def getBBoxWithoutContours(edge: pcbnew.EDA_SHAPE) -> pcbnew.wxRect:
    width = edge.GetWidth()
    edge.SetWidth(0)
    bBox = edge.GetBoundingBox()
    edge.SetWidth(width)
    return bBox

def findBoundingBox(edges: List[pcbnew.EDA_SHAPE]) -> pcbnew.wxRect:
    """
    Return a bounding box of all drawings in edges
    """
    if len(edges) == 0:
        raise RuntimeError("No board edges found")
    boundingBox = getBBoxWithoutContours(edges[0])
    for edge in edges[1:]:
        boundingBox = combineBoundingBoxes(boundingBox, getBBoxWithoutContours(edge))
    return boundingBox

def findBoardBoundingBox(board: pcbnew.BOARD) -> wxRect:
    """
    Returns a bounding box (wxRect) of all Edge.Cuts items either in
    specified source area (wxRect) or in the whole board
    """
    edges = collectEdges(board, "Edge.Cuts")
    return findBoundingBox(edges)


def collectEdges(board: pcbnew.BOARD, layerName: str) -> List[pcbnew.EDA_SHAPE]:
    """ Collect edges on given layer including footprints """
    edges = []
    for edge in chain(board.GetDrawings(), *[m.GraphicalItems() for m in board.GetFootprints()]):
        if edge.GetLayerName() != layerName:
            continue
        if isV6() and isinstance(edge, pcbnew.PCB_DIMENSION_BASE):
            continue
        edges.append(edge)
    return edges

def combineBoundingBoxes(a: pcbnew.wxRect, b: pcbnew.wxRect) -> pcbnew.wxRect:
    """ Retrun wxRect as a combination of source bounding boxes """
    x1 = min(a.GetX(), b.GetX())
    y1 = min(a.GetY(), b.GetY())
    x2 = max(a.GetX() + a.GetWidth(), b.GetX() + b.GetWidth())
    y2 = max(a.GetY() + a.GetHeight(), b.GetY() + b.GetHeight())
    # Beware that we cannot use the following code! It will add 1 to width and
    # height. See https://github.com/wxWidgets/wxWidgets/blob/e43895e5317a1e82e295788264553d9839190337/src/common/gdicmn.cpp#L94-L114
    # return wxRect(topLeft, bottomRight)
    return wxRect(x1, y1, x2 - x1, y2 - y1)

def fakeKiCADGui() -> Optional[wx.App]:
    """
    KiCAD assumes wxApp and locale exists. If we invoke a command, fake the
    existence of an app. You should store the application in a top-level
    function of the command
    """
    if os.name != "nt" and os.environ.get("DISPLAY", "").strip() == "":
        return None

    app = wx.App()
    app.InitLocale()
    return app
