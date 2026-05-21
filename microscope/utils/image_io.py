"""
Image I/O utilities for saving numpy arrays as TIFF or PNG.
"""

import numpy as np
import tifffile
from PIL import Image


def save_tiff(array: np.ndarray, path: str) -> None:
    """Save a numpy array as a TIFF file (16-bit compatible)."""
    tifffile.imwrite(path, array)


def save_png(array: np.ndarray, path: str) -> None:
    """Save a numpy array as a PNG file."""
    img = Image.fromarray(array)
    img.save(path, format="PNG")
