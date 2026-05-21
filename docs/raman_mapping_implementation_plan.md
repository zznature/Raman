# Raman mapping implementation plan

This document summarizes the current motion-control, autofocus, and position-calibration code, then proposes an implementation plan for automated Raman mapping.

## Goals

The mapping workflow should move a sample through a planned XY grid, keep the optical focus reliable, correct image-observed XY drift, and coordinate each Raman acquisition with LabSpec6. The orchestration layer should depend on small interfaces instead of camera SDKs, serial commands, or LabSpec internals directly.

The target loop is:

```text
prepare run
  -> validate hardware and limits
  -> choose ROI and mapping grid
  -> collect focus and calibration anchors
  -> fit focus plane
  -> load or create pixel/stage transform

for each mapping point
  -> move XY to planned point
  -> predict Z from focus plane
  -> optionally run local autofocus
  -> capture microscope reference/current frame
  -> estimate XY drift and apply correction
  -> optionally verify residual drift
  -> trigger LabSpec6 Raman acquisition
  -> persist point record, images, focus result, correction, and errors
```

## Current State

### Motion Control

Implemented:

- `stage.models.ZStage` defines the Z-only protocol: read position, absolute move, relative move, wait, stop.
- `stage.models.XYZStage` defines the planned three-axis interface used by mapping and calibration.
- `stage.z_stage.ZStageController` controls the MC.NewtonLT-06 Z axis over serial.
- `stage.memory_stage.MemoryXYZStage` provides an offline XYZ implementation for tests and workflow simulation.

Missing:

- Real XY or XYZ stage adapter.
- Persistent motion limits and per-axis safety configuration.
- A shared motion log with commanded target, measured position, settle time, timeout, and operator abort state.
- Hardware-loop tests for backlash, repeatability, and settle thresholds.

### Autofocus

Implemented:

- `autofocus.models.FrameProvider`, `ZStage`, `FocusStrategy`, `AutofocusParams`, `FocusResult`.
- `autofocus.metrics` sharpness metrics: Tenengrad, Laplacian variance, Brenner, normalized variance.
- `autofocus.scanner.ZScanner` coarse/fine Z scanning, median score per Z, backlash-aware scan direction, parabolic peak interpolation.
- `autofocus.controller.AutofocusController.run_single` with status output and confidence checks.
- Offline tests using synthetic and saved-frame providers.

Important behavior:

- Autofocus is single-point and ROI-based.
- It is hardware-decoupled and can run against any `FrameProvider` and `ZStage`.
- The output is a result object, not an exception-driven success path.

Missing:

- Mapping-level focus strategy: when to reuse focus plane, when to run local autofocus, and when to re-anchor.
- GUI ROI selection and persisted ROI records.
- Focus-plane fitting from anchor points.
- Focus quality trend monitoring during long runs.

### Position Calibration

Implemented:

- `calibration.phase_correlation.estimate_translation()` estimates pixel translation between reference and current images.
- `calibration.stage_transform.PixelStageTransform` converts between pixel shifts and stage shifts through a 2x2 matrix.
- `calibration.xy_corrector.estimate_xy_correction()` returns inverse XY correction in stage units.
- `calibration.stage_adapter.estimate_and_apply_xy_correction()` applies correction through `XYZStage`.

Important behavior:

- The current implementation assumes image motion is mostly translation.
- The transform convention is:

```text
[dx_px, dy_px]^T = pixel_per_um @ [dx_um, dy_um]^T
```

Missing:

- A calibration workflow that commands known XY moves, captures frames, estimates shifts, and fits `pixel_per_um`.
- Persistent calibration records, including ROI, magnification, camera settings, matrix, confidence, and validation residual.
- Verification after correction.
- Handling for low-confidence registration during mapping.

### Camera And LabSpec

Implemented:

- `microscope.acquisition.AcquisitionController` can act as a `FrameProvider` for autofocus.
- `camera-activeX/` contains DirectShow/COM diagnostics and frame capture experiments.

Missing:

- One stable camera acquisition path selected for production mapping.
- A LabSpec abstraction for starting an acquisition and waiting for completion.
- Run-time ownership rules for camera usage when LabSpec and the microscope preview both want the same hardware.

## Proposed Architecture

Add a new package:

```text
raman/mapping/
  models.py              # MappingPoint, MappingGrid, MappingParams, PointRecord, RunRecord
  planner.py             # grid generation and point ordering
  focus_plane.py         # fit/predict z = ax + by + c
  calibration_workflow.py# pixel/stage transform calibration and validation
  runner.py              # mapping state machine
  records.py             # JSONL/CSV/image path persistence
  labspec.py             # LabSpec protocol plus manual/mock adapters
```

Keep the runner dependent only on:

- `XYZStage` for motion.
- `FrameProvider` for microscope images.
- `AutofocusController` for local Z focus.
- `PixelStageTransform` and `estimate_translation()` for XY correction.
- `RamanAcquirer` protocol for LabSpec integration.
- `RunRecorder` for persistence.

Suggested LabSpec interface:

```python
class RamanAcquirer(Protocol):
    def acquire_point(self, point_id: str, metadata: dict) -> "AcquisitionResult":
        ...
```

The first implementation can be manual or file-trigger based. COM automation should be isolated behind this protocol once the reliable LabSpec control surface is confirmed.

## Mapping Data Model

Minimum records:

- `MappingPoint`: `point_id`, planned `x_um`, `y_um`, optional planned `z_um`.
- `FocusAnchor`: `x_um`, `y_um`, `z_um`, `confidence`, ROI, image path.
- `FocusPlane`: coefficients `a`, `b`, `c`, residual statistics, anchors used.
- `CalibrationRecord`: pixel/stage matrix, ROI, reference image, validation shifts, confidence.
- `PointRecord`: planned position, commanded position, final position, focus result, XY correction, registration confidence, Raman acquisition result, image paths, timestamps, status.
- `RunRecord`: run ID, sample ID, operator notes, hardware config, mapping params, calibration IDs, output directory.

Persist point records as JSONL during the run so partial runs remain recoverable after interruption.

## Motion-Control Plan

1. Define software limits for X, Y, and Z before any mapping run.
2. Implement or wrap the real XY stage as `XYZStage`.
3. Keep Z movement direction consistent for autofocus final approach.
4. Add a global abort path that calls `stage.stop()` and marks the run interrupted.
5. Log every command and settle result.
6. Use preflight checks:
   - current position readable,
   - all grid points inside limits,
   - predicted Z inside limits,
   - stage can move a small test distance and return.

Until the real XY hardware adapter exists, use `MemoryXYZStage` to build and test the mapping runner offline.

## Autofocus Plan

Use a two-level strategy:

1. Anchor autofocus:
   - Pick 3-9 anchor points across the mapping area.
   - Run full autofocus at each anchor.
   - Reject anchors with `NO_PEAK`, `OUT_OF_RANGE`, or low confidence unless manually approved.
   - Fit `z = ax + by + c`.

2. Per-point autofocus:
   - Predict Z from the plane.
   - For most points, move directly to predicted Z.
   - Run local autofocus every N points, when registration/focus score degrades, or when the predicted plane residual is high.
   - Update the focus plane only from high-confidence local autofocus results.

Recommended first-pass defaults:

- 5 anchors: center plus four corners.
- Local autofocus every 10-20 points.
- Force local autofocus after any low-confidence XY correction.
- Keep full coarse/fine autofocus for anchors; use smaller fine-only or narrow-range autofocus for per-point refresh.

## Position-Calibration Plan

Calibration should be an explicit workflow before mapping:

1. Move to a textured field and focus.
2. Capture reference image.
3. Move `+X` by a known distance, capture image, estimate pixel shift.
4. Return, move `+Y` by a known distance, capture image, estimate pixel shift.
5. Fit `pixel_per_um`.
6. Validate with one or more diagonal or negative moves.
7. Save the transform and validation residuals.

During mapping:

1. Capture a current microscope image after Z movement.
2. Compare with a reference image for the point or local anchor.
3. Convert pixel shift to stage correction.
4. Apply correction if confidence is high and correction magnitude is within a configured limit.
5. Optionally capture a second image and verify residual drift.

Correction must be bounded. A low-confidence or too-large correction should not blindly move the stage; it should mark the point for retry or operator review.

## Mapping Runner State Machine

Suggested states:

```text
INIT
  -> PREFLIGHT
  -> CALIBRATE_OR_LOAD
  -> FOCUS_ANCHORS
  -> RUN_POINTS
  -> COMPLETE

RUN_POINTS per point:
  MOVE_XY
  PREDICT_AND_MOVE_Z
  OPTIONAL_AUTOFOCUS
  CAPTURE_IMAGE
  XY_REGISTER
  OPTIONAL_XY_CORRECT
  OPTIONAL_VERIFY
  RAMAN_ACQUIRE
  RECORD_POINT
```

Failure handling:

- Stage error: stop run and require operator action.
- Frame timeout: retry capture once, then mark point failed.
- Autofocus `NO_PEAK`: retry with expanded range or skip point depending on policy.
- Autofocus `LOW_CONFIDENCE`: continue only if configured; mark record.
- XY registration low confidence: skip correction, optionally run local autofocus and retry registration.
- Raman acquisition failure: record failure and continue or abort according to policy.

## Implementation Phases

### Phase 1: Offline Mapping Skeleton

Deliverables:

- `mapping.models`, `mapping.planner`, `mapping.focus_plane`, `mapping.runner`.
- Offline runner using `MemoryXYZStage`, synthetic frames, fake Raman acquirer.
- JSONL point records.
- Tests for grid ordering, focus-plane prediction, retry/status behavior.

### Phase 2: Calibration Workflow

Deliverables:

- `calibration_workflow.py` that fits `PixelStageTransform` from commanded moves and captured frames.
- Persistent calibration record format.
- Validation routine that reports residual pixel/stage error.
- Tests using synthetic translated images and `MemoryXYZStage`.

### Phase 3: Hardware Motion Integration

Deliverables:

- Real XY/XYZ stage adapter.
- Motion limit config.
- Hardware smoke tests for read/move/wait/stop.
- Repeatability and backlash measurement scripts.

### Phase 4: Camera And GUI Integration

Deliverables:

- Stable production `FrameProvider`.
- GUI ROI selection.
- Mapping run setup panel: grid, ROI, focus params, calibration selection.
- Background worker for mapping so the GUI thread never blocks.

### Phase 5: LabSpec Integration

Deliverables:

- `RamanAcquirer` adapter for the chosen LabSpec control method.
- Manual fallback mode.
- Acquisition result records with file references.
- End-to-end dry run and hardware run protocol.

## Current Function Optimizations Needed

Priority 1:

- Implement real `XYZStage` or an adapter that combines the existing Z controller with confirmed XY motion control.
- Add motion-limit configuration and enforce it before every commanded move.
- Add focus-plane fitting and anchor autofocus workflow.
- Add persistent run records under a structured output directory.
- Add calibration record persistence for `PixelStageTransform`.
- Add bounded XY correction policy: max correction, min confidence, optional verify.

Priority 2:

- Add GUI ROI selection and save ROI with run/calibration records.
- Add mapping runner tests with fake stage, fake frames, and fake Raman acquirer.
- Add camera acquisition selection: decide whether production mapping uses `pyueye`, DirectShow, or LabSpec-owned capture.
- Add hardware smoke scripts for real Z autofocus and XY correction.
- Add operator abort/pause/resume states.

Priority 3:

- Add adaptive autofocus scheduling based on focus score trend and registration quality.
- Add focus-plane update from successful local autofocus points.
- Add run resume from JSONL records.
- Add calibration drift checks during long mappings.
- Add summary report generation after each run.

## Practical First Milestone

The next useful milestone is an offline end-to-end mapping runner:

1. Generate a small 3x3 grid.
2. Use `MemoryXYZStage`.
3. Fit a focus plane from synthetic anchors.
4. Run through all points with fake autofocus and fake Raman acquisition.
5. Write one JSONL record per point.
6. Prove failures are recorded and do not corrupt the run state.

This creates the orchestration structure before hardware-specific uncertainty blocks progress.
