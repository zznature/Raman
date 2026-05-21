"""Tests for mapping grid planning."""

import pytest

from mapping.planner import rect_grid


def test_rect_grid_generates_snake_order():
    grid = rect_grid(
        origin_x_um=10.0,
        origin_y_um=20.0,
        x_count=3,
        y_count=2,
        x_step_um=5.0,
        y_step_um=2.0,
        snake=True,
    )

    assert [point.point_id for point in grid] == [
        "P0001",
        "P0002",
        "P0003",
        "P0004",
        "P0005",
        "P0006",
    ]
    assert [(point.x_um, point.y_um) for point in grid] == [
        (10.0, 20.0),
        (15.0, 20.0),
        (20.0, 20.0),
        (20.0, 22.0),
        (15.0, 22.0),
        (10.0, 22.0),
    ]


def test_rect_grid_rejects_empty_dimensions():
    with pytest.raises(ValueError):
        rect_grid(
            origin_x_um=0.0,
            origin_y_um=0.0,
            x_count=0,
            y_count=1,
            x_step_um=1.0,
            y_step_um=1.0,
        )
