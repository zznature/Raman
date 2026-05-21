"""Tests for high-level XY correction calculation."""

import numpy as np
import pytest

from calibration.exceptions import LowConfidenceError
from calibration.stage_transform import PixelStageTransform
from calibration.xy_corrector import estimate_xy_correction
from stage.models import StageShift


def _textured_image(seed: int = 4, shape: tuple[int, int] = (128, 128)) -> np.ndarray:
    rng = np.random.default_rng(seed)
    image = rng.normal(0.0, 1.0, shape).astype(np.float32)
    image[24:42, 36:52] += 5.0
    image[76:82, 70:118] += 3.0
    return image


def _shift_integer(image: np.ndarray, dx: int, dy: int) -> np.ndarray:
    return np.roll(np.roll(image, dy, axis=0), dx, axis=1)


def test_estimate_xy_correction_returns_opposite_stage_move():
    reference = _textured_image()
    current = _shift_integer(reference, dx=8, dy=-6)
    transform = PixelStageTransform(np.array([[2.0, 0.0], [0.0, 3.0]]))

    correction = estimate_xy_correction(
        reference,
        current,
        transform,
        min_confidence=0.2,
    )

    assert isinstance(correction, StageShift)
    assert correction.dx_um == pytest.approx(-4.0, abs=0.01)
    assert correction.dy_um == pytest.approx(2.0, abs=0.01)


def test_estimate_xy_correction_enforces_confidence_threshold():
    reference = _textured_image()
    current = _shift_integer(reference, dx=2, dy=2)
    transform = PixelStageTransform(np.eye(2))

    with pytest.raises(LowConfidenceError):
        estimate_xy_correction(
            reference,
            current,
            transform,
            min_confidence=0.999,
        )
