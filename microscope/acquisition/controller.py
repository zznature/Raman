"""
Acquisition controller — business logic layer between camera driver and GUI.

Manages camera lifecycle, live preview, and snapshot capture.
"""

import os
import time
import threading
from datetime import datetime
from typing import Optional

import numpy as np

from microscope.camera.driver import CameraDriver
from microscope.camera.exceptions import CameraError
from microscope.config import CAPTURE_DIR, DEFAULT_IMAGE_FORMAT
from microscope.utils.image_io import save_tiff, save_png
from microscope.acquisition.frame_thread import FrameGrabThread
from autofocus.models import Frame
from autofocus.exceptions import FrameTimeoutError


class AcquisitionController:
    """High-level controller for camera acquisition operations."""

    def __init__(self):
        self._driver = CameraDriver()
        self._thread: Optional[FrameGrabThread] = None
        self._last_frame: Optional[Frame] = None
        self._frame_condition = threading.Condition()

    @property
    def driver(self) -> CameraDriver:
        return self._driver

    @property
    def is_connected(self) -> bool:
        return self._driver.connected

    @property
    def is_live(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    @property
    def last_frame(self) -> Optional[Frame]:
        """Return the most recently cached Frame, or None if none yet."""
        return self._last_frame

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> tuple[int, int]:
        """
        Connect to camera.

        Returns:
            (width, height) tuple of the sensor resolution.
        """
        self._driver.connect()
        return self._driver.width, self._driver.height

    def disconnect(self) -> None:
        """Stop live view if running, then disconnect camera."""
        self.stop_live()
        self._driver.disconnect()
        self._last_frame = None

    # ------------------------------------------------------------------
    # Live view
    # ------------------------------------------------------------------

    def start_live(self, on_frame=None, on_error=None) -> None:
        """
        Start live video capture and frame grabbing thread.

        Args:
            on_frame: Callback receiving numpy array for each frame.
            on_error: Callback receiving error message string.
        """
        if self.is_live:
            return

        self._driver.start_capture()
        self._thread = FrameGrabThread(self._driver)

        if on_frame:
            # Forward only the image to the legacy on_frame callback
            self._thread.frame_ready.connect(lambda f: on_frame(f.image))
        # Always cache the latest frame for snapshot
        self._thread.frame_ready.connect(self._cache_frame)

        if on_error:
            self._thread.error_occurred.connect(on_error)

        self._thread.start()

    def stop_live(self) -> None:
        """Stop frame grabbing thread and video capture."""
        if self._thread is not None:
            self._thread.stop()
            self._thread = None
        if self._driver.connected:
            self._driver.stop_capture()

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self, directory: str = CAPTURE_DIR, fmt: str = DEFAULT_IMAGE_FORMAT) -> Optional[str]:
        """
        Save the most recent frame to disk.

        Args:
            directory: Target directory for saved images.
            fmt: Image format, "tiff" or "png".

        Returns:
            Path to saved file, or None if no frame is available.
        """
        if self._last_frame is None:
            return None

        os.makedirs(directory, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"capture_{timestamp}"

        fmt = fmt.lower()
        if fmt == "tiff":
            path = os.path.join(directory, f"{filename}.tiff")
            save_tiff(self._last_frame.image, path)
        elif fmt == "png":
            path = os.path.join(directory, f"{filename}.png")
            save_png(self._last_frame.image, path)
        else:
            raise ValueError(f"Unsupported image format '{fmt}'; expected 'tiff' or 'png'")

        return path

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def set_exposure(self, ms: float) -> float:
        """Set exposure and return actual value applied."""
        return self._driver.set_exposure(ms)

    def get_exposure(self) -> float:
        return self._driver.get_exposure()

    # ------------------------------------------------------------------
    # FrameProvider
    # ------------------------------------------------------------------

    def get_latest(self) -> Frame:
        """Return the most recent cached frame. Raises RuntimeError if no frame received yet."""
        frame = self._last_frame
        if frame is None:
            raise RuntimeError("No frame has been captured yet; start live view first.")
        return frame

    def wait_for_next(self, after_ts: float, timeout_ms: int) -> Frame:
        """Block until a frame with timestamp > after_ts arrives."""
        deadline = time.monotonic() + timeout_ms / 1000.0
        with self._frame_condition:
            while True:
                cur = self._last_frame
                if cur is not None and cur.timestamp > after_ts:
                    return cur
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise FrameTimeoutError(
                        f"No frame newer than {after_ts:.3f}s arrived within {timeout_ms}ms"
                    )
                self._frame_condition.wait(timeout=remaining)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _cache_frame(self, frame: Frame) -> None:
        """Store the latest frame and wake any waiting threads."""
        with self._frame_condition:
            self._last_frame = frame
            self._frame_condition.notify_all()
