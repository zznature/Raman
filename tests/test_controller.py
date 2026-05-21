"""End-to-end tests for AutofocusController."""

import pytest

from autofocus.controller import AutofocusController
from autofocus.models import AutofocusParams, FocusStatus, ROI
from stage.exceptions import StageCommandError
from tests.fakes import FakeZStage, SyntheticFrameProvider


def _make_params(**overrides):
    base = dict(
        z_min_um=-100.0, z_max_um=100.0,
        coarse_range_um=40.0, coarse_step_um=10.0,
        fine_range_um=10.0, fine_step_um=2.0,
        frames_per_z=1, frame_timeout_ms=200, stage_timeout_ms=200,
        max_saturation_ratio=1.0,
    )
    base.update(overrides)
    return AutofocusParams(**base)


def test_run_single_finds_peak():
    stage = FakeZStage(initial_z_um=0.0)
    frames = SyntheticFrameProvider(stage, peak_z_um=5.0, sigma_um=8.0, noise_level=0.02)
    ctrl = AutofocusController(stage=stage, frames=frames)
    result = ctrl.run_single(ROI(50, 50, 100, 100), _make_params())
    assert result.status in (FocusStatus.OK, FocusStatus.LOW_CONFIDENCE)
    assert result.z_best_um is not None
    assert abs(result.z_best_um - 5.0) <= 2.0


def test_run_single_out_of_range_when_z0_far_below_min():
    stage = FakeZStage(initial_z_um=-200.0)
    frames = SyntheticFrameProvider(stage)
    ctrl = AutofocusController(stage=stage, frames=frames)
    result = ctrl.run_single(ROI(50, 50, 100, 100), _make_params())
    assert result.status == FocusStatus.OUT_OF_RANGE


def test_run_single_progress_callback_invoked():
    stage = FakeZStage(initial_z_um=0.0)
    frames = SyntheticFrameProvider(stage, peak_z_um=5.0, sigma_um=8.0, noise_level=0.02)
    ctrl = AutofocusController(stage=stage, frames=frames)
    calls: list = []
    ctrl.run_single(ROI(50, 50, 100, 100), _make_params(), on_progress=calls.append)
    assert len(calls) > 1


def test_run_single_low_texture_returns_no_peak():
    stage = FakeZStage(initial_z_um=0.0)
    frames = SyntheticFrameProvider(
        stage, peak_z_um=10000.0, sigma_um=1.0, noise_level=0.0
    )
    ctrl = AutofocusController(stage=stage, frames=frames)
    result = ctrl.run_single(ROI(50, 50, 100, 100), _make_params())
    assert result.status == FocusStatus.NO_PEAK


def test_run_single_stage_command_error_returns_stage_error():
    class FailingStage(FakeZStage):
        def move_absolute_um(self, z_um: float) -> None:
            raise StageCommandError("bad stage response")

    stage = FailingStage(initial_z_um=0.0)
    frames = SyntheticFrameProvider(stage)
    ctrl = AutofocusController(stage=stage, frames=frames)
    result = ctrl.run_single(ROI(50, 50, 100, 100), _make_params())
    assert result.status == FocusStatus.STAGE_ERROR
    assert "bad stage response" in result.message
