"""Raman acquisition protocols and offline fakes."""

from pathlib import Path
from typing import Protocol

from mapping.models import AcquisitionResult


class RamanAcquirer(Protocol):
    """Interface for triggering one Raman acquisition."""

    def acquire_point(self, point_id: str, metadata: dict) -> AcquisitionResult:
        """Acquire one Raman spectrum for a mapping point."""
        ...


class FakeRamanAcquirer:
    """Offline Raman acquirer that records calls and optionally writes marker files."""

    def __init__(
        self,
        output_dir: Path | str | None = None,
        fail_point_ids: set[str] | None = None,
    ):
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.fail_point_ids = fail_point_ids or set()
        self.calls: list[tuple[str, dict]] = []

    def acquire_point(self, point_id: str, metadata: dict) -> AcquisitionResult:
        self.calls.append((point_id, dict(metadata)))
        if point_id in self.fail_point_ids:
            return AcquisitionResult(
                status="failed",
                message=f"Fake Raman acquisition failed for {point_id}",
            )

        output_path = None
        if self.output_dir is not None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / f"{point_id}.txt"
            path.write_text(f"fake spectrum for {point_id}\n", encoding="utf-8")
            output_path = str(path)
        return AcquisitionResult(status="ok", output_path=output_path)
