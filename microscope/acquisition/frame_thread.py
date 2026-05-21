"""
QThread-based frame grabber for continuous image acquisition.

Emits frames as numpy arrays via pyqtSignal for thread-safe GUI updates.
"""

import time
from PyQt5.QtCore import QThread, pyqtSignal

from autofocus.models import Frame
from microscope.camera.driver import CameraDriver
from microscope.camera.exceptions import CameraCaptureError


class FrameGrabThread(QThread):
    """Background thread that continuously grabs frames from the camera."""

    frame_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, driver: CameraDriver, parent=None):
        super().__init__(parent)
        self._driver = driver
        self._running = False

    def run(self) -> None:
        self._running = True
        seq = 0
        while self._running:
            try:
                image = self._driver.wait_for_frame()
                seq += 1
                frame = Frame(image=image, timestamp=time.monotonic(), seq=seq)
                self.frame_ready.emit(frame)
            except CameraCaptureError as e:
                if self._running:
                    self.error_occurred.emit(str(e))
                break

    def stop(self) -> None:
        """Signal the thread to stop and wait for it to finish."""
        self._running = False
        self.wait(2000)
