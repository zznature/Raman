"""
Low-level pyueye SDK wrapper for IDS UI-358x cameras.

Manages the full camera lifecycle: init, memory allocation, capture, and cleanup.
"""

import ctypes
import numpy as np
from pyueye import ueye

from microscope.config import (
    DEFAULT_EXPOSURE_MS,
    DEFAULT_PIXEL_CLOCK_MHZ,
    NUM_RING_BUFFERS,
    WAIT_TIMEOUT_MS,
)
from microscope.camera.exceptions import CameraInitError, CameraMemoryError, CameraCaptureError


class CameraDriver:
    """Wraps pyueye SDK calls for a single IDS USB camera."""

    def __init__(self):
        self._cam = ueye.HIDS(0)
        self._mem_ptrs = []
        self._mem_ids = []
        self._width = 0
        self._height = 0
        self._bits_per_pixel = 8  # MONO8
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Initialize camera and allocate ring buffer memory."""
        ret = ueye.is_InitCamera(self._cam, None)
        if ret != ueye.IS_SUCCESS:
            raise CameraInitError(f"is_InitCamera failed with code {ret}")

        # Set mono 8-bit color mode
        ret = ueye.is_SetColorMode(self._cam, ueye.IS_CM_MONO8)
        if ret != ueye.IS_SUCCESS:
            self._exit_camera()
            raise CameraInitError(f"is_SetColorMode failed with code {ret}")

        # Read sensor AOI to get resolution
        rect_aoi = ueye.IS_RECT()
        ret = ueye.is_AOI(
            self._cam, ueye.IS_AOI_IMAGE_GET_AOI, rect_aoi, ueye.sizeof(rect_aoi)
        )
        if ret != ueye.IS_SUCCESS:
            self._exit_camera()
            raise CameraInitError(f"is_AOI GET failed with code {ret}")

        self._width = rect_aoi.s32Width.value
        self._height = rect_aoi.s32Height.value

        try:
            # Set pixel clock
            pixel_clock = ueye.UINT(DEFAULT_PIXEL_CLOCK_MHZ)
            ret = ueye.is_PixelClock(
                self._cam, ueye.IS_PIXELCLOCK_CMD_SET, pixel_clock, ueye.sizeof(pixel_clock)
            )
            if ret != ueye.IS_SUCCESS:
                raise CameraInitError(f"is_PixelClock SET failed with code {ret}")

            # Set default exposure
            self.set_exposure(DEFAULT_EXPOSURE_MS)

            # Allocate ring buffer
            self._alloc_ring_buffer()
        except CameraInitError:
            self._free_ring_buffer()
            self._exit_camera()
            raise
        except CameraCaptureError:
            self._free_ring_buffer()
            self._exit_camera()
            raise
        except CameraMemoryError:
            self._free_ring_buffer()
            self._exit_camera()
            raise

        self._connected = True

    def disconnect(self) -> None:
        """Stop capture and release all resources."""
        if not self._connected:
            return
        self.stop_capture()
        self._free_ring_buffer()
        self._exit_camera()
        self._connected = False

    # ------------------------------------------------------------------
    # Capture control
    # ------------------------------------------------------------------

    def start_capture(self) -> None:
        """Start continuous (live) video capture."""
        ret = ueye.is_CaptureVideo(self._cam, ueye.IS_DONT_WAIT)
        if ret != ueye.IS_SUCCESS:
            raise CameraCaptureError(f"is_CaptureVideo failed with code {ret}")

    def stop_capture(self) -> None:
        """Stop live video capture."""
        ueye.is_StopLiveVideo(self._cam, ueye.IS_FORCE_VIDEO_STOP)

    def wait_for_frame(self) -> np.ndarray:
        """
        Block until the next frame is available, then return a copy as numpy array.

        Returns:
            numpy.ndarray of shape (height, width) with dtype uint8.

        Raises:
            CameraCaptureError if wait times out or copy fails.
        """
        mem_ptr = ueye.c_mem_p()
        mem_id = ueye.INT()

        ret = ueye.is_WaitForNextImage(
            self._cam, WAIT_TIMEOUT_MS, mem_ptr, mem_id
        )
        if ret != ueye.IS_SUCCESS:
            raise CameraCaptureError(f"is_WaitForNextImage failed with code {ret}")

        try:
            # Copy pixel data from locked buffer
            array = ueye.get_data(
                mem_ptr,
                self._width,
                self._height,
                self._bits_per_pixel,
                self._width,  # line increment for MONO8
                copy=True,
            )
        except Exception as exc:
            raise CameraCaptureError("Failed to copy image data from locked buffer") from exc
        finally:
            # Unlock the buffer so it can be reused.
            ueye.is_UnlockSeqBuf(self._cam, mem_id, mem_ptr)

        return array.reshape((self._height, self._width))

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def set_exposure(self, ms: float) -> float:
        """
        Set exposure time in milliseconds.

        Returns:
            The actual exposure time set by the camera (may differ from requested).
        """
        exposure = ueye.DOUBLE(ms)
        ret = ueye.is_Exposure(
            self._cam,
            ueye.IS_EXPOSURE_CMD_SET_EXPOSURE,
            exposure,
            ueye.sizeof(exposure),
        )
        if ret != ueye.IS_SUCCESS:
            raise CameraCaptureError(f"is_Exposure SET failed with code {ret}")
        return exposure.value

    def get_exposure(self) -> float:
        """Get current exposure time in milliseconds."""
        exposure = ueye.DOUBLE()
        ueye.is_Exposure(
            self._cam,
            ueye.IS_EXPOSURE_CMD_GET_EXPOSURE,
            exposure,
            ueye.sizeof(exposure),
        )
        return exposure.value

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _alloc_ring_buffer(self) -> None:
        """Allocate NUM_RING_BUFFERS image memory buffers and add to sequence."""
        try:
            for _ in range(NUM_RING_BUFFERS):
                mem_ptr = ueye.c_mem_p()
                mem_id = ueye.INT()

                ret = ueye.is_AllocImageMem(
                    self._cam,
                    self._width,
                    self._height,
                    self._bits_per_pixel,
                    mem_ptr,
                    mem_id,
                )
                if ret != ueye.IS_SUCCESS:
                    raise CameraMemoryError(f"is_AllocImageMem failed with code {ret}")

                ret = ueye.is_AddToSequence(self._cam, mem_ptr, mem_id)
                if ret != ueye.IS_SUCCESS:
                    ueye.is_FreeImageMem(self._cam, mem_ptr, mem_id)
                    raise CameraMemoryError(f"is_AddToSequence failed with code {ret}")

                self._mem_ptrs.append(mem_ptr)
                self._mem_ids.append(mem_id)

            ret = ueye.is_InitImageQueue(self._cam, 0)
            if ret != ueye.IS_SUCCESS:
                raise CameraMemoryError(f"is_InitImageQueue failed with code {ret}")
        except CameraMemoryError:
            self._free_ring_buffer()
            raise

    def _free_ring_buffer(self) -> None:
        """Clear sequence and free all allocated image memory."""
        ueye.is_ClearSequence(self._cam)
        for mem_ptr, mem_id in zip(self._mem_ptrs, self._mem_ids):
            ueye.is_FreeImageMem(self._cam, mem_ptr, mem_id)
        self._mem_ptrs.clear()
        self._mem_ids.clear()

    def _exit_camera(self) -> None:
        """Close camera handle."""
        ueye.is_ExitCamera(self._cam)
