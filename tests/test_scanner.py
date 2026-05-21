"""Unit tests for autofocus.scanner."""

import numpy as np
import pytest

from autofocus.exceptions import OutOfRangeError
from autofocus.metrics import MetricStrategy
from autofocus.models import AutofocusParams, ROI
from autofocus.scanner import ZScanner, parabolic_peak
from tests.fakes import FakeZStage, SyntheticFrameProvider


def test_parabolic_peak_symmetric():
    assert parabolic_peak([0.0, 1.0, 2.0], [0.5, 1.0, 0.5]) == pytest.approx(1.0)


def test_parabolic_peak_left_skewed():
    peak = parabolic_peak([0.0, 1.0, 2.0], [0.9, 1.0, 0.5])
    assert peak is not None
    assert 0.5 < peak < 1.0


def test_parabolic_peak_flat_returns_none():
    assert parabolic_peak([0.0, 1.0, 2.0], [1.0, 1.0, 1.0]) is None


def test_parabolic_peak_too_few_returns_none():
    assert parabolic_peak([0.0, 1.0], [0.5, 1.0]) is None


def test_parabolic_peak_unequal_spacing_returns_none():
    assert parabolic_peak([0.0, 1.0, 3.0], [0.5, 1.0, 0.5]) is None


def test_parabolic_peak_outside_bracket_returns_none():
    assert parabolic_peak([0.0, 1.0, 2.0], [0.0, 0.4, 1.0]) is None


def _make_scanner(stage, frames, **param_overrides):
    base = dict(
        z_min_um=-100.0, z_max_um=100.0,
        coarse_range_um=40.0, coarse_step_um=10.0,
        fine_range_um=10.0, fine_step_um=2.0,
        frames_per_z=1, frame_timeout_ms=200, stage_timeout_ms=200,
        max_saturation_ratio=1.0,
    )
    base.update(param_overrides)
    params = AutofocusParams(**base)
    return ZScanner(stage, frames, MetricStrategy("tenengrad"), params)


def test_zscanner_sample_out_of_range_raises():
    stage = FakeZStage(initial_z_um=0.0)
    frames = SyntheticFrameProvider(stage)
    scanner = _make_scanner(stage, frames, z_min_um=0.0, z_max_um=10.0)
    with pytest.raises(OutOfRangeError):
        scanner.sample_score(20.0, ROI(0, 0, 50, 50))


def test_zscanner_sample_honors_settle_ms(monkeypatch):
    stage = FakeZStage(initial_z_um=0.0)
    frames = SyntheticFrameProvider(stage)
    scanner = _make_scanner(stage, frames, settle_ms=123)
    sleeps: list[float] = []

    monkeypatch.setattr("autofocus.scanner.time.sleep", sleeps.append)

    scanner.sample_score(0.0, ROI(0, 0, 50, 50))

    assert sleeps[0] == pytest.approx(0.123)


def test_zscanner_coarse_sweeps_low_to_high():
    stage = FakeZStage(initial_z_um=20.0)
    frames = SyntheticFrameProvider(stage, peak_z_um=0.0)
    scanner = _make_scanner(stage, frames)
    scanner.coarse_scan(0.0, ROI(50, 50, 100, 100))
    moves = stage.history[1:]
    assert moves == sorted(moves)


def test_zscanner_coarse_finds_peak_near_truth():
    stage = FakeZStage(initial_z_um=0.0)
    frames = SyntheticFrameProvider(stage, peak_z_um=5.0, sigma_um=8.0, noise_level=0.02)
    scanner = _make_scanner(stage, frames)
    curve = scanner.coarse_scan(0.0, ROI(50, 50, 100, 100))
    best = curve.best()
    assert best is not None
    assert abs(best.z_um - 5.0) <= 10.0


def test_zscanner_scan_grid_does_not_exceed_requested_upper_bound():
    stage = FakeZStage(initial_z_um=0.0)
    frames = SyntheticFrameProvider(stage)
    scanner = _make_scanner(
        stage,
        frames,
        z_min_um=0.0,
        z_max_um=100.0,
        coarse_range_um=5.0,
        coarse_step_um=6.0,
    )

    curve = scanner.coarse_scan(5.0, ROI(50, 50, 100, 100))

    assert [point.z_um for point in curve.points] == [0.0, 6.0]
