"""Tests for focus-plane fitting."""

import pytest

from mapping.focus_plane import FocusAnchor, fit_focus_plane


def test_fit_focus_plane_predicts_linear_z():
    anchors = [
        FocusAnchor(0.0, 0.0, 5.0),
        FocusAnchor(10.0, 0.0, 25.0),
        FocusAnchor(0.0, 10.0, 35.0),
        FocusAnchor(10.0, 10.0, 55.0),
    ]

    plane = fit_focus_plane(anchors)

    assert plane.a == pytest.approx(2.0)
    assert plane.b == pytest.approx(3.0)
    assert plane.c == pytest.approx(5.0)
    assert plane.predict_z(2.0, 4.0) == pytest.approx(21.0)
    assert plane.rms_error_um == pytest.approx(0.0, abs=1e-10)
    assert plane.anchor_count == 4


def test_fit_focus_plane_rejects_collinear_anchors():
    anchors = [
        FocusAnchor(0.0, 0.0, 1.0),
        FocusAnchor(1.0, 1.0, 2.0),
        FocusAnchor(2.0, 2.0, 3.0),
    ]

    with pytest.raises(ValueError, match="collinear"):
        fit_focus_plane(anchors)
