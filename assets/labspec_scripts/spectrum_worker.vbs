' LabSpec-internal spectrum acquisition worker.
'
' Run this script inside LabSpec. External programs can either write the legacy
' REQUEST_PATH file or enqueue many *.ini files under REQUEST_DIR. The worker
' claims one request at a time, executes LabSpec.Acq inside the LabSpec VBS
' context, writes a result file, and keeps the UI responsive by yielding with
' LabSpec.Pause during every polling loop.

Option Explicit

Const ACQ_SPECTRUM = 0
Const ACQ_AUTO_SHOW = 10
Const ACQ_CANCEL = 8

Const ForReading = 1
Const ForWriting = 2

Dim BRIDGE_DIR
Dim REQUEST_PATH
Dim RESULT_PATH
Dim STOP_PATH
Dim REQUEST_DIR
Dim PROCESSING_DIR
Dim RESULT_DIR
Dim FAILED_DIR
Dim POLL_MS
Dim ACQ_POLL_MS
Dim DEFAULT_TIMEOUT_MARGIN_MS
Dim Fso

Set Fso = CreateObject("Scripting.FileSystemObject")

BRIDGE_DIR = ResolveBridgeDir()
REQUEST_PATH = BRIDGE_DIR & "\spectrum_request.ini"
RESULT_PATH = BRIDGE_DIR & "\spectrum_result.ini"
STOP_PATH = BRIDGE_DIR & "\spectrum_worker.stop"
REQUEST_DIR = BRIDGE_DIR & "\requests"
PROCESSING_DIR = BRIDGE_DIR & "\processing"
RESULT_DIR = BRIDGE_DIR & "\results"
FAILED_DIR = BRIDGE_DIR & "\failed"
POLL_MS = 200
ACQ_POLL_MS = 100
DEFAULT_TIMEOUT_MARGIN_MS = 10000

EnsureFolder BRIDGE_DIR
EnsureFolder REQUEST_DIR
EnsureFolder PROCESSING_DIR
EnsureFolder RESULT_DIR
EnsureFolder FAILED_DIR

LabSpec.Message "Spectrum worker started: " & BRIDGE_DIR, 6

Do
  If Fso.FileExists(STOP_PATH) Then
    Fso.DeleteFile STOP_PATH, True
    Exit Do
  End If

  Dim RequestPath
  Dim LegacyResult
  RequestPath = ClaimNextRequest(LegacyResult)

  If Len(RequestPath) > 0 Then
    ProcessRequest RequestPath, LegacyResult
    LabSpec.Pause POLL_MS
  Else
    LabSpec.Pause POLL_MS
  End If
Loop

LabSpec.Message "Spectrum worker stopped", 6

Function ResolveBridgeDir()
  Dim EnvPath
  Dim Shell
  On Error Resume Next
  Set Shell = CreateObject("WScript.Shell")
  If Err.Number = 0 Then
    EnvPath = Trim(Shell.ExpandEnvironmentStrings("%RAMANLAB_BRIDGE_DIR%"))
    If Len(EnvPath) > 0 Then
      If EnvPath <> "%RAMANLAB_BRIDGE_DIR%" Then
        ResolveBridgeDir = EnvPath
        On Error GoTo 0
        Exit Function
      End If
    End If
  End If
  Err.Clear
  On Error GoTo 0

  ResolveBridgeDir = ResolveBridgeDirFromScript()
End Function

Function ResolveBridgeDirFromScript()
  Dim ScriptPath
  Dim ScriptFolder
  Dim RamanRoot
  On Error Resume Next
  ScriptPath = WScript.ScriptFullName
  If Err.Number = 0 Then
    ScriptFolder = Fso.GetParentFolderName(ScriptPath)
    RamanRoot = Fso.GetParentFolderName(Fso.GetParentFolderName(ScriptFolder))
    ResolveBridgeDirFromScript = Fso.BuildPath(RamanRoot, "runtime\labspec_bridge")
    On Error GoTo 0
    Exit Function
  End If
  Err.Clear
  On Error GoTo 0

  ResolveBridgeDirFromScript = Fso.GetAbsolutePathName("runtime\labspec_bridge")
End Function

Function ClaimNextRequest(ByRef LegacyResult)
  LegacyResult = False
  ClaimNextRequest = ""

  If Fso.FileExists(REQUEST_PATH) Then
    LegacyResult = True
    ClaimNextRequest = ClaimFile(REQUEST_PATH, PROCESSING_DIR & "\legacy_" & UniqueSuffix() & ".ini")
    Exit Function
  End If

  Dim Folder
  Dim File
  Dim BestFile
  Dim BestTime
  Set BestFile = Nothing

  Set Folder = Fso.GetFolder(REQUEST_DIR)
  For Each File In Folder.Files
    If LCase(Fso.GetExtensionName(File.Name)) = "ini" Then
      If Left(File.Name, 1) <> "." Then
        If BestFile Is Nothing Then
          Set BestFile = File
          BestTime = File.DateLastModified
        ElseIf File.DateLastModified < BestTime Then
          Set BestFile = File
          BestTime = File.DateLastModified
        End If
      End If
    End If
  Next

  If Not BestFile Is Nothing Then
    ClaimNextRequest = ClaimFile(BestFile.Path, PROCESSING_DIR & "\" & Fso.GetBaseName(BestFile.Name) & "_" & UniqueSuffix() & ".ini")
  End If
End Function

Function ClaimFile(SourcePath, TargetPath)
  On Error Resume Next
  Err.Clear
  Fso.MoveFile SourcePath, TargetPath
  If Err.Number <> 0 Then
    Err.Clear
    ClaimFile = ""
  Else
    ClaimFile = TargetPath
  End If
  On Error GoTo 0
End Function

Sub ProcessRequest(RequestPath, LegacyResult)
  On Error Resume Next

  Dim Request
  Set Request = ReadKeyValueFile(RequestPath)
  If Err.Number <> 0 Then
    WriteFailure ResolveResultPath("", LegacyResult, RequestPath), "", "read_request", Err.Description
    MoveFailed RequestPath
    Err.Clear
    On Error GoTo 0
    Exit Sub
  End If

  Dim RequestID
  Dim IntegrationTime
  Dim Accumulations
  Dim AcqFrom
  Dim AcqTo
  Dim AutoShow
  Dim SavePath
  Dim SaveFormat
  Dim TimeoutMs
  Dim Mode
  Dim DataID
  Dim StartedAt
  Dim FinishedAt
  Dim SaveRet
  Dim ResultPath
  Dim WaitStartedAt

  RequestID = GetString(Request, "request_id", "")
  If Len(RequestID) = 0 Then
    RequestID = Fso.GetBaseName(RequestPath)
  End If

  ResultPath = ResolveResultPath(RequestID, LegacyResult, RequestPath)
  IntegrationTime = CDbl(GetString(Request, "integration_time_s", "1"))
  Accumulations = CLng(GetString(Request, "accumulations", "1"))
  AcqFrom = CDbl(GetString(Request, "from_nm", "0"))
  AcqTo = CDbl(GetString(Request, "to_nm", "0"))
  AutoShow = CLng(GetString(Request, "auto_show", "1"))
  SavePath = GetString(Request, "save_path", "")
  SaveFormat = GetString(Request, "save_format", "txt")
  TimeoutMs = CLng(GetString(Request, "timeout_ms", CStr(CLng(IntegrationTime * Accumulations * 1000) + DEFAULT_TIMEOUT_MARGIN_MS)))

  If Err.Number <> 0 Then
    WriteFailure ResultPath, RequestID, "parse_request", Err.Description
    MoveFailed RequestPath
    Err.Clear
    On Error GoTo 0
    Exit Sub
  End If

  If IntegrationTime <= 0 Then
    WriteFailure ResultPath, RequestID, "invalid_request", "integration_time_s must be > 0"
    MoveFailed RequestPath
    On Error GoTo 0
    Exit Sub
  End If
  If Accumulations <= 0 Then
    WriteFailure ResultPath, RequestID, "invalid_request", "accumulations must be > 0"
    MoveFailed RequestPath
    On Error GoTo 0
    Exit Sub
  End If
  If TimeoutMs <= 0 Then
    WriteFailure ResultPath, RequestID, "invalid_request", "timeout_ms must be > 0"
    MoveFailed RequestPath
    On Error GoTo 0
    Exit Sub
  End If

  Mode = ACQ_SPECTRUM
  If AutoShow <> 0 Then
    Mode = Mode + ACQ_AUTO_SHOW
  End If

  StartedAt = LabSpec.TickCount()
  Err.Clear
  LabSpec.Acq Mode, IntegrationTime, Accumulations, AcqFrom, AcqTo
  If Err.Number <> 0 Then
    WriteFailure ResultPath, RequestID, "acq_start", Err.Description
    MoveFailed RequestPath
    Err.Clear
    On Error GoTo 0
    Exit Sub
  End If

  DataID = 0
  WaitStartedAt = LabSpec.TickCount()
  Do
    Err.Clear
    DataID = CLng(LabSpec.GetAcqID())
    If Err.Number <> 0 Then
      WriteFailure ResultPath, RequestID, "get_acq_id", Err.Description
      MoveFailed RequestPath
      Err.Clear
      On Error GoTo 0
      Exit Sub
    End If

    If DataID > 0 Then
      Exit Do
    End If

    If LabSpec.TickCount() - WaitStartedAt >= TimeoutMs Then
      Err.Clear
      LabSpec.Acq ACQ_CANCEL, 0, 0, 0, 0
      WriteFailure ResultPath, RequestID, "acq_timeout", "GetAcqID timed out after " & CStr(TimeoutMs) & " ms"
      MoveFailed RequestPath
      Err.Clear
      On Error GoTo 0
      Exit Sub
    End If

    LabSpec.Pause ACQ_POLL_MS
  Loop

  FinishedAt = LabSpec.TickCount()
  SaveRet = ""
  If Len(SavePath) > 0 Then
    EnsureParentFolder SavePath
    Err.Clear
    SaveRet = CStr(LabSpec.Save(DataID, SavePath, SaveFormat))
    If Err.Number <> 0 Then
      WriteFailure ResultPath, RequestID, "save", Err.Description
      MoveFailed RequestPath
      Err.Clear
      On Error GoTo 0
      Exit Sub
    End If
  End If

  WriteSuccess ResultPath, RequestID, DataID, StartedAt, FinishedAt, SavePath, SaveFormat, SaveRet
  DeleteFileIfExists RequestPath
  LabSpec.Message "Spectrum done: " & RequestID & " id=" & CStr(DataID), 6
  On Error GoTo 0
End Sub

Function ResolveResultPath(RequestID, LegacyResult, RequestPath)
  If LegacyResult Then
    ResolveResultPath = RESULT_PATH
  ElseIf Len(RequestID) > 0 Then
    ResolveResultPath = RESULT_DIR & "\" & RequestID & ".ini"
  Else
    ResolveResultPath = RESULT_DIR & "\" & Fso.GetBaseName(RequestPath) & ".ini"
  End If
End Function

Function ReadKeyValueFile(Path)
  Dim Dict
  Dim File
  Dim Line
  Dim Pos
  Dim Key
  Dim Value

  Set Dict = CreateObject("Scripting.Dictionary")
  Set File = Fso.OpenTextFile(Path, ForReading, False)
  Do Until File.AtEndOfStream
    Line = Trim(File.ReadLine)
    If Len(Line) > 0 Then
      If Left(Line, 1) <> "#" Then
        Pos = InStr(Line, "=")
        If Pos > 0 Then
          Key = LCase(Trim(Left(Line, Pos - 1)))
          Value = Trim(Mid(Line, Pos + 1))
          Dict(Key) = Value
        End If
      End If
    End If
  Loop
  File.Close
  Set ReadKeyValueFile = Dict
End Function

Function GetString(Dict, Key, DefaultValue)
  Key = LCase(Key)
  If Dict.Exists(Key) Then
    GetString = Dict(Key)
  Else
    GetString = DefaultValue
  End If
End Function

Sub WriteSuccess(Path, RequestID, DataID, StartedAt, FinishedAt, SavePath, SaveFormat, SaveRet)
  Dim File
  Dim TempPath
  EnsureParentFolder Path
  TempPath = Path & "." & UniqueSuffix() & ".tmp"
  Set File = Fso.OpenTextFile(TempPath, ForWriting, True)
  File.WriteLine "status=ok"
  File.WriteLine "request_id=" & RequestID
  File.WriteLine "spectrum_id=" & CStr(DataID)
  File.WriteLine "duration_ms=" & CStr(FinishedAt - StartedAt)
  File.WriteLine "save_path=" & SavePath
  File.WriteLine "save_format=" & SaveFormat
  File.WriteLine "save_return=" & SaveRet
  File.Close
  ReplaceFile TempPath, Path
End Sub

Sub WriteFailure(Path, RequestID, StepName, Message)
  Dim File
  Dim TempPath
  EnsureParentFolder Path
  TempPath = Path & "." & UniqueSuffix() & ".tmp"
  Set File = Fso.OpenTextFile(TempPath, ForWriting, True)
  File.WriteLine "status=error"
  File.WriteLine "request_id=" & RequestID
  File.WriteLine "step=" & StepName
  File.WriteLine "message=" & Replace(Message, vbCrLf, " ")
  File.Close
  ReplaceFile TempPath, Path
End Sub

Sub ReplaceFile(SourcePath, TargetPath)
  If Fso.FileExists(TargetPath) Then
    Fso.DeleteFile TargetPath, True
  End If
  Fso.MoveFile SourcePath, TargetPath
End Sub

Sub MoveFailed(Path)
  On Error Resume Next
  If Fso.FileExists(Path) Then
    Fso.MoveFile Path, FAILED_DIR & "\" & Fso.GetBaseName(Path) & "_" & UniqueSuffix() & ".ini"
  End If
  Err.Clear
  On Error GoTo 0
End Sub

Sub DeleteFileIfExists(Path)
  On Error Resume Next
  If Fso.FileExists(Path) Then
    Fso.DeleteFile Path, True
  End If
  Err.Clear
  On Error GoTo 0
End Sub

Function UniqueSuffix()
  UniqueSuffix = CStr(LabSpec.TickCount()) & "_" & Replace(CStr(Timer), ".", "")
End Function

Sub EnsureParentFolder(Path)
  Dim Folder
  Folder = Fso.GetParentFolderName(Path)
  If Len(Folder) > 0 Then
    If Not Fso.FolderExists(Folder) Then
      EnsureFolder Folder
    End If
  End If
End Sub

Sub EnsureFolder(Folder)
  Dim Parent
  If Fso.FolderExists(Folder) Then
    Exit Sub
  End If
  Parent = Fso.GetParentFolderName(Folder)
  If Len(Parent) > 0 Then
    EnsureFolder Parent
  End If
  Fso.CreateFolder Folder
End Sub
