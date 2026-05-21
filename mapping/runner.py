"""Offline-first Raman mapping runner."""

import time
from collections.abc import Iterable

from mapping.focus_plane import FocusPlane
from mapping.labspec import RamanAcquirer
from mapping.models import AcquisitionResult, MappingPoint, PointRecord, PointStatus
from mapping.records import JsonlRunRecorder
from stage.models import StagePosition, XYZStage


class MappingRunner:
    """Run an ordered list of mapping points through motion and Raman acquisition."""

    def __init__(
        self,
        *,
        stage: XYZStage,
        focus_plane: FocusPlane,
        raman: RamanAcquirer,
        recorder: JsonlRunRecorder,
        settle_timeout_ms: int = 3000,
        continue_on_point_error: bool = True,
    ):
        self.stage = stage
        self.focus_plane = focus_plane
        self.raman = raman
        self.recorder = recorder
        self.settle_timeout_ms = settle_timeout_ms
        self.continue_on_point_error = continue_on_point_error

    def run(self, points: Iterable[MappingPoint]) -> list[PointRecord]:
        """Execute all points and append one JSONL record per point."""
        records: list[PointRecord] = []
        for point in points:
            record = self._run_point(point)
            records.append(record)
            if record.status != PointStatus.COMPLETED and not self.continue_on_point_error:
                break
        return records

    def _run_point(self, point: MappingPoint) -> PointRecord:
        started_at = time.time()
        predicted_z = (
            float(point.z_um)
            if point.z_um is not None
            else self.focus_plane.predict_z(point.x_um, point.y_um)
        )
        final_position: StagePosition | None = None
        raman_result: AcquisitionResult | None = None
        status = PointStatus.COMPLETED
        error = ""

        try:
            self.stage.move_absolute_um(x_um=point.x_um, y_um=point.y_um, z_um=predicted_z)
            self.stage.wait_settled(self.settle_timeout_ms)
            final_position = self.stage.get_position_um()
        except Exception as exc:  # noqa: BLE001 - runner must persist point failures
            status = PointStatus.STAGE_ERROR
            error = str(exc)
        else:
            raman_result = self.raman.acquire_point(
                point.point_id,
                metadata={
                    "planned_x_um": point.x_um,
                    "planned_y_um": point.y_um,
                    "predicted_z_um": predicted_z,
                    "final_position": {
                        "x_um": final_position.x_um,
                        "y_um": final_position.y_um,
                        "z_um": final_position.z_um,
                    },
                },
            )
            if not raman_result.ok:
                status = PointStatus.RAMAN_ERROR
                error = raman_result.message

        record = PointRecord(
            point_id=point.point_id,
            status=status,
            planned_x_um=point.x_um,
            planned_y_um=point.y_um,
            planned_z_um=point.z_um,
            predicted_z_um=predicted_z,
            final_position=final_position,
            raman=raman_result,
            started_at=started_at,
            finished_at=time.time(),
            error=error,
        )
        self.recorder.append(record)
        return record
