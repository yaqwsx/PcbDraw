from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from tempfile import TemporaryDirectory
from typing import Callable, Dict, List, Optional, Tuple, Union, Any, Generator
from pathlib import Path
import numpy as np

# We import the typing under try-catch to allow runtime for systems that have
# old Numpy that don't feature the numpy.typing module, but we want to preserve
# type checking.
try:
    import numpy.typing
except ImportError:
    pass

from PIL import Image, ImageChops, ImageDraw, ImageFilter
from pyvirtualdisplay.smartdisplay import SmartDisplay

from .pcbnew_common import findBoardBoundingBox
from pcbnewTransition import pcbnew # type: ignore

PKG_BASE = os.path.dirname(__file__)
DEBUG_PATH = None


class GuiPuppetError(RuntimeError):
    """
    A wrapper exception that carries original exception and screenshot of the
    virtual screen at the moment of release.
    """
    def __init__(self, msg: str, origin: Exception, img: Optional[Image.Image]) -> None:
        super().__init__(msg)
        self.origin = origin
        self.img = img

    def show(self) -> None:
        if self.img is not None:
            self.img.show()
        else:
            raise RuntimeError("No image to show")


class PcbnewSession:
    """
    An interactive session with Pcbnew running in a virtual display. An instance
    of this class shouldn't be created directly, instead, use startPcbnewSession
    """
    def __init__(self, display: SmartDisplay, pcbnewProcess: subprocess.Popen[bytes], configdir: str) -> None:
        self._display = display
        self._process = pcbnewProcess
        self._configdir = configdir

        if DEBUG_PATH is not None:
            from pathlib import Path
            [f.unlink() for f in Path(DEBUG_PATH).glob("*.png") if f.is_file()]
            self.counter = 1

    def debugDump(self) -> None:
        if DEBUG_PATH is None:
            return
        self.getScreenshot().save(os.path.join(DEBUG_PATH, f"{self.counter}.png"))
        self.counter += 1

    def _xdotool(self, args: List[Any]) -> List[str]:
        """
        Run xdotool with arguments and return its output.
        """
        command = ["xdotool"] + [str(x) for x in args]
        c = subprocess.run(command, capture_output=True)
        output = c.stdout.decode("utf-8")
        return [x.strip() for x in output.split("\n") if len(x.strip())]


    def listWindows(self) -> Dict[str, int]:
        """
        List currently active windows, return mapping "Title -> id"
        """
        windows = self._xdotool(["search", "--pid", self._process.pid])
        res = {}
        for winId in windows:
            name = self._xdotool(["getwindowname", winId])
            if len(name):
                res[name[0]] = int(winId)
        return res

    def waitForWindow(self, titlePattern: str, timeout: int=60,
                      callback: Optional[Callable[[], None]]=None) -> int:
        """
        Waits for a window with title
        """
        return self.waitForWindows([titlePattern], timeout, callback)

    def waitForWindows(self, titlePatterns: List[str], timeout: int=60,
                       callback: Optional[Callable[[], None]]=None) -> int:
        """
        Waits for a window with title
        """
        titlePatterns = [x.lower() for x in titlePatterns]
        for _ in range(timeout + 1):
            if callback is not None:
                callback()
            self.debugDump()
            windows = self.listWindows()
            for title, id in windows.items():
                if any([pattern in title.lower() for pattern in titlePatterns]):
                    return id
            time.sleep(1)
        windows_list = "\n".join([f"- {t}" for t in windows.keys()])
        raise TimeoutError(f"None of '{titlePatterns}' didn't appear within timeout. Available windows:\n{windows_list}")

    def maximizeWindow(self, windowId: int) -> None:
        self._xdotool(["windowmove", windowId, "0", "0"])
        self._xdotool(["windowsize", windowId, "100%", "100%"])
        self._xdotool(["windowactivate", "--sync", windowId])

    def closeWindow(self, windowId: int, timeout: int=5) -> None:
        self._xdotool(["windowkill", windowId])
        for _ in range(timeout * 10):
            if windowId not in self.listWindows().values():
                return
            time.sleep(0.1)
        raise TimeoutError("Waiting on window close timeout")

    def getScreenshot(self) ->Image.Image:
        image = self._display.grab(autocrop=False) # type: ignore
        assert isinstance(image, Image.Image)
        displayWidth, displayHeight = self._display._size
        return image.crop((30, 80, displayWidth - 30, displayHeight - 50))

    def waitForImmovable(self, delta: float=0.1, threshold: int=10, timeout: float=60) -> None:
        """
        Wait until the screen is immovable. Scan the screen every delta seconds
        and if they haven't changed for threshold iterations, stop.
        """
        start = time.time()
        base = self.getScreenshot()
        stableFor = 0
        while True:
            time.sleep(delta)
            current = self.getScreenshot()
            diff = ImageChops.difference(base, current)
            if diff.getbbox() is None:
                stableFor += 1
            else:
                stableFor = 0
            if stableFor >= threshold:
                return
            base = current
            if time.time() - start > timeout:
                raise TimeoutError("Image was not stabilized in timeout")

    def _dismissWarningsOrErrors(self) -> None:
        while True:
            try:
                id = self.waitForWindows(["warning", "error"], timeout=1)
                self._xdotool(["key", "--window", id, "Return"])
            except TimeoutError:
                break

    def _dismissConfigs(self) -> None:
        windows = self.listWindows()
        if "Configure KiCad Settings Path" in windows.keys():
            id = windows["Configure KiCad Settings Path"]
            self._xdotool(["key", "--window", id, "Return"])
        if "Configure Global Footprint Library Table" in windows.keys():
            id = windows["Configure Global Footprint Library Table"]
            self._xdotool(["key", "--window", id, "Return"])
        if "KiCad PCB Editor" in windows.keys():
            id = windows["KiCad PCB Editor"]
            self._xdotool(["key", "--window", id, "Return"])
        if "File Open Error" in windows.keys():
            raise RuntimeError("File Open Error")

    def waitForMainWindow(self) -> int:
        mainId = self.waitForWindow("pcb editor",
            callback=lambda: self._dismissConfigs())
        while "Loading PCB" in self.listWindows().keys():
            self.debugDump()
            self._dismissWarningsOrErrors()
            time.sleep(0.1)
        self._dismissWarningsOrErrors()
        self.debugDump()
        return mainId


    @contextlib.contextmanager
    def start3DViewer(self) -> Generator[ViewerSession, None, None]:
        mainWindow = self.waitForWindow("pcb editor")
        try:
            self._xdotool(["key", "--window", mainWindow, "alt+3"])
            id = self.waitForWindow("3d viewer", 15)
        except TimeoutError:
            # No window shown, try it once more:
            self._xdotool(["key", "--window", mainWindow, "alt+3"])
            id = self.waitForWindow("3d viewer", 15)
        try:
            session = ViewerSession(self, id)
            session.waitForResponsiveness()
            self.maximizeWindow(id)
            yield session
        finally:
            self.closeWindow(id)

class ViewerSession:
    def __init__(self, parent: PcbnewSession, winId: int) -> None:
        self._parent = parent
        self._winId = winId

    def _sendKeys(self, keys: List[str]) -> None:
        self._parent._xdotool(["key", "--window", str(self._winId)] + keys)

    def _click(self, coords: Tuple[int, int]) -> None:
        self._parent._xdotool(["mousemove", "--window", self._winId, coords[0],
                               coords[1], "click", "1"])

    def waitForResponsiveness(self) -> None:
        # We have to wait for board processing, we try to open preferences
        # and then close it. The safest seems to open the menu as it is
        # not locale dependent
        self._sendKeys(["alt+p", "Down", "Return"])
        prefId = self._parent.waitForWindow("Preferences")
        self._parent._xdotool(["key", "--window", prefId, "Escape"])
        while "Preferences" in self._parent.listWindows():
            time.sleep(0.1)

    def showFront(self) -> None:
        self._sendKeys(["z"])
        time.sleep(0.5)
        self._parent.waitForImmovable(threshold=20)

    def showBack(self) -> None:
        self._sendKeys(["Shift+z"])
        time.sleep(0.5)
        self._parent.waitForImmovable(threshold=20)

    def toggleAxisIndicator(self) -> None:
        self._sendKeys(["alt+p"] + 6 * ["Down"] + ["Return"])
        self._parent.waitForImmovable(threshold=20)

    def toggleComponents(self) -> None:
        self._sendKeys(["T", "S", "V"])
        self._parent.waitForImmovable(threshold=20)

    def captureRaytraced(self, withComponents: bool=True) -> Image.Image:
        if not withComponents:
            self.toggleComponents()
        # Enable it
        self._sendKeys(["alt+p", "Return"])
        self._parent.waitForImmovable(threshold=50, timeout=(3 * 60))
        img = self._parent.getScreenshot()
        # Disable it
        self._sendKeys(["alt+p", "Return"])
        self._parent.waitForImmovable(threshold=10)
        if not withComponents:
            self.toggleComponents()
        return img

    def toggleOrthographic(self) -> None:
        # There is no shortcut...
        self._click((676, 44))

    def _rotate(self, angle: int, plusButton: Tuple[int, int],
                minusButton: Tuple[int, int]) -> None:
        if angle % 10 != 0:
            raise RuntimeError("Rotations can be done only in multiples of 10°")
        coords = plusButton if angle > 0 else minusButton
        for _ in range(abs(angle // 10)):
            self._click(coords)
            time.sleep(0.05)

    def rotateX(self, angle: int) -> None:
        self._rotate(angle, (280, 44), (313, 44))

    def rotateY(self, angle: int) -> None:
        self._rotate(angle, (354, 44), (385, 44))

    def rotateZ(self, angle: int) -> None:
        self._rotate(angle, (426, 44), (458, 44))

    def captureRendered(self, withComponents: bool=True) -> Image.Image:
        if not withComponents:
            self.toggleComponents()
            self._parent.waitForImmovable()
        img = self._parent.getScreenshot()
        if not withComponents:
            self.toggleComponents()
            self._parent.waitForImmovable()
        return img


def duplicateKiCadSettings(outputDir: str) -> None:
    """
    Get KiCAD settings and make exact copy in outputdir
    """
    # The argument of constructor creates a headless manager
    source = pcbnew.SETTINGS_MANAGER(True).GetUserSettingsPath()
    Path(outputDir).mkdir(parents=True, exist_ok=True)
    if os.path.exists(source):
        for f in os.listdir(source):
            path = os.path.join(source, f)
            if os.path.isfile(path):
                shutil.copy(path, outputDir)
            else:
                shutil.copytree(os.path.join(source, f), os.path.join(outputDir, f))


@contextlib.contextmanager
def startPcbnewSession(resolution: Tuple[int, int]=(3000, 3000),
                       board: Optional[str]=None,
                       adjustConfig: Optional[Callable[[str], None]]=None,
                       executable: str="pcbnew") -> Generator[PcbnewSession, None, None]:
    command = [executable]
    if board is not None:
        command.append(board)

    try:
        p = None
        with SmartDisplay(size=resolution) as display, TemporaryDirectory() as tempdir:
            try:
                # There are some viewer settings that are persistent. In order
                # to produce consistent results, we provide a new KiCAD config
                # that is a copy of the original and the crucial files are
                # replaced with pristine ones.
                kicadConfigDir = os.path.join(tempdir, "6.0")
                duplicateKiCadSettings(kicadConfigDir)
                shutil.copy(os.path.join(PKG_BASE, "resources", "defaultKiCadSettings", "3d_viewer.json"),
                            os.path.join(kicadConfigDir, "3d_viewer.json"))
                Path(os.path.join(kicadConfigDir, "colors")).mkdir(parents=True, exist_ok=True)
                shutil.copy(os.path.join(PKG_BASE, "resources", "defaultKiCadSettings", "user_colors.json"),
                            os.path.join(kicadConfigDir, "colors", "user.json"))
                if adjustConfig is not None:
                    adjustConfig(kicadConfigDir)

                env = os.environ.copy()
                env["KICAD_CONFIG_HOME"] = tempdir

                p = subprocess.Popen(command,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=env)
                session = PcbnewSession(display, p, tempdir)
                mainId = session.waitForMainWindow()
                session.maximizeWindow(mainId)
                yield session
            except Exception as e:
                raise GuiPuppetError(str(e), e, display.grab())
    finally:
        try:
            if p is not None:
                p.kill()
                p.wait()
        except ProcessLookupError:
            pass

def findBoard(image: Image.Image) -> Tuple[int, int, int, int]:
    """
    Locate the board in the image a return its box
    """
    edges = image.convert("L") \
        .filter(ImageFilter.FIND_EDGES) \
        .point( lambda p: 255 if p > 127 else 0 )
    edges = edges.crop((5, 5, edges.width - 5, edges.height - 5))
    box = edges.getbbox()
    assert box is not None
    a, b, c, d = box
    return a + 5, b + 5, c + 6, d + 6

class Side(Enum):
    FRONT = 0
    BACK = 1

def noPostProcessing(plan: RenderAction, substrate: Image.Image,
                     board: Image.Image) -> Image.Image:
    return board

def postProcessCrop(board: Union[str, pcbnew.BOARD], verticalPadding: int,
                    horizontalPadding: int, makeTransparent: bool=False) \
        -> Callable[[RenderAction, Image.Image, Image.Image], Tuple[Image.Image, Tuple[int, int, int, int]]]:
    """
    Generates a post-processing function that detects the board and crops it
    leaving a specified border around the board. It also returns the KiCAD
    coordinates of top-left and bottom-right corner of the image. The
    coordinates only work correctly when the board is rendered without orientation
    """
    if isinstance(board, str):
        board = pcbnew.LoadBoard(board)
    bBox = findBoardBoundingBox(board)
    def f(plan: RenderAction, substrate: Image.Image, board: Image.Image) \
            -> Tuple[Image.Image, Tuple[int, int, int, int]]:
        stlx, stly, sbrx, sbry = findBoard(substrate)
        ratio = bBox.GetWidth() / (sbrx - stlx) # Number of KiCAD units per pixel
        pxVPadding = verticalPadding / ratio
        pxHPadding = horizontalPadding / ratio
        btlx, btly, bbrx, bbry = findBoard(board)

        if makeTransparent:
            board = board.convert("RGBA")
            pixel = np.array(board.getpixel((1, 1)))

            npBoard = np.array(board) # type: ignore
            # This isn't the fastest way, but given the cost of raytracing it is
            # good enough for now.
            for rId, row in enumerate(npBoard):
                for cId, elem in enumerate(row):
                    fPix = np.array([int(x) for x in elem])
                    distance = np.linalg.norm(fPix - pixel)
                    if distance < 20:
                        ImageDraw.floodfill(board, (cId, rId), (0, 0, 0, 0), thresh=30)



        btlx -= pxHPadding
        bbrx += pxHPadding
        btly -= pxVPadding
        bbry += pxVPadding

        image = board.crop((btlx, btly, bbrx, bbry))
        rtlx = bBox.GetX() + (btlx - stlx) * ratio
        rtly = bBox.GetY() + (btly - stly) * ratio
        rbrx = bBox.GetX() + (bbrx - stlx) * ratio
        rbry = bBox.GetY() + (bbry - stly) * ratio
        return image, (rtlx, rtly, rbrx, rbry)
    return f


@dataclass
class RenderAction:
    side: Side = Side.FRONT
    components: bool = True
    raytraced: bool = False
    orthographic: bool = False
    rotX: int = 0
    rotY: int = 0
    rotZ: int = 0
    postprocess: Optional[Callable[[RenderAction, Image.Image, Image.Image], Any]] = None
    # The post-processing function takes two images: the first one is rendered
    # board substrate without any components in the simplest way possible; the
    # second image is the board redered as the user wished. The first image can
    # be used to locate the board.

    def __post_init__(self) -> None:
        if self.rotX % 10 != 0 or self.rotY % 10 != 0 or self.rotZ % 10 != 0:
            raise RuntimeError("Invalid plot plan - rotation can be only multiple of 10°")

    def execute(self, viewer: ViewerSession) -> Any:
        """
        Executes the plan and promises to leave the viewer in an intact way. We
        could always supply this with a fresh instance
        """
        if self.side == Side.FRONT:
            viewer.showFront()
        else:
            viewer.showBack()
        viewer.toggleAxisIndicator()
        viewer.rotateX(self.rotX)
        viewer.rotateY(self.rotY)
        viewer.rotateZ(self.rotZ)
        if self.orthographic:
            viewer.toggleOrthographic()
        if self.postprocess is not None:
            substrate = viewer.captureRendered(withComponents=False)
        if self.raytraced:
            img = viewer.captureRaytraced(withComponents=self.components)
        else:
            img = viewer.captureRendered(withComponents=self.components)
        viewer.toggleAxisIndicator()
        if self.orthographic:
            viewer.toggleOrthographic()
        if self.postprocess is None:
            return img
        return self.postprocess(self, substrate, img)


def renderBoard(boardFile: str, renderPlans: List[RenderAction],
                baseResolution: Tuple[int, int]=(3000, 3000),
                bgColor1: Optional[Tuple[int, int, int]]=None,
                bgColor2: Optional[Tuple[int, int, int]]=None) -> List[Any]:
    """
    Render KiCAD board using KiCAD's 3D renderer. Since the process has
    significant startup overhead, you can specify multiple images per board via
    plot plans.

    The base resolution doesn't specify the size of the final image, but only
    the size of virtual screen we use for rendering. Use it sufficiently large,
    the actual board will be only about 3/5 of the resolution.

    The function return a list of post processed results. The post processing
    result depends on the post-processing function.
    """
    if baseResolution[0] < 800 or baseResolution[1] < 800:
        raise RuntimeError("Resolution cannot be less than 800×800px")

    def updateConfig(configPath: str) -> None:
        colorFile = os.path.join(configPath, "colors", "user.json")
        with open(colorFile) as f:
            colors = json.load(f)
        if bgColor1 is not None:
            colors["3d_viewer"]["background_top"] = \
                f"rgb({bgColor1[0]}, {bgColor1[1]}, {bgColor1[2]})"
        if bgColor2 is not None:
            colors["3d_viewer"]["background_bottom"] = \
                f"rgb({bgColor2[0]}, {bgColor2[1]}, {bgColor2[2]})"
        with open(colorFile, "w") as f:
            json.dump(colors, f)
    outputs = []
    with startPcbnewSession(resolution=baseResolution, board=boardFile, adjustConfig=updateConfig) as session:
        with session.start3DViewer() as viewer:
            for plan in renderPlans:
                outputs.append(plan.execute(viewer))
    return outputs


def checkForExternalPrerequisites() -> List[str]:
    """
    Returns a list of missing prerequisites
    """
    missing = []
    try:
        subprocess.run(["xvfb-run", "--help"], capture_output=True, check=True)
    except Exception as e:
        missing.append("xvfb")
    try:
        subprocess.run(["xdotool", "--help"], capture_output=True, check=True)
    except Exception as e:
        missing.append("xdotool")
    return missing


def validateExternalPrerequisites() -> None:
    missing = checkForExternalPrerequisites()
    message = ""
    if "xvfb" in missing:
        message += "XVFB is not available. Please install it. The virtual buffer\n" + \
                   "is used for capturing the renderer output.\n"
    if "xdotool" in missing:
        message += "xdotool is no available. Please install it. The tool is used\n" + \
                   "for controlling the graphical viewer.\n"
    if len(message):
        message += "\n\nNote that the 3D rendering work only on Linux. If you want to\n" + \
                   "run you process on Windows, consider running it in WSL or Docker"
        raise RuntimeError(message)


