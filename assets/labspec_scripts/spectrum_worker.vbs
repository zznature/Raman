' LabSpec-internal spectrum acquisition worker.
'
' Run this script inside LabSpec. External programs submit one request by writing
' REQUEST_PATH as key=value lines. The worker executes LabSpec.Acq inside the
' proven LabSpec VBS context, then writes RESULT_PATH.

Option Explicit

Const ACQ_SPECTRUM = 0
Const ACQ_AUTO_SHOW = 10
Const ACQ_CANCEL = 8

Const ForReading = 1
Const ForWriting = 2

Dim REQUEST_PATH
Dim RESULT_PATH
Dim STOP_PATH
Dim POLL_MS

REQUEST_PATH = "D:\RamanLab\RamanLab\raman\runtime\labspec_bridge\spectrum_request.ini"
RESULT_PATH = "D:\RamanLab\RamanLab\raman\runtime\labspec_bridge\spectrum_result.ini"
STOP_PATH = "D:\RamanLab\RamanLab\raman\runtime\labspec_bridge\spectrum_worker.stop"
POLL_MS = 200

Dim Fso
Set Fso = CreateObject("Scripting.FileSystemObject")
EnsureParentFolder REQUEST_PATH

LabSpec.Message "Spectrum worker started", 6

Do
  If Fso.FileExists(STOP_PATH) Then
    Fso.DeleteFile STOP_PATH, True
    Exit Do
  End If

  If Fso.FileExists(REQUEST_PATH) Then
    ProcessRequest
  End If

  LabSpec.Pause POLL_MS
Loop

LabSpec.Message "Spectrum worker stopped", 6

Sub ProcessRequest()
  On Error Resume Next

  Dim Request
  Set Request = ReadKeyValueFile(REQUEST_PATH)
  If Err.Number <> 0 Then
    WriteFailure "", "read_request", Err.Description
    Err.Clear
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
  Dim Mode
  Dim DataID
  Dim StartedAt
  Dim FinishedAt
  Dim SaveRet

  RequestID = GetString(Request, "request_id", "")
  IntegrationTime = CDbl(GetString(Request, "integration_time_s", "1"))
  Accumulations = CLng(GetString(Request, "accumulations", "1"))
  AcqFrom = CDbl(GetString(Request, "from_nm", "0"))
  AcqTo = CDbl(GetString(Request, "to_nm", "0"))
  AutoShow = CLng(GetString(Request, "auto_show", "1"))
  SavePath = GetString(Request, "save_path", "")
  SaveFormat = GetString(Request, "save_format", "txt")

  If IntegrationTime <= 0 Then
    WriteFailure RequestID, "invalid_request", "integration_time_s must be > 0"
    DeleteRequest
    Exit Sub
  End If
  If Accumulations <= 0 Then
    WriteFailure RequestID, "invalid_request", "accumulations must be > 0"
    DeleteRequest
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
    WriteFailure RequestID, "acq_start", Err.Description
    Err.Clear
    DeleteRequest
    Exit Sub
  End If

  Do
    DataID = LabSpec.GetAcqID()
  Loop Until DataID > 0

  FinishedAt = LabSpec.TickCount()
  SaveRet = ""
  If Len(SavePath) > 0 Then
    EnsureParentFolder SavePath
    SaveRet = CStr(LabSpec.Save(DataID, SavePath, SaveFormat))
  End If

  WriteSuccess RequestID, DataID, StartedAt, FinishedAt, SavePath, SaveFormat, SaveRet
  DeleteRequest
End Sub

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

Sub WriteSuccess(RequestID, DataID, StartedAt, FinishedAt, SavePath, SaveFormat, SaveRet)
  Dim File
  EnsureParentFolder RESULT_PATH
  Set File = Fso.OpenTextFile(RESULT_PATH, ForWriting, True)
  File.WriteLine "status=ok"
  File.WriteLine "request_id=" & RequestID
  File.WriteLine "spectrum_id=" & CStr(DataID)
  File.WriteLine "duration_ms=" & CStr(FinishedAt - StartedAt)
  File.WriteLine "save_path=" & SavePath
  File.WriteLine "save_format=" & SaveFormat
  File.WriteLine "save_return=" & SaveRet
  File.Close
End Sub

Sub WriteFailure(RequestID, StepName, Message)
  Dim File
  EnsureParentFolder RESULT_PATH
  Set File = Fso.OpenTextFile(RESULT_PATH, ForWriting, True)
  File.WriteLine "status=error"
  File.WriteLine "request_id=" & RequestID
  File.WriteLine "step=" & StepName
  File.WriteLine "message=" & Replace(Message, vbCrLf, " ")
  File.Close
End Sub

Sub DeleteRequest()
  If Fso.FileExists(REQUEST_PATH) Then
    Fso.DeleteFile REQUEST_PATH, True
  End If
End Sub

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
