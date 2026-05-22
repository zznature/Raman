Const START_VIDEO = 0
Const STOP_VIDEO = 1
Const GET_VIDEO_ID = 2
Const GET_ACTIVE_CAMERA = 4

Const MB_OK = 0
Const MB_STATUS_BAR = 6
Const MB_ICONINFORMATION = 20
Const MB_ICONWARNING = 50

Dim OutputPath
Dim Format
Dim Ret
Dim CameraID
Dim VideoID
Dim StartedAt

OutputPath = "D:\RamanLab\RamanLab\raman\captures\labspec_video_probe.tif"
Format = "tif"

CameraID = LabSpec.Video(GET_ACTIVE_CAMERA)
LabSpec.Message "Active camera ID: " & CameraID, MB_STATUS_BAR

Ret = LabSpec.Video(START_VIDEO)
StartedAt = LabSpec.TickCount()

Do
  VideoID = LabSpec.Video(GET_VIDEO_ID)
Loop Until VideoID > 0 Or LabSpec.TickCount() - StartedAt > 5000

If VideoID > 0 Then
  Ret = LabSpec.Save(VideoID, OutputPath, Format)
  If Ret = 0 Then
    LabSpec.Message "Saved video frame: " & OutputPath, MB_OK + MB_ICONINFORMATION
  Else
    LabSpec.Message "LabSpec.Save failed for VideoID " & VideoID & ", ret=" & Ret, MB_OK + MB_ICONWARNING
  End If
Else
  LabSpec.Message "No positive VideoID after 5 seconds.", MB_OK + MB_ICONWARNING
End If

Ret = LabSpec.Video(STOP_VIDEO)
