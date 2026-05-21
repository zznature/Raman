"""Unit tests for autofocus.metrics and autofocus.roi."""

import numpy as np
import pytest

from autofocus.models import ROI
from autofocus.metrics import (
    METRICS,
    MetricStrategy,
    brenner,
    get_metric,
    laplacian_variance,
    normalized_variance,
    tenengrad,
)
from autofocus.roi import (
    crop,
    gaussian_blur,
    prepare,
    saturation_ratio,
    to_grayscale,
)


def _random_image(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.random((100, 100)) * 255).astype(np.uint8)


def test_metrics_all_nonnegative_finite():
    img = _random_image()
    roi = ROI(10, 10, 50, 50)
    for name, fn in METRICS.items():
        v = fn(img, roi)
        assert np.isfinite(v), f"{name} produced non-finite value"
        assert v >= 0.0, f"{name} produced negative value {v}"


def test_metrics_higher_score_for_textured():
    flat = np.full((100, 100), 128, dtype=np.uint8)
    stripes = np.zeros((100, 100), dtype=np.uint8)
    stripes[:, ::4] = 255
    stripes[:, 1::4] = 255
    roi = ROI(10, 10, 80, 80)
    for fn in (tenengrad, laplacian_variance, brenner):
        assert fn(stripes, roi) > fn(flat, roi)


def test_metric_strategy_protocol():
    img = _random_image(1)
    roi = ROI(0, 0, 60, 60)
    s = MetricStrategy("tenengrad")
    assert s.name == "tenengrad"
    assert s.score(img, roi) == pytest.approx(tenengrad(img, roi))


def test_get_metric_unknown_raises():
    with pytest.raises(KeyError):
        get_metric("does_not_exist")


def test_metrics_registry_completeness():
    assert set(METRICS.keys()) == {
        "tenengrad",
        "laplacian_variance",
        "brenner",
        "normalized_variance",
    }


def test_roi_invalid_raises():
    img = np.zeros((50, 50), dtype=np.uint8)
    with pytest.raises(ValueError):
        crop(img, ROI(-1, -1, 5, 5))


def test_to_grayscale_passthrough_2d():
    img = np.zeros((20, 20), dtype=np.uint8)
    out = to_grayscale(img)
    assert out.dtype == np.uint8
    assert out.shape == (20, 20)


def test_to_grayscale_rgb():
    rgb = np.zeros((4, 4, 3), dtype=np.float32)
    rgb[:, :, 0] = 1.0
    out = to_grayscale(rgb)
    assert out.shape == (4, 4)
    assert out.dtype == np.float32
    assert out[0, 0] == pytest.approx(0.299, abs=1e-4)


def test_saturation_ratio_uint8():
    bright = np.full((10, 10), 255, dtype=np.uint8)
    mid = np.full((10, 10), 128, dtype=np.uint8)
    assert saturation_ratio(bright) == pytest.approx(1.0)
    assert saturation_ratio(mid) == pytest.approx(0.0)


def test_saturation_ratio_scales_integer_dtype():
    bright = np.full((10, 10), 65535, dtype=np.uint16)
    mid = np.full((10, 10), 32768, dtype=np.uint16)
    assert saturation_ratio(bright) == pytest.approx(1.0)
    assert saturation_ratio(mid) == pytest.approx(0.0)


def test_saturation_ratio_handles_float_ranges():
    normalized_mid = np.full((10, 10), 0.5, dtype=np.float32)
    raw_mid = np.full((10, 10), 128.0, dtype=np.float32)
    assert saturation_ratio(normalized_mid) == pytest.approx(0.0)
    assert saturation_ratio(raw_mid) == pytest.approx(0.0)


def test_gaussian_blur_preserves_shape():
    img = _random_image(2)
    out = gaussian_blur(img)
    assert out.shape == img.shape


def test_prepare_returns_float32_2d():
    img = _random_image(3)
    roi = ROI(5, 5, 30, 20)
    out = prepare(img, roi)
    assert out.shape == (20, 30)
    assert out.dtype == np.float32
