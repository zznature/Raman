Const START_VIDEO = 0
Const STOP_VIDEO = 1
Const GET_VIDEO_ID = 2

Const MB_OK = 0
Const MB_STATUS_BAR = 6
Const MB_ICONINFORMATION = 20
Const MB_ICONWARNING = 50

Dim OutputDir
Dim StopFile
Dim Format
Dim PollMs
Dim MaxFrames
Dim Fso
Dim Ret
Dim VideoID
Dim Seq
Dim FileName
Dim StartedAt
Dim Folder
Dim ExistingFile

OutputDir = "D:\RamanLab\RamanLab\raman\captures\labspec_bridge"
StopFile = OutputDir & "\stop.txt"
Format = "tif"
PollMs = 200
MaxFrames = 0

Set Fso = CreateObject("Scripting.FileSystemObject")
If Not Fso.FolderExists(OutputDir) Then
  Fso.CreateFolder(OutputDir)
End If
If Fso.FileExists(StopFile) Then
  Fso.DeleteFile StopFile
End If
Set Folder = Fso.GetFolder(OutputDir)
For Each ExistingFile In Folder.Files
  If LCase(Left(ExistingFile.Name, 6)) = "frame_" And LCase(Right(ExistingFile.Name, 4)) = ".tif" Then
    Fso.DeleteFile ExistingFile.Path
  End If
Next

Ret = LabSpec.Video(START_VIDEO)
Seq = 0
LabSpec.Message "LabSpec video frame bridge running: " & OutputDir, MB_STATUS_BAR

Do
  VideoID = 0
  StartedAt = LabSpec.TickCount()
  Do
    VideoID = LabSpec.Video(GET_VIDEO_ID)
  Loop Until VideoID > 0 Or LabSpec.TickCount() - StartedAt > 2000

  If VideoID > 0 Then
    Seq = Seq + 1
    FileName = OutputDir & "\frame_" & Right("000000" & CStr(Seq), 6) & ".tif"
    Ret = LabSpec.Save(VideoID, FileName, Format)
    If Ret <> 0 Then
      LabSpec.Message "LabSpec.Save failed: " & FileName & ", ret=" & Ret, MB_STATUS_BAR
    End If
  Else
    LabSpec.Message "No positive VideoID while bridge is running.", MB_STATUS_BAR
  End If

  LabSpec.Pause PollMs
Loop Until Fso.FileExists(StopFile) Or (MaxFrames > 0 And Seq >= MaxFrames)

Ret = LabSpec.Video(STOP_VIDEO)
LabSpec.Message "LabSpec video frame bridge stopped after " & Seq & " frames.", MB_OK + MB_ICONINFORMATION
