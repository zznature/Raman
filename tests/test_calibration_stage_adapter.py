"""Tests for applying calibration corrections to XYZStage."""

import numpy as np
import pytest

from calibration.stage_adapter import estimate_and_apply_xy_correction
from calibration.stage_transform import PixelStageTransform
from stage.memory_stage import MemoryXYZStage


def _textured_image(seed: int = 8, shape: tuple[int, int] = (128, 128)) -> np.ndarray:
    rng = np.random.default_rng(seed)
    image = rng.normal(0.0, 1.0, shape).astype(np.float32)
    image[18:42, 24:50] += 4.0
    image[70:90, 82:112] -= 3.0
    return image


def _shift_integer(image: np.ndarray, dx: int, dy: int) -> np.ndarray:
    return np.roll(np.roll(image, dy, axis=0), dx, axis=1)


def test_estimate_and_apply_xy_correction_moves_xyz_stage():
    reference = _textured_image()
    current = _shift_integer(reference, dx=8, dy=-6)
    transform = PixelStageTransform(np.array([[2.0, 0.0], [0.0, 3.0]]))
    stage = MemoryXYZStage()

    correction = estimate_and_apply_xy_correction(
        reference,
        current,
        transform,
        stage,
        min_confidence=0.2,
    )

    position = stage.get_position_um()
    assert correction.dx_um == pytest.approx(-4.0, abs=0.01)
    assert correction.dy_um == pytest.approx(2.0, abs=0.01)
    assert correction.dz_um == pytest.approx(0.0)
    assert position.x_um == pytest.approx(-4.0, abs=0.01)
    assert position.y_um == pytest.approx(2.0, abs=0.01)
    assert position.z_um == pytest.approx(0.0)
