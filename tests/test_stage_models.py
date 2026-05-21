"""Tests for generic XYZ stage interfaces and offline implementation."""

import pytest

from stage.memory_stage import MemoryXYZStage
from stage.models import StagePosition


def test_memory_xyz_stage_absolute_and_relative_moves():
    stage = MemoryXYZStage(StagePosition(x_um=1.0, y_um=2.0, z_um=3.0))

    stage.move_absolute_um(x_um=10.0)
    assert stage.get_position_um() == StagePosition(x_um=10.0, y_um=2.0, z_um=3.0)

    stage.move_relative_um(dx_um=-2.0, dy_um=5.0, dz_um=1.5)
    position = stage.get_position_um()
    assert position.x_um == pytest.approx(8.0)
    assert position.y_um == pytest.approx(7.0)
    assert position.z_um == pytest.approx(4.5)
    assert len(stage.history) == 3


def test_memory_xyz_stage_stop_records_state():
    stage = MemoryXYZStage()
    assert stage.stopped is False
    stage.stop()
    assert stage.stopped is True
