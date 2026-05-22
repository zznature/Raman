"""
Manual lab runner for one real-camera autofocus test.

Run from the raman directory, after manually placing the sample near focus:

    .\\.venv\\python.exe -m tests.autofocus_lab_manual ^
        --port COM3 ^
        --roi 100 100 300 300 ^
        --z-min-um 1200 ^
        --z-max-um 1240 ^
        --confirm-run

The script connects the real IDS camera path used by microscope/, connects the
real MC.NewtonLT-06 Z controller, runs one AutofocusController pass, and writes
curves/results under captures/.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from autofocus.controller import AutofocusController
from autofocus.exceptions import FrameTimeoutError
from autofocus.models import AutofocusParams, FocusResult, Frame, ROI, ScanCurve
from microscope.camera.driver import CameraDriver
from microscope.config import CAPTURE_DIR
from microscope.utils.image_io import save_tiff
from stage.z_stage import ZStageController


def load_directshow_module():
    root = Path(__file__).resolve().parent.parent
    path = root / "camera-activeX" / "directshow_persistent_capture.py"
    spec = importlib.util.spec_from_file_location("ids_directshow_capture", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load DirectShow helper from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LiveCameraFrameProvider:
    """Synchronous real-camera FrameProvider for CLI autofocus runs."""

    def __init__(self) -> None:
        self.driver = CameraDriver()
        self._last_frame: Frame | None = None
        self._seq = 0
        self._capturing = False

    def connect(self) -> tuple[int, int]:
        self.driver.connect()
        return self.driver.width, self.driver.height

    def start(self) -> None:
        self.driver.start_capture()
        self._capturing = True

    def disconnect(self) -> None:
        if self._capturing:
            self.driver.stop_capture()
            self._capturing = False
        self.driver.disconnect()

    def set_exposure(self, ms: float) -> float:
        return self.driver.set_exposure(ms)

    def get_latest(self) -> Frame:
        if self._last_frame is None:
            raise RuntimeError("No frame has been captured yet.")
        return self._last_frame

    def wait_for_next(self, after_ts: float, timeout_ms: int) -> Frame:
        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            image = self.driver.wait_for_frame()
            self._seq += 1
            frame = Frame(image=image, timestamp=time.monotonic(), seq=self._seq)
            self._last_frame = frame
            if frame.timestamp > after_ts:
                return frame
            if time.monotonic() >= deadline:
                raise FrameTimeoutError(
                    f"No frame newer than {after_ts:.3f}s arrived within {timeout_ms}ms"
                )


class DirectShowStillFrameProvider:
    """FrameProvider backed by one persistent DirectShow graph."""

    def __init__(self, name_contains: str, timeout_ms: int, temp_dir: Path) -> None:
        self.name_contains = name_contains
        self.timeout_ms = timeout_ms
        self.temp_dir = temp_dir
        self._helper = load_directshow_module()
        self._capture = None
        self._last_frame: Frame | None = None
        self._seq = 0

    def connect(self) -> tuple[int, int]:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._capture = self._helper.PersistentDirectShowCapture(
            self.name_contains,
            self.timeout_ms,
        )
        ready = self._capture.start()
        print(f"DirectShow persistent capture: {ready}")
        frame = self.wait_for_next(after_ts=0.0, timeout_ms=self.timeout_ms)
        h, w = frame.image.shape[:2]
        return w, h

    def start(self) -> None:
        return

    def disconnect(self) -> None:
        if self._capture is not None:
            self._capture.close()
            self._capture = None

    def set_exposure(self, ms: float) -> float:
        raise RuntimeError("DirectShow still backend does not expose exposure control yet.")

    def get_latest(self) -> Frame:
        if self._last_frame is None:
            raise RuntimeError("No frame has been captured yet.")
        return self._last_frame

    def wait_for_next(self, after_ts: float, timeout_ms: int) -> Frame:
        from PIL import Image
        import numpy as np

        if self._capture is None:
            raise RuntimeError("DirectShow persistent capture is not connected.")
        self._seq += 1
        output_path = self.temp_dir / f"directshow_frame_{self._seq:06d}.pgm"
        self._capture.grab(output_path)
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise FrameTimeoutError(f"DirectShow capture did not create {output_path}")
        image = np.asarray(Image.open(output_path))
        frame = Frame(image=image, timestamp=time.monotonic(), seq=self._seq)
        self._last_frame = frame
        return frame


class LabSpecFileBridgeFrameProvider:
    """FrameProvider that reads frames exported by a LabSpec-internal VBS bridge."""

    def __init__(self, bridge_dir: Path, pattern: str = "frame_*.tif") -> None:
        self.bridge_dir = bridge_dir
        self.pattern = pattern
        self._last_frame: Frame | None = None
        self._seq = 0
        self._seen_paths: set[Path] = set()

    def connect(self) -> tuple[int, int]:
        self.bridge_dir.mkdir(parents=True, exist_ok=True)
        frame = self.wait_for_next(after_ts=0.0, timeout_ms=10000)
        h, w = frame.image.shape[:2]
        return w, h

    def start(self) -> None:
        return

    def disconnect(self) -> None:
        stop_path = self.bridge_dir / "stop.txt"
        try:
            stop_path.write_text("stop\n", encoding="utf-8")
        except Exception:
            pass

    def set_exposure(self, ms: float) -> float:
        raise RuntimeError("LabSpec file bridge backend does not expose exposure control.")

    def get_latest(self) -> Frame:
        if self._last_frame is None:
            raise RuntimeError("No frame has been captured yet.")
        return self._last_frame

    @staticmethod
    def _is_stable_file(path: Path) -> bool:
        try:
            first_size = path.stat().st_size
            if first_size <= 0:
                return False
            time.sleep(0.02)
            return path.exists() and path.stat().st_size == first_size
        except OSError:
            return False

    def wait_for_next(self, after_ts: float, timeout_ms: int) -> Frame:
        from PIL import Image
        import numpy as np

        deadline = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() <= deadline:
            candidates = sorted(
                (
                    path
                    for path in self.bridge_dir.glob(self.pattern)
                    if path not in self._seen_paths and self._is_stable_file(path)
                ),
                key=lambda path: path.stat().st_mtime,
            )
            if candidates:
                path = candidates[-1]
                image = np.asarray(Image.open(path))
                self._seen_paths.add(path)
                self._seq += 1
                frame = Frame(image=image, timestamp=time.monotonic(), seq=self._seq)
                if frame.timestamp > after_ts:
                    self._last_frame = frame
                    return frame
            time.sleep(0.05)
        raise FrameTimeoutError(
            f"No new LabSpec bridge frame in {self.bridge_dir} within {timeout_ms}ms"
        )


def parse_roi(values: list[int]) -> ROI:
    if len(values) != 4:
        raise argparse.ArgumentTypeError("ROI requires x y width height")
    x, y, width, height = values
    return ROI(x=x, y=y, width=width, height=height)


def curve_to_rows(curve: ScanCurve | None) -> list[dict[str, float | str]]:
    if curve is None:
        return []
    return [
        {
            "phase": curve.phase,
            "z_um": point.z_um,
            "score": point.score,
            "saturation_ratio": point.saturation_ratio,
        }
        for point in curve.points
    ]


def result_to_dict(result: FocusResult) -> dict[str, Any]:
    return {
        "status": result.status.value,
        "z_best_um": result.z_best_um,
        "final_score": result.final_score,
        "confidence": result.confidence,
        "message": result.message,
        "coarse": curve_to_rows(result.coarse),
        "fine": curve_to_rows(result.fine),
    }


def write_curve_csv(path: Path, curve: ScanCurve | None) -> None:
    rows = curve_to_rows(curve)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["phase", "z_um", "score", "saturation_ratio"],
        )
        writer.writeheader()
        writer.writerows(rows)


def wait_for_first_frame(camera: LiveCameraFrameProvider, timeout_ms: int) -> None:
    t0 = time.monotonic()
    camera.wait_for_next(after_ts=t0, timeout_ms=timeout_ms)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one manual lab autofocus test with the real camera and Z stage."
    )
    parser.add_argument("--port", required=True, help="Z-stage serial port, for example COM3.")
    parser.add_argument(
        "--roi",
        nargs=4,
        type=int,
        metavar=("X", "Y", "WIDTH", "HEIGHT"),
        required=True,
        help="Focus ROI in image pixel coordinates.",
    )
    parser.add_argument("--z-min-um", type=float, required=True, help="Absolute safe lower Z limit.")
    parser.add_argument("--z-max-um", type=float, required=True, help="Absolute safe upper Z limit.")
    parser.add_argument("--coarse-range-um", type=float, default=10.0)
    parser.add_argument("--coarse-step-um", type=float, default=2.0)
    parser.add_argument("--fine-range-um", type=float, default=3.0)
    parser.add_argument("--fine-step-um", type=float, default=0.5)
    parser.add_argument("--frames-per-z", type=int, default=3)
    parser.add_argument("--settle-ms", type=int, default=100)
    parser.add_argument("--frame-timeout-ms", type=int, default=1000)
    parser.add_argument("--stage-timeout-ms", type=int, default=3000)
    parser.add_argument(
        "--stage-read-timeout-s",
        type=float,
        default=1.0,
        help="Serial read timeout used when connecting to the Z stage.",
    )
    parser.add_argument(
        "--stage-idn-wait-ms",
        type=float,
        default=100.0,
        help="Wait after writing the Z-stage IDN query before reading the response.",
    )
    parser.add_argument(
        "--stage-cmd-wait-ms",
        type=float,
        default=5.0,
        help="Wait after normal Z-stage query commands before reading responses.",
    )
    parser.add_argument("--backlash-um", type=float, default=3.0)
    parser.add_argument("--min-confidence", type=float, default=0.2)
    parser.add_argument("--coarse-min-prominence", type=float, default=0.2)
    parser.add_argument("--max-saturation-ratio", type=float, default=0.01)
    parser.add_argument("--metric-name", default="tenengrad")
    parser.add_argument(
        "--camera-backend",
        choices=("pyueye", "directshow", "labspec-file"),
        default="pyueye",
        help="Camera backend for lab autofocus.",
    )
    parser.add_argument(
        "--directshow-name-contains",
        default="UI358x",
        help="Friendly-name substring for the DirectShow camera backend.",
    )
    parser.add_argument(
        "--labspec-bridge-dir",
        type=Path,
        default=Path(CAPTURE_DIR) / "labspec_bridge",
        help="Directory where the LabSpec VBS bridge writes frame_*.tif files.",
    )
    parser.add_argument(
        "--labspec-bridge-pattern",
        default="frame_*.tif",
        help="Glob pattern for frames written by the LabSpec VBS bridge.",
    )
    parser.add_argument(
        "--exposure-ms",
        type=float,
        default=None,
        help="Optional fixed camera exposure to set before autofocus.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(CAPTURE_DIR),
        help="Directory for result JSON, curves, and frame snapshots.",
    )
    parser.add_argument(
        "--confirm-run",
        action="store_true",
        help="Required safety acknowledgement. The script will move the real Z stage.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roi = parse_roi(args.roi)
    params = AutofocusParams(
        z_min_um=args.z_min_um,
        z_max_um=args.z_max_um,
        coarse_range_um=args.coarse_range_um,
        coarse_step_um=args.coarse_step_um,
        fine_range_um=args.fine_range_um,
        fine_step_um=args.fine_step_um,
        settle_ms=args.settle_ms,
        frame_timeout_ms=args.frame_timeout_ms,
        stage_timeout_ms=args.stage_timeout_ms,
        frames_per_z=args.frames_per_z,
        backlash_um=args.backlash_um,
        min_confidence=args.min_confidence,
        coarse_min_prominence=args.coarse_min_prominence,
        max_saturation_ratio=args.max_saturation_ratio,
        metric_name=args.metric_name,
    )

    if not args.confirm_run:
        print("Refusing to move hardware without --confirm-run.", file=sys.stderr)
        print(f"Requested ROI: {asdict(roi)}", file=sys.stderr)
        print(f"Requested Z limits: [{params.z_min_um:.3f}, {params.z_max_um:.3f}] um", file=sys.stderr)
        return 2

    run_id = datetime.now().strftime("autofocus_%Y%m%d_%H%M%S")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.camera_backend == "directshow":
        camera = DirectShowStillFrameProvider(
            name_contains=args.directshow_name_contains,
            timeout_ms=args.frame_timeout_ms,
            temp_dir=output_dir / f"{run_id}_directshow_frames",
        )
    elif args.camera_backend == "labspec-file":
        camera = LabSpecFileBridgeFrameProvider(
            bridge_dir=args.labspec_bridge_dir,
            pattern=args.labspec_bridge_pattern,
        )
    else:
        camera = LiveCameraFrameProvider()
    stage = ZStageController(
        port=args.port,
        read_timeout=args.stage_read_timeout_s,
        default_cmd_wait_ms=args.stage_cmd_wait_ms,
        idn_wait_ms=args.stage_idn_wait_ms,
    )
    progress_rows: list[dict[str, float | str]] = []

    try:
        print("Connecting camera...")
        width, height = camera.connect()
        print(f"Camera connected: {width} x {height}")
        if not roi.is_valid((height, width)):
            raise ValueError(f"ROI {roi} is invalid for camera image shape {(height, width)}")

        if args.exposure_ms is not None:
            actual = camera.set_exposure(args.exposure_ms)
            print(f"Exposure set: requested={args.exposure_ms:.3f} ms actual={actual:.3f} ms")

        camera.start()
        wait_for_first_frame(camera, args.frame_timeout_ms)
        before_frame = camera.get_latest()
        before_path = output_dir / f"{run_id}_before.tiff"
        save_tiff(before_frame.image, str(before_path))
        print(f"Saved pre-run frame: {before_path}")

        print("Connecting Z stage...")
        stage.connect()
        z0 = stage.get_position_um()
        print(f"Initial Z: {z0:.3f} um")
        if not (params.z_min_um <= z0 <= params.z_max_um):
            raise ValueError(
                f"Current Z {z0:.3f} um is outside safe limits "
                f"[{params.z_min_um:.3f}, {params.z_max_um:.3f}] um"
            )

        def on_progress(point) -> None:
            row = {
                "phase": "scan",
                "z_um": point.z_um,
                "score": point.score,
                "saturation_ratio": point.saturation_ratio,
            }
            progress_rows.append(row)
            print(
                f"z={point.z_um:.3f} um "
                f"score={point.score:.6g} "
                f"sat={point.saturation_ratio:.4f}"
            )

        print("Running autofocus...")
        controller = AutofocusController(stage=stage, frames=camera)
        result = controller.run_single(roi, params, on_progress=on_progress)

        after_frame = camera.get_latest()
        after_path = output_dir / f"{run_id}_after.tiff"
        save_tiff(after_frame.image, str(after_path))

        result_path = output_dir / f"{run_id}_result.json"
        coarse_path = output_dir / f"{run_id}_coarse.csv"
        fine_path = output_dir / f"{run_id}_fine.csv"
        progress_path = output_dir / f"{run_id}_progress.csv"

        payload = {
            "run_id": run_id,
            "roi": asdict(roi),
            "params": asdict(params),
            "initial_z_um": z0,
            "final_z_um": stage.get_position_um(),
            "before_frame": str(before_path),
            "after_frame": str(after_path),
            "result": result_to_dict(result),
        }
        result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        write_curve_csv(coarse_path, result.coarse)
        write_curve_csv(fine_path, result.fine)
        with progress_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["phase", "z_um", "score", "saturation_ratio"],
            )
            writer.writeheader()
            writer.writerows(progress_rows)

        print(f"Status: {result.status.value}")
        print(f"Best Z: {result.z_best_um}")
        print(f"Final score: {result.final_score}")
        print(f"Confidence: {result.confidence:.3f}")
        if result.message:
            print(f"Message: {result.message}")
        print(f"Saved result JSON: {result_path}")
        print(f"Saved coarse curve: {coarse_path}")
        print(f"Saved fine curve: {fine_path}")
        print(f"Saved post-run frame: {after_path}")
        return 0
    finally:
        try:
            stage.stop()
        except Exception:
            pass
        try:
            stage.disconnect()
        except Exception:
            pass
        try:
            camera.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
