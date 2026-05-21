"""Fake hardware implementations for offline autofocus testing."""

import re
import time
from pathlib import Path
from typing import Optional

import numpy as np

from autofocus.models import Frame


class FakeZStage:
    """In-memory ZStage that records every commanded position."""

    def __init__(self, initial_z_um: float = 0.0, settle_delay_s: float = 0.0):
        self.z = float(initial_z_um)
        self.settle_delay_s = settle_delay_s
        self.history: list[float] = [self.z]

    def get_position_um(self) -> float:
        return self.z

    def move_absolute_um(self, z_um: float) -> None:
        self.z = float(z_um)
        self.history.append(self.z)
        if self.settle_delay_s > 0:
            time.sleep(self.settle_delay_s)

    def move_relative_um(self, dz_um: float) -> None:
        self.move_absolute_um(self.z + dz_um)

    def wait_settled(self, timeout_ms: int) -> None:
        return

    def stop(self) -> None:
        return


class SyntheticFrameProvider:
    """Generates frames whose Tenengrad sharpness peaks at a configurable Z."""

    def __init__(
        self,
        stage: FakeZStage,
        peak_z_um: float = 0.0,
        sigma_um: float = 8.0,
        image_shape: tuple[int, int] = (200, 200),
        noise_level: float = 0.05,
        seed: int = 42,
    ):
        self.stage = stage
        self.peak_z_um = peak_z_um
        self.sigma_um = sigma_um
        self.image_shape = image_shape
        self.noise_level = noise_level
        self._seed = seed
        self._seq = 0
        self._base = self._build_base(image_shape)
        self._mean = float(self._base.mean())

    @staticmethod
    def _build_base(shape: tuple[int, int]) -> np.ndarray:
        h, w = shape
        base = np.zeros(shape, dtype=np.float32)
        rects = [
            (int(h * 0.1), int(h * 0.3), int(w * 0.1), int(w * 0.4)),
            (int(h * 0.5), int(h * 0.7), int(w * 0.2), int(w * 0.5)),
            (int(h * 0.2), int(h * 0.5), int(w * 0.6), int(w * 0.8)),
            (int(h * 0.7), int(h * 0.9), int(w * 0.55), int(w * 0.95)),
        ]
        for y0, y1, x0, x1 in rects:
            base[y0:y1, x0:x1] = 200.0
        return base

    def _make_frame(self) -> Frame:
        self._seq += 1
        sharpness = float(
            np.exp(-((self.stage.z - self.peak_z_um) ** 2) / (2 * self.sigma_um ** 2))
        )
        out = sharpness * self._base + (1.0 - sharpness) * self._mean
        rng = np.random.default_rng(self._seed + self._seq)
        out = out + rng.standard_normal(self.image_shape) * 255.0 * self.noise_level
        image = np.clip(out, 0.0, 255.0).astype(np.uint8)
        ts = time.monotonic()
        return Frame(image=image, timestamp=ts, seq=self._seq)

    def get_latest(self) -> Frame:
        return self._make_frame()

    def wait_for_next(self, after_ts: float, timeout_ms: int) -> Frame:
        frame = self._make_frame()
        if frame.timestamp <= after_ts:
            time.sleep(0.001)
            frame = self._make_frame()
        return frame


class ZStackFrameProvider:
    """Returns the closest pre-captured z-stack image to the stage's current Z."""

    _PATTERN = re.compile(r"z_(-?\d+(?:\.\d+)?)")

    def __init__(self, stage: FakeZStage, stack_dir: Path | str):
        self.stage = stage
        self.stack_dir = Path(stack_dir)
        self._index = self._scan(self.stack_dir)
        self._zs_sorted = sorted(self._index.keys())
        self._cache: dict[float, np.ndarray] = {}
        self._seq = 0

    @classmethod
    def _scan(cls, stack_dir: Path) -> dict[float, Path]:
        index: dict[float, Path] = {}
        for path in stack_dir.iterdir():
            if path.suffix.lower() not in (".tif", ".tiff", ".png"):
                continue
            match = cls._PATTERN.search(path.stem)
            if match:
                index[float(match.group(1))] = path
        return index

    def _closest_z(self) -> float:
        if not self._zs_sorted:
            raise RuntimeError(f"No z-stack images found in {self.stack_dir}")
        cur = self.stage.z
        return min(self._zs_sorted, key=lambda z: abs(z - cur))

    def _load(self, z: float) -> np.ndarray:
        if z in self._cache:
            return self._cache[z]
        path = self._index[z]
        if path.suffix.lower() in (".tif", ".tiff"):
            import tifffile
            img = tifffile.imread(str(path))
        else:
            from PIL import Image
            img = np.asarray(Image.open(path))
        self._cache[z] = img
        return img

    def _make_frame(self) -> Frame:
        self._seq += 1
        z = self._closest_z()
        image = self._load(z)
        return Frame(image=image, timestamp=time.monotonic(), seq=self._seq)

    def get_latest(self) -> Frame:
        return self._make_frame()

    def wait_for_next(self, after_ts: float, timeout_ms: int) -> Frame:
        frame = self._make_frame()
        if frame.timestamp <= after_ts:
            time.sleep(0.001)
            frame = self._make_frame()
        return frame
