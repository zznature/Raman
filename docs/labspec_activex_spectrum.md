# LabSpec ActiveX Spectrum Acquisition Notes

## Goal

Acquire one spectrum with parameters supplied by an external program:

- integration time
- accumulation count
- detector range
- optional save path

The acquisition target is a single spectrum, not LabSpec mapping.

## ActiveX direct-call result

The installed ActiveX control is:

```text
ProgID: NFACTIVEX.NFActiveXCtrl.1
CLSID:  {084B94EF-4DA1-4964-A142-6AD6C4B3E1C9}
64-bit: C:\HORIBA\LabSpec_6_5_1\REG64\COMMON\NFActiveX.ocx
32-bit: C:\HORIBA\LabSpec_6_5_1\Register\Common\NFActiveX.ocx
```

The type library exposes `Acq`, `GetAcqID`, `ConvertUnit`, `Message`, and related
methods. The external smoke tools can instantiate the 64-bit control and call
`InitNA(0, 0)` and `SetScriptPath(...)`.

Direct external acquisition is still blocked. Observed behavior:

- 64-bit host:
  - `TickCount` returns.
  - `ConvertUnit`, `GetAcqID`, `GetActiveData`, `Message`, and `Acq` block.
- 32-bit host:
  - `InitNA(0, 0)` raises an access violation.
- Running from the same `RAMAN` console user/session as LabSpec does not fix it.
- Visible WinForms hosting does not fix it.
- Adding LabSpec directories to the process DLL search path does not fix it.
- Passing LabSpec main window handle, process ID, or `1` to `InitNA` does not fix it.
- LabSpec has a normal visible main window and no obvious modal dialog during tests.

Current interpretation: externally created `NFActiveX.ocx` is only a control shell
unless LabSpec's internal script module supplies the real LabSpec object context.
Methods that need that context wait indefinitely. `TickCount` returns because it is
effectively local to the control.

## Working bridge

Use a LabSpec-internal worker script:

```text
assets/labspec_scripts/spectrum_worker.vbs
```

Run it inside LabSpec. The worker watches:

```text
raman/runtime/labspec_bridge/spectrum_request.ini
```

and writes:

```text
raman/runtime/labspec_bridge/spectrum_result.ini
```

Submit one externally configured request:

```powershell
python raman\acquire-spectrum\request_labspec_spectrum.py `
  --integration-time 1 `
  --accumulations 1 `
  --from-nm 0 `
  --to-nm 0 `
  --save-path raman\runtime\labspec_bridge\spectrum.txt `
  --save-format txt
```

Stop the worker by creating:

```text
raman/runtime/labspec_bridge/spectrum_worker.stop
```

This keeps the actual `LabSpec.Acq` and `LabSpec.GetAcqID` calls inside the
LabSpec VBS context, which has been verified to acquire successfully, while still
allowing external parameter control.
