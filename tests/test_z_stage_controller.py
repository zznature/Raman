"""Tests for the MC.NewtonLT-06 serial controller safety checks."""

import pytest

from stage.exceptions import StageConnectionError
from stage.z_stage import ZStageController


class FakeSerial:
    """Minimal serial port fake for ZStageController.connect()."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.writes: list[str] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(data.decode("ascii"))

    def read_all(self) -> bytes:
        if not self._responses:
            return b""
        return self._responses.pop(0).encode("ascii")

    def close(self) -> None:
        self.closed = True


def test_connect_rejects_non_newton_idn(monkeypatch):
    fake = FakeSerial(["[Arduino Uno]"])

    monkeypatch.setattr("stage.z_stage.serial.Serial", lambda **kwargs: fake)

    controller = ZStageController("COM_TEST")
    with pytest.raises(StageConnectionError):
        controller.connect()

    assert fake.closed is True
    assert fake.writes == ["[*IDN?]"]
