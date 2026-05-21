"""Tests for Fourier phase-correlation image registration."""

import numpy as np
import pytest

from calibration.models import ROI
from calibration.phase_correlation import estimate_translation


def _textured_image(seed: int = 0, shape: tuple[int, int] = (128, 128)) -> np.ndarray:
    rng = np.random.default_rng(seed)
    image = rng.normal(0.0, 1.0, shape).astype(np.float32)
    image[20:45, 30:35] += 4.0
    image[70:75, 80:115] += 3.0
    image[90:108, 22:40] -= 2.5
    return image


def _shift_integer(image: np.ndarray, dx: int, dy: int) -> np.ndarray:
    return np.roll(np.roll(image, dy, axis=0), dx, axis=1)


@pytest.mark.parametrize(
    ("dx", "dy"),
    [
        (7, -5),
        (-11, 8),
        (0, 9),
    ],
)
def test_estimate_translation_integer_shift(dx, dy):
    reference = _textured_image()
    moving = _shift_integer(reference, dx=dx, dy=dy)
    result = estimate_translation(reference, moving, upsample=False)
    assert result.shift.dx == pytest.approx(dx, abs=0.01)
    assert result.shift.dy == pytest.approx(dy, abs=0.01)
    assert result.confidence > 0.5


def test_estimate_translation_with_roi():
    reference = _textured_image(shape=(160, 160))
    moving = _shift_integer(reference, dx=-6, dy=4)
    roi = ROI(16, 16, 96, 96)
    result = estimate_translation(reference, moving, roi=roi, upsample=False)
    assert result.shift.dx == pytest.approx(-6, abs=0.01)
    assert result.shift.dy == pytest.approx(4, abs=0.01)
    assert result.roi == roi


def test_estimate_translation_rejects_shape_mismatch():
    reference = np.zeros((32, 32), dtype=np.float32)
    moving = np.zeros((16, 32), dtype=np.float32)
    with pytest.raises(ValueError):
        estimate_translation(reference, moving)
