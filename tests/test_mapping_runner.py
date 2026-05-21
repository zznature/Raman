"""Tests for the offline mapping runner."""

import shutil
from pathlib import Path

import pytest

from mapping.focus_plane import FocusPlane
from mapping.labspec import FakeRamanAcquirer
from mapping.models import PointStatus
from mapping.planner import rect_grid
from mapping.records import JsonlRunRecorder, read_jsonl_records
from mapping.runner import MappingRunner
from stage.memory_stage import MemoryXYZStage


@pytest.fixture
def mapping_tmp_dir(request):
    root = Path(__file__).resolve().parent / "_tmp_mapping"
    path = root / request.node.name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        if path.exists():
            shutil.rmtree(path)
        if root.exists() and not any(root.iterdir()):
            root.rmdir()


def test_mapping_runner_moves_points_and_writes_jsonl(mapping_tmp_dir):
    stage = MemoryXYZStage()
    plane = FocusPlane(a=0.1, b=0.2, c=1.0)
    spectra_dir = mapping_tmp_dir / "spectra"
    raman = FakeRamanAcquirer(output_dir=spectra_dir)
    record_path = mapping_tmp_dir / "points.jsonl"
    recorder = JsonlRunRecorder(record_path)
    runner = MappingRunner(stage=stage, focus_plane=plane, raman=raman, recorder=recorder)
    grid = rect_grid(
        origin_x_um=0.0,
        origin_y_um=0.0,
        x_count=2,
        y_count=1,
        x_step_um=10.0,
        y_step_um=5.0,
    )

    records = runner.run(grid)
    stored = read_jsonl_records(record_path)

    assert [record.status for record in records] == [PointStatus.COMPLETED, PointStatus.COMPLETED]
    assert len(stored) == 2
    assert stored[0]["point_id"] == "P0001"
    assert stored[0]["predicted_z_um"] == 1.0
    assert stored[1]["predicted_z_um"] == 2.0
    assert stored[1]["final_position"] == {"x_um": 10.0, "y_um": 0.0, "z_um": 2.0}
    assert stored[1]["raman"]["status"] == "ok"
    assert (spectra_dir / "P0001.txt").exists()
    assert [point_id for point_id, _ in raman.calls] == ["P0001", "P0002"]


def test_mapping_runner_records_raman_failure_and_continues(mapping_tmp_dir):
    stage = MemoryXYZStage()
    plane = FocusPlane(a=0.0, b=0.0, c=3.0)
    raman = FakeRamanAcquirer(fail_point_ids={"P0002"})
    record_path = mapping_tmp_dir / "points.jsonl"
    recorder = JsonlRunRecorder(record_path)
    runner = MappingRunner(stage=stage, focus_plane=plane, raman=raman, recorder=recorder)
    grid = rect_grid(
        origin_x_um=0.0,
        origin_y_um=0.0,
        x_count=3,
        y_count=1,
        x_step_um=1.0,
        y_step_um=1.0,
    )

    records = runner.run(grid)
    stored = read_jsonl_records(record_path)

    assert [record.status for record in records] == [
        PointStatus.COMPLETED,
        PointStatus.RAMAN_ERROR,
        PointStatus.COMPLETED,
    ]
    assert [row["status"] for row in stored] == ["completed", "raman_error", "completed"]
    assert "P0002" in stored[1]["error"]
    assert len(raman.calls) == 3
