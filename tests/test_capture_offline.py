"""Offline autofocus exercise driven by a single real capture TIFF.

Two scenarios:

1. Per-metric scan over a centered ROI of the real frame, increasing Gaussian
   blur to simulate defocus — the resulting "score vs blur" curve must be
   monotonically decreasing, which proves each metric reacts to focus loss.
2. Synthetic z-stack: the sharp frame is the original capture; off-focus
   frames are produced by a separable Gaussian blur whose sigma grows with
   |z - z_peak|. Drop this stack into a `FrameProvider` and run the full
   `AutofocusController.run_single` pipeline.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autofocus.controller import AutofocusController
from autofocus.metrics import METRICS, MetricStrategy
from autofocus.models import AutofocusParams, Frame, ROI
from autofocus.roi import gaussian_blur, to_grayscale
from tests.fakes import FakeZStage


CAPTURE = ROOT / "captures" / "capture_20260513_145336_184742.tiff"


def load_capture() -> np.ndarray:
    return np.asarray(Image.open(CAPTURE))


def _separable_gaussian(image: np.ndarray, sigma: float) -> np.ndarray:
    """Apply a separable Gaussian blur with the given sigma using a fresh kernel each call."""
    if sigma <= 1e-3:
        return image.astype(np.float32)
    radius = max(1, int(round(3.0 * sigma)))
    xs = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-0.5 * (xs / sigma) ** 2)
    kernel /= kernel.sum()
    img = image.astype(np.float32)
    padded = np.pad(img, ((0, 0), (radius, radius)), mode="edge")
    out = np.zeros_like(img)
    for k, w in enumerate(kernel):
        out += w * padded[:, k : k + img.shape[1]]
    padded = np.pad(out, ((radius, radius), (0, 0)), mode="edge")
    out = np.zeros_like(img)
    for k, w in enumerate(kernel):
        out += w * padded[k : k + img.shape[0], :]
    return out


def center_roi(image_shape: tuple[int, ...], size: int = 512) -> ROI:
    h, w = image_shape[:2]
    s = min(size, h, w)
    return ROI(x=(w - s) // 2, y=(h - s) // 2, width=s, height=s)


def scenario1_blur_response(image: np.ndarray, roi: ROI) -> dict[str, list[float]]:
    """Simulate focus loss with growing Gaussian blur and record each metric's response."""
    sigmas = [0.0, 0.5, 1.0, 2.0, 4.0, 8.0]
    results: dict[str, list[float]] = {name: [] for name in METRICS}
    print(f"\n--- Scenario 1: blur sweep on real capture, ROI={roi} ---")
    print(f"{'sigma_px':>10} | " + " | ".join(f"{name:>20}" for name in METRICS))
    for sigma in sigmas:
        blurred = _separable_gaussian(image, sigma)
        row = []
        for name, fn in METRICS.items():
            score = float(fn(blurred, roi))
            results[name].append(score)
            row.append(f"{score:>20.4f}")
        print(f"{sigma:>10.2f} | " + " | ".join(row))
    return results


def report_monotonic(curves: dict[str, list[float]]) -> None:
    print("\nMonotonic-decrease check (sharper -> higher score expected):")
    for name, scores in curves.items():
        first, last = scores[0], scores[-1]
        ratio = last / first if first > 0 else float("nan")
        ok = all(scores[i] >= scores[i + 1] - 1e-6 * scores[0] for i in range(len(scores) - 1))
        flag = "OK   " if ok else "FAIL "
        print(f"  {flag} {name:>20}: sharp={first:.4f}, blur8={last:.4f}, ratio={ratio:.4f}")


class ZStackBlurProvider:
    """Provide frames whose blur grows with |stage.z - peak_z|, on top of the real capture."""

    def __init__(
        self,
        stage: FakeZStage,
        base_image: np.ndarray,
        peak_z_um: float,
        depth_of_field_um: float = 4.0,
    ):
        self.stage = stage
        self.base = base_image
        self.peak_z_um = peak_z_um
        self.dof = depth_of_field_um
        self._seq = 0
        self._cache: dict[float, np.ndarray] = {}

    def _frame_for(self, z: float) -> np.ndarray:
        sigma = abs(z - self.peak_z_um) / self.dof
        key = round(sigma, 4)
        if key in self._cache:
            return self._cache[key]
        rendered = _separable_gaussian(self.base, sigma)
        rendered = np.clip(rendered, 0, 255).astype(np.uint8)
        self._cache[key] = rendered
        return rendered

    def _make_frame(self) -> Frame:
        self._seq += 1
        image = self._frame_for(self.stage.z)
        return Frame(image=image, timestamp=time.monotonic(), seq=self._seq)

    def get_latest(self) -> Frame:
        return self._make_frame()

    def wait_for_next(self, after_ts: float, timeout_ms: int) -> Frame:
        frame = self._make_frame()
        if frame.timestamp <= after_ts:
            time.sleep(0.001)
            frame = self._make_frame()
        return frame


def scenario2_full_autofocus(image: np.ndarray, roi: ROI) -> None:
    """Run AutofocusController over a synthetic blur-vs-z stack of the real capture, per metric."""
    peak_z = 12.5
    z0 = -25.0
    print(
        f"\n--- Scenario 2: end-to-end AutofocusController (peak={peak_z} um, "
        f"z0={z0} um, dof_proxy=4 um) ---"
    )
    print(f"{'metric':>20} | {'status':>14} | {'z_best_um':>10} | {'err_um':>8} | "
          f"{'final_score':>12} | {'confidence':>10}")
    for metric_name in METRICS:
        stage = FakeZStage(initial_z_um=z0)
        provider = ZStackBlurProvider(stage, image, peak_z_um=peak_z, depth_of_field_um=4.0)
        controller = AutofocusController(stage, provider, MetricStrategy(metric_name))
        params = AutofocusParams(
            z_min_um=-100.0,
            z_max_um=100.0,
            coarse_range_um=80.0,
            coarse_step_um=10.0,
            fine_range_um=15.0,
            fine_step_um=2.0,
            settle_ms=0,
            frame_timeout_ms=200,
            stage_timeout_ms=200,
            frames_per_z=1,
            metric_name=metric_name,
        )
        result = controller.run_single(roi, params)
        z_best = result.z_best_um
        err = (z_best - peak_z) if z_best is not None else float("nan")
        z_best_str = f"{z_best:>10.3f}" if z_best is not None else f"{'-':>10}"
        score_str = (
            f"{result.final_score:>12.4f}" if result.final_score is not None else f"{'-':>12}"
        )
        print(
            f"{metric_name:>20} | {result.status.value:>14} | {z_best_str} | "
            f"{err:>8.3f} | {score_str} | {result.confidence:>10.3f}"
        )
        if result.message:
            print(f"  msg: {result.message}")


def main() -> None:
    print(f"loading {CAPTURE.name}")
    image = load_capture()
    gray = to_grayscale(image)
    print(
        f"  shape={image.shape}, dtype={image.dtype}, range=({image.min()}, {image.max()}), "
        f"mean={float(image.mean()):.2f}"
    )

    roi = center_roi(gray.shape, size=512)
    curves = scenario1_blur_response(gray, roi)
    report_monotonic(curves)

    scenario2_full_autofocus(gray, roi)


if __name__ == "__main__":
    main()
