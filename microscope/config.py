"""
Configuration constants for IDS UI-358x camera acquisition system.
"""

import os
import ctypes

# ---------------------------------------------------------------------------
# DLL path injection (must happen before importing pyueye)
# IDS Software Suite default installation path on Windows
# ---------------------------------------------------------------------------
IDS_DLL_DIR = os.environ.get(
    "IDS_DLL_DIR",
    r"C:\Program Files\IDS\uEye\develop\bin",
)

if os.path.isdir(IDS_DLL_DIR):
    os.add_dll_directory(IDS_DLL_DIR)
    os.environ["PATH"] = IDS_DLL_DIR + os.pathsep + os.environ.get("PATH", "")

# ---------------------------------------------------------------------------
# Camera defaults
# ---------------------------------------------------------------------------
DEFAULT_EXPOSURE_MS = 10.0
DEFAULT_PIXEL_CLOCK_MHZ = 30
NUM_RING_BUFFERS = 3
WAIT_TIMEOUT_MS = 1000

# ---------------------------------------------------------------------------
# Image save defaults
# ---------------------------------------------------------------------------
CAPTURE_DIR = os.environ.get("RAMAN_CAPTURE_DIR", "./captures")
DEFAULT_IMAGE_FORMAT = "tiff"  # "tiff" or "png"

# ---------------------------------------------------------------------------
# GUI defaults
# ---------------------------------------------------------------------------
PREVIEW_MAX_WIDTH = 800
PREVIEW_MAX_HEIGHT = 600
