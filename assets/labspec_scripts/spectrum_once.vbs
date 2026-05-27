' LabSpec-internal one-shot spectrum acquisition bridge.
'
' Run this script inside LabSpec after an external program writes
' spectrum_request.ini. It waits briefly for the request file, performs one
' acquisition, writes spectrum_result.ini, then exits.

Option Explicit

Const ACQ_SPECTRUM = 0
Const ACQ_AUTO_SHOW = 10
Const ForReading = 1
Const ForWriting = 2

Dim REQUEST_PATH
Dim RESULT_PATH

REQUEST_PATH = "D:\RamanLab\RamanLab\raman\runtime\labspec_bridge\spectrum_request.ini"
RESULT_PATH = "D:\RamanLab\RamanLab\raman\runtime\labspec_bridge\spectrum_result.ini"

Dim Fso
Set Fso = CreateObject("Scripting.FileSystemObject")

If Not WaitForRequest(REQUEST_PATH, 3000, 100) Then
  WriteFailure "", "missing_request", "Request file does not exist: " & REQUEST_PATH
  LabSpec.Message "Spectrum once: missing request", 6
Else

  Dim Request
  Set Request = ReadKeyValueFile(REQUEST_PATH)

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

  Mode = ACQ_SPECTRUM
  If AutoShow <> 0 Then
    Mode = Mode + ACQ_AUTO_SHOW
  End If

  StartedAt = LabSpec.TickCount()
  LabSpec.Acq Mode, IntegrationTime, Accumulations, AcqFrom, AcqTo
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
  If Fso.FileExists(REQUEST_PATH) Then
    Fso.DeleteFile REQUEST_PATH, True
  End If
  LabSpec.Message "Spectrum once done: " & CStr(DataID), 6
End If

Function WaitForRequest(Path, TimeoutMs, PollMs)
  Dim Deadline
  Deadline = LabSpec.TickCount() + TimeoutMs
  Do
    If Fso.FileExists(Path) Then
      WaitForRequest = True
      Exit Function
    End If
    LabSpec.Pause PollMs
  Loop Until LabSpec.TickCount() >= Deadline
  WaitForRequest = False
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
