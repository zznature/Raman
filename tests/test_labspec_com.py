"""Tests for LabSpec COM single-spectrum acquisition."""

import pytest

from mapping.labspec import (
    ACQ_AUTO_SHOW,
    ACQ_CANCEL,
    ACQ_DARK,
    ACQ_ICS,
    ACQ_LABSPEC_PARAM,
    ACQ_NO_SPIKE_REMOVING,
    ACQ_SPECTRUM,
    LabSpecAcquisitionConfig,
    LabSpecComRamanAcquirer,
    LabSpecFileBridgeRamanAcquirer,
    LabSpecWorkerAcquisitionConfig,
)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeLabSpec:
    def __init__(self, acq_ids: list[int] | None = None, acq_error: Exception | None = None):
        self.acq_ids = list(acq_ids or [])
        self.acq_error = acq_error
        self.acq_calls: list[tuple[int, float, int, float, float]] = []
        self.get_acq_id_calls = 0

    def Acq(
        self,
        mode: int,
        integration_time_s: float,
        accumulations: int,
        acq_from_nm: float,
        acq_to_nm: float,
    ) -> int:
        self.acq_calls.append(
            (mode, integration_time_s, accumulations, acq_from_nm, acq_to_nm)
        )
        if self.acq_error is not None and mode != ACQ_CANCEL:
            raise self.acq_error
        return 0

    def GetAcqID(self) -> int:
        self.get_acq_id_calls += 1
        if self.acq_ids:
            return self.acq_ids.pop(0)
        return 0


def test_labspec_com_acquires_single_spectrum_with_external_params():
    lab_spec = FakeLabSpec(acq_ids=[0, 0, 42])
    clock = FakeClock()
    config = LabSpecAcquisitionConfig(
        prog_id="LabSpec6.S",
        integration_time_s=1.5,
        accumulations=2,
        acq_from_nm=500.0,
        acq_to_nm=700.0,
    )
    acquirer = LabSpecComRamanAcquirer(
        config,
        com_object=lab_spec,
        clock=clock,
        sleeper=clock.sleep,
    )

    result = acquirer.acquire_point("P0001", {"planned_x_um": 1.0})

    assert result.ok
    assert lab_spec.acq_calls == [(ACQ_SPECTRUM, 1.5, 2, 500.0, 700.0)]
    assert lab_spec.get_acq_id_calls == 3
    assert result.metadata["spectrum_id"] == 42
    assert result.metadata["input_metadata"] == {"planned_x_um": 1.0}


def test_labspec_com_builds_explicit_mode_flags():
    config = LabSpecAcquisitionConfig(
        prog_id="LabSpec6.S",
        integration_time_s=1.0,
        auto_show=True,
        spike_removing="none",
        ics="enable",
        dark="enable",
    )

    assert config.effective_mode() == (
        ACQ_SPECTRUM + ACQ_AUTO_SHOW + ACQ_NO_SPIKE_REMOVING + ACQ_ICS + ACQ_DARK
    )


def test_labspec_com_ignores_acq_return_value_and_waits_for_get_acq_id():
    lab_spec = FakeLabSpec(acq_ids=[17])
    config = LabSpecAcquisitionConfig(prog_id="LabSpec6.S", integration_time_s=1.0)
    acquirer = LabSpecComRamanAcquirer(config, com_object=lab_spec)

    result = acquirer.acquire_point("P0001", {})

    assert result.ok
    assert result.metadata["spectrum_id"] == 17


def test_labspec_com_timeout_cancels_current_acquisition():
    lab_spec = FakeLabSpec(acq_ids=[0, 0, 0, 0])
    clock = FakeClock()
    config = LabSpecAcquisitionConfig(
        prog_id="LabSpec6.S",
        integration_time_s=1.0,
        poll_interval_s=0.5,
        timeout_s=1.0,
    )
    acquirer = LabSpecComRamanAcquirer(
        config,
        com_object=lab_spec,
        clock=clock,
        sleeper=clock.sleep,
    )

    result = acquirer.acquire_point("P0001", {})

    assert not result.ok
    assert "timed out" in result.message
    assert lab_spec.acq_calls[-1] == (ACQ_CANCEL, 0, 0, 0, 0)
    assert result.metadata["cancel_attempted"] is True
    assert result.metadata["cancel_error"] == ""


def test_labspec_com_records_acq_failure():
    lab_spec = FakeLabSpec(acq_error=RuntimeError("COM call failed"))
    config = LabSpecAcquisitionConfig(prog_id="LabSpec6.S", integration_time_s=1.0)
    acquirer = LabSpecComRamanAcquirer(config, com_object=lab_spec)

    result = acquirer.acquire_point("P0001", {})

    assert not result.ok
    assert result.metadata["error_stage"] == "acq_failed"
    assert "COM call failed" in result.message


def test_labspec_config_rejects_labspec_ui_param_mode():
    with pytest.raises(ValueError, match="Only ACQ_SPECTRUM"):
        LabSpecAcquisitionConfig(
            prog_id="LabSpec6.S",
            integration_time_s=1.0,
            base_mode=ACQ_LABSPEC_PARAM,
        )


def test_labspec_config_rejects_autoexposure():
    with pytest.raises(ValueError, match="autoexposure"):
        LabSpecAcquisitionConfig(prog_id="LabSpec6.S", integration_time_s=0)


def test_labspec_worker_bridge_reads_result_and_writes_request(tmp_path):
    bridge_dir = tmp_path / "bridge"
    config = LabSpecWorkerAcquisitionConfig(
        bridge_dir=bridge_dir,
        integration_time_s=1.0,
        accumulations=1,
        acq_from_nm=500.0,
        acq_to_nm=700.0,
        save_path=bridge_dir / "spectrum.txt",
        timeout_s=1.0,
        poll_interval_s=0.1,
    )
    acquirer = LabSpecFileBridgeRamanAcquirer(config, clock=lambda: 0.0, sleeper=lambda _: None)

    request_path = bridge_dir / "spectrum_request.ini"
    result_path = bridge_dir / "spectrum_result.ini"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        "status=ok\nrequest_id=abc123\nspectrum_id=77\nsave_path=D:\\out\\spectrum.txt\n",
        encoding="utf-8",
    )

    from unittest.mock import patch

    with patch("mapping.labspec.uuid.uuid4", return_value=type("U", (), {"hex": "abc123"})()):
        result = acquirer.acquire_point("P0001", {"planned_x_um": 1.0})

    assert result.ok
    assert result.output_path == "D:\\out\\spectrum.txt"
    assert request_path.exists() is False


def test_labspec_worker_bridge_times_out_and_clears_request(tmp_path):
    bridge_dir = tmp_path / "bridge"
    config = LabSpecWorkerAcquisitionConfig(
        bridge_dir=bridge_dir,
        integration_time_s=1.0,
        timeout_s=0.2,
        poll_interval_s=0.1,
    )
    clock = FakeClock()
    acquirer = LabSpecFileBridgeRamanAcquirer(config, clock=clock, sleeper=clock.sleep)

    result = acquirer.acquire_point("P0001", {})

    assert not result.ok
    assert "timed out" in result.message
    assert not (bridge_dir / "spectrum_request.ini").exists()
