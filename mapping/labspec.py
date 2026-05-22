"""Raman acquisition protocols, offline fakes, and LabSpec acquisition adapters."""

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from mapping.models import AcquisitionResult

ACQ_SPECTRUM = 0
ACQ_IMAGE = 1
ACQ_LABSPEC_PARAM = 2
ACQ_SPECTRAL_IMAGE = 3
ACQ_GET_TEMPERATURE = 4
ACQ_SPECTRUM_RTD = 5
ACQ_SET_PMT_PARAMETER = 6
ACQ_MACRO_SPOT = 7
ACQ_CANCEL = 8
ACQ_PMT_CCD = 9

ACQ_AUTO_SHOW = 10
ACQ_LABSPEC_SPIKE_REMOVING = 0
ACQ_NO_SPIKE_REMOVING = 100
ACQ_SINGLE_SPIKE_REMOVING = 200
ACQ_DOUBLE_SPIKE_REMOVING = 300
ACQ_DOUBLE_AUTOADD_SPIKE_REMOVING = 400
ACQ_NO_ICS = 100000
ACQ_ICS = 200000
ACQ_NO_DARK = 1000000
ACQ_DARK = 2000000

_SPIKE_FLAGS = {
    "labspec_default": ACQ_LABSPEC_SPIKE_REMOVING,
    "none": ACQ_NO_SPIKE_REMOVING,
    "single": ACQ_SINGLE_SPIKE_REMOVING,
    "double": ACQ_DOUBLE_SPIKE_REMOVING,
    "double_autoadd": ACQ_DOUBLE_AUTOADD_SPIKE_REMOVING,
}
_ICS_FLAGS = {
    "unchanged": 0,
    "enable": ACQ_ICS,
    "disable": ACQ_NO_ICS,
}
_DARK_FLAGS = {
    "unchanged": 0,
    "enable": ACQ_DARK,
    "disable": ACQ_NO_DARK,
}


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


@dataclass(frozen=True)
class LabSpecAcquisitionConfig:
    """External parameters for one LabSpec spectrum acquisition."""

    prog_id: str
    integration_time_s: float
    accumulations: int = 1
    acq_from_nm: float = 0.0
    acq_to_nm: float = 0.0
    base_mode: int = ACQ_SPECTRUM
    auto_show: bool = False
    spike_removing: str = "labspec_default"
    ics: str = "unchanged"
    dark: str = "unchanged"
    poll_interval_s: float = 0.2
    timeout_s: float | None = None

    def __post_init__(self) -> None:
        if not self.prog_id.strip():
            raise ValueError("LabSpec prog_id is required.")
        if self.base_mode != ACQ_SPECTRUM:
            raise ValueError("Only ACQ_SPECTRUM single-spectrum acquisition is supported.")
        if self.integration_time_s <= 0:
            raise ValueError("integration_time_s must be > 0; autoexposure is not supported.")
        if self.accumulations <= 0:
            raise ValueError("accumulations must be > 0.")
        if self.poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be > 0.")
        if self.timeout_s is not None and self.timeout_s <= 0:
            raise ValueError("timeout_s must be > 0 when provided.")
        if self.spike_removing not in _SPIKE_FLAGS:
            raise ValueError(f"Unsupported spike_removing mode: {self.spike_removing}")
        if self.ics not in _ICS_FLAGS:
            raise ValueError(f"Unsupported ics mode: {self.ics}")
        if self.dark not in _DARK_FLAGS:
            raise ValueError(f"Unsupported dark mode: {self.dark}")

    @property
    def effective_timeout_s(self) -> float:
        if self.timeout_s is not None:
            return self.timeout_s
        return self.integration_time_s * self.accumulations + 10.0

    def effective_mode(self) -> int:
        mode = self.base_mode
        if self.auto_show:
            mode += ACQ_AUTO_SHOW
        mode += _SPIKE_FLAGS[self.spike_removing]
        mode += _ICS_FLAGS[self.ics]
        mode += _DARK_FLAGS[self.dark]
        return mode

    def to_metadata(self) -> dict[str, Any]:
        return {
            "prog_id": self.prog_id,
            "integration_time_s": self.integration_time_s,
            "accumulations": self.accumulations,
            "acq_from_nm": self.acq_from_nm,
            "acq_to_nm": self.acq_to_nm,
            "effective_mode": self.effective_mode(),
            "auto_show": self.auto_show,
            "spike_removing": self.spike_removing,
            "ics": self.ics,
            "dark": self.dark,
            "poll_interval_s": self.poll_interval_s,
            "timeout_s": self.effective_timeout_s,
        }


@dataclass(frozen=True)
class LabSpecWorkerAcquisitionConfig:
    """Parameters for the LabSpec-internal VBS worker file bridge."""

    bridge_dir: Path | str
    integration_time_s: float
    accumulations: int = 1
    acq_from_nm: float = 0.0
    acq_to_nm: float = 0.0
    auto_show: bool = True
    save_path: Path | str | None = None
    save_format: str = "txt"
    poll_interval_s: float = 0.2
    timeout_s: float | None = None
    request_filename: str = "spectrum_request.ini"
    result_filename: str = "spectrum_result.ini"

    def __post_init__(self) -> None:
        if self.integration_time_s <= 0:
            raise ValueError("integration_time_s must be > 0.")
        if self.accumulations <= 0:
            raise ValueError("accumulations must be > 0.")
        if self.poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be > 0.")
        if self.timeout_s is not None and self.timeout_s <= 0:
            raise ValueError("timeout_s must be > 0 when provided.")
        if not self.request_filename.strip():
            raise ValueError("request_filename is required.")
        if not self.result_filename.strip():
            raise ValueError("result_filename is required.")
        if not self.save_format.strip():
            raise ValueError("save_format is required.")

    @property
    def bridge_path(self) -> Path:
        return Path(self.bridge_dir)

    @property
    def effective_timeout_s(self) -> float:
        if self.timeout_s is not None:
            return self.timeout_s
        return self.integration_time_s * self.accumulations + 10.0

    def to_metadata(self) -> dict[str, Any]:
        return {
            "bridge_dir": str(self.bridge_path),
            "integration_time_s": self.integration_time_s,
            "accumulations": self.accumulations,
            "acq_from_nm": self.acq_from_nm,
            "acq_to_nm": self.acq_to_nm,
            "auto_show": self.auto_show,
            "save_path": str(Path(self.save_path).resolve()) if self.save_path else "",
            "save_format": self.save_format,
            "poll_interval_s": self.poll_interval_s,
            "timeout_s": self.effective_timeout_s,
            "request_filename": self.request_filename,
            "result_filename": self.result_filename,
        }


class LabSpecComRamanAcquirer:
    """LabSpec6 ActiveX/COM adapter for externally configured single spectra."""

    def __init__(
        self,
        config: LabSpecAcquisitionConfig,
        *,
        com_object: Any | None = None,
        com_factory: Callable[[str], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.config = config
        self._com_object = com_object
        self._com_factory = com_factory
        self._owns_com_object = com_object is None
        self._clock = clock
        self._sleeper = sleeper

    def acquire_point(self, point_id: str, metadata: dict) -> AcquisitionResult:
        started_at = time.time()
        acquisition_metadata = {
            **self.config.to_metadata(),
            "point_id": point_id,
            "input_metadata": dict(metadata),
            "started_at": started_at,
        }

        try:
            lab_spec = self._get_com_object()
        except Exception as exc:  # noqa: BLE001 - hardware adapter returns structured failure
            return self._failed("dispatch_failed", exc, acquisition_metadata, started_at)

        try:
            lab_spec.Acq(
                self.config.effective_mode(),
                self.config.integration_time_s,
                self.config.accumulations,
                self.config.acq_from_nm,
                self.config.acq_to_nm,
            )
        except Exception as exc:  # noqa: BLE001 - COM exceptions depend on LabSpec install
            self._release_com_object()
            return self._failed("acq_failed", exc, acquisition_metadata, started_at)

        deadline = self._clock() + self.config.effective_timeout_s
        try:
            while self._clock() <= deadline:
                spectrum_id = int(lab_spec.GetAcqID())
                if spectrum_id > 0:
                    finished_at = time.time()
                    acquisition_metadata.update(
                        {
                            "spectrum_id": spectrum_id,
                            "finished_at": finished_at,
                            "duration_s": finished_at - started_at,
                        }
                    )
                    self._release_com_object()
                    return AcquisitionResult(status="ok", metadata=acquisition_metadata)
                self._sleeper(self.config.poll_interval_s)
        except Exception as exc:  # noqa: BLE001 - polling failures must be recorded
            self._release_com_object()
            return self._failed("poll_failed", exc, acquisition_metadata, started_at)

        cancel_error = self._cancel(lab_spec)
        self._release_com_object()
        finished_at = time.time()
        acquisition_metadata.update(
            {
                "finished_at": finished_at,
                "duration_s": finished_at - started_at,
                "cancel_attempted": True,
                "cancel_error": cancel_error,
            }
        )
        return AcquisitionResult(
            status="failed",
            message=(
                f"LabSpec acquisition timed out after "
                f"{self.config.effective_timeout_s:.3f}s for {point_id}"
            ),
            metadata=acquisition_metadata,
        )

    def _get_com_object(self) -> Any:
        if self._com_object is not None:
            return self._com_object
        if self._com_factory is not None:
            self._com_object = self._com_factory(self.config.prog_id)
            return self._com_object

        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:  # pragma: no cover - depends on Windows lab host
            raise RuntimeError("pywin32 is required for LabSpec COM acquisition.") from exc

        pythoncom.CoInitialize()
        self._com_object = win32com.client.Dispatch(self.config.prog_id)
        return self._com_object

    def _release_com_object(self) -> None:
        if not self._owns_com_object:
            return
        self._com_object = None
        try:
            import pythoncom
        except ImportError:  # pragma: no cover - depends on Windows lab host
            return
        try:
            pythoncom.CoUninitialize()
        except Exception:
            return

    def _cancel(self, lab_spec: Any) -> str:
        try:
            lab_spec.Acq(ACQ_CANCEL, 0, 0, 0, 0)
        except Exception as exc:  # noqa: BLE001 - preserve cancel failure in metadata
            return str(exc)
        return ""

    @staticmethod
    def _failed(
        stage: str,
        exc: Exception,
        metadata: dict[str, Any],
        started_at: float,
    ) -> AcquisitionResult:
        finished_at = time.time()
        result_metadata = {
            **metadata,
            "error_stage": stage,
            "finished_at": finished_at,
            "duration_s": finished_at - started_at,
        }
        return AcquisitionResult(
            status="failed",
            message=f"LabSpec acquisition {stage}: {exc}",
            metadata=result_metadata,
        )


class LabSpecFileBridgeRamanAcquirer:
    """LabSpec-internal VBS worker bridge for one externally configured spectrum."""

    def __init__(
        self,
        config: LabSpecWorkerAcquisitionConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.config = config
        self._clock = clock
        self._sleeper = sleeper

    def acquire_point(self, point_id: str, metadata: dict) -> AcquisitionResult:
        bridge_dir = self.config.bridge_path
        request_path = bridge_dir / self.config.request_filename
        result_path = bridge_dir / self.config.result_filename
        started_at = time.time()
        acquisition_metadata = {
            **self.config.to_metadata(),
            "point_id": point_id,
            "request_id": "",
            "input_metadata": dict(metadata),
            "started_at": started_at,
            "request_path": str(request_path),
            "result_path": str(result_path),
        }

        try:
            bridge_dir.mkdir(parents=True, exist_ok=True)
            if request_path.exists():
                return self._failed(
                    "request_pending",
                    RuntimeError(f"Pending request already exists: {request_path}"),
                    acquisition_metadata,
                    started_at,
                )
            if result_path.exists():
                result_path.unlink()
        except Exception as exc:  # noqa: BLE001 - filesystem bridge returns structured failure
            return self._failed("bridge_setup_failed", exc, acquisition_metadata, started_at)

        request_id = uuid.uuid4().hex
        acquisition_metadata["request_id"] = request_id

        request_lines = [
            ("request_id", request_id),
            ("point_id", point_id),
            ("integration_time_s", f"{self.config.integration_time_s:g}"),
            ("accumulations", str(self.config.accumulations)),
            ("from_nm", f"{self.config.acq_from_nm:g}"),
            ("to_nm", f"{self.config.acq_to_nm:g}"),
            ("auto_show", "1" if self.config.auto_show else "0"),
            (
                "save_path",
                str(Path(self.config.save_path).resolve()) if self.config.save_path else "",
            ),
            ("save_format", self.config.save_format),
        ]

        try:
            self._write_key_value_file(request_path, request_lines)
        except Exception as exc:  # noqa: BLE001 - filesystem bridge returns structured failure
            return self._failed("request_write_failed", exc, acquisition_metadata, started_at)

        deadline = self._clock() + self.config.effective_timeout_s
        try:
            while self._clock() <= deadline:
                if result_path.exists():
                    result = self._read_key_value_file(result_path)
                    if result.get("request_id") == request_id:
                        acquisition_metadata.update(
                            {
                                "finished_at": time.time(),
                                "duration_s": time.time() - started_at,
                                "worker_result": dict(result),
                            }
                        )
                        status = result.get("status", "error").strip().lower()
                        if status == "ok":
                            output_path = result.get("save_path") or None
                            self._safe_delete(request_path)
                            return AcquisitionResult(
                                status="ok",
                                output_path=output_path,
                                metadata=acquisition_metadata,
                            )
                        message = result.get("message", "LabSpec worker reported an error")
                        acquisition_metadata.update(
                            {
                                "error_stage": result.get("step", "worker_error"),
                            }
                        )
                        self._safe_delete(request_path)
                        return AcquisitionResult(
                            status="failed",
                            message=message,
                            metadata=acquisition_metadata,
                        )
                self._sleeper(self.config.poll_interval_s)
        except Exception as exc:  # noqa: BLE001 - bridge polling failures must be recorded
            self._safe_delete(request_path)
            return self._failed("poll_failed", exc, acquisition_metadata, started_at)

        self._safe_delete(request_path)
        finished_at = time.time()
        acquisition_metadata.update(
            {
                "finished_at": finished_at,
                "duration_s": finished_at - started_at,
                "cancel_attempted": False,
            }
        )
        return AcquisitionResult(
            status="failed",
            message=(
                f"LabSpec worker acquisition timed out after "
                f"{self.config.effective_timeout_s:.3f}s for {point_id}"
            ),
            metadata=acquisition_metadata,
        )

    @staticmethod
    def _write_key_value_file(path: Path, items: list[tuple[str, str]]) -> None:
        temp_path = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
        body = "".join(f"{key}={value}\n" for key, value in items)
        temp_path.write_text(body, encoding="utf-8")
        temp_path.replace(path)

    @staticmethod
    def _read_key_value_file(path: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            result[key.strip()] = value.strip()
        return result

    @staticmethod
    def _safe_delete(path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except Exception:
            return

    @staticmethod
    def _failed(
        stage: str,
        exc: Exception,
        metadata: dict[str, Any],
        started_at: float,
    ) -> AcquisitionResult:
        finished_at = time.time()
        result_metadata = {
            **metadata,
            "error_stage": stage,
            "finished_at": finished_at,
            "duration_s": finished_at - started_at,
        }
        return AcquisitionResult(
            status="failed",
            message=f"LabSpec worker acquisition {stage}: {exc}",
            metadata=result_metadata,
        )
