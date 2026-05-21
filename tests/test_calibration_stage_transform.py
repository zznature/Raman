"""Tests for pixel/stage calibration transforms."""

import numpy as np
import pytest

from calibration.exceptions import SingularTransformError
from calibration.models import PixelShift
from calibration.stage_transform import PixelStageTransform
from stage.models import StageShift


def test_pixel_stage_transform_round_trip():
    transform = PixelStageTransform(np.array([[2.0, 0.5], [-0.25, 1.5]]))
    stage = StageShift(dx_um=10.0, dy_um=-4.0)
    pixel = transform.stage_to_pixel(stage)
    recovered = transform.pixel_to_stage(pixel)
    assert recovered.dx_um == pytest.approx(stage.dx_um)
    assert recovered.dy_um == pytest.approx(stage.dy_um)


def test_pixel_to_stage_axis_aligned():
    transform = PixelStageTransform(np.array([[2.0, 0.0], [0.0, -4.0]]))
    stage = transform.pixel_to_stage(PixelShift(dx=8.0, dy=12.0))
    assert stage.dx_um == pytest.approx(4.0)
    assert stage.dy_um == pytest.approx(-3.0)


def test_transform_rejects_singular_matrix():
    with pytest.raises(SingularTransformError):
        PixelStageTransform(np.array([[1.0, 2.0], [2.0, 4.0]]))
