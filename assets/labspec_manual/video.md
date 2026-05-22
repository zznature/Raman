# Video

Description : Display video image
Keywords : camera extended
Type : AutoVBSAct
Category : Video Control


--------------------------------------------------------------------------------

long Video(long Mode) 

Mode : Start/Stop video 
            0 : START_VIDEO Start Video 
            1 : STOP_VIDEO Stop Video 
            2 : GET_VIDEO_ID Get Video ID (ActiveX mode : You need to call that function during the entire video process) 
            3 : START_EXTENDED_VIDEO Start an Extended Video (see SetExtendedVideo() to define the parameters). An Extended Video Image is not a live image. 
            4 : GET_ACTIVE_CAMERA Get the active video CameraID 
            10+CameraID : SET_ACTIVE_CAMERA Set the active video camera ID 



Return Values : 
>0 : VideoID 
0 : OK 
-1 : Error 

Constant List : 


Const START_VIDEO = 0 
Const STOP_VIDEO = 1 
Const GET_VIDEO_ID = 2 
Const START_EXTENDED_VIDEO = 3 
Const GET_ACTIVE_CAMERA = 4 
Const SET_ACTIVE_CAMERA = 10 
--------------------------------------------------------------------------------

Example : 


Dim Ret 
Dim VideoID 
Dim StopVideo 

Ret = LabSpec.Video(START_VIDEO) 


' Only for ActiveX use 
Do 
    IDVideo = LabSpec.Video(GET_VIDEO_ID) 
    DoEvents 
Loop until StopVideo=1 ' WARNING : You have to add a button to stop the video (StopVideo=1) 
' End Only for ActiveX use 

Ret = LabSpec.Video(STOP_VIDEO) 

 

--------------------------------------------------------------------------------

## Local LabSpec 6.5.1 notes from installed help

The lab PC also has the original LabSpec help files under:

`C:\HORIBA\LabSpec_6_5_1\HELP\VBS`

Relevant pages:

- `Video.html`
- `Save.html`
- `SetExtendedVideo.html`

### Saving a VideoID

`Video(GET_VIDEO_ID)` returns a LabSpec data ID for the current video image while
video is running. LabSpec's generic save function can then save that data ID:

```vb
Ret = LabSpec.Save(VideoID, FileName, Format)
```

Signature from the installed help:

```text
long Save(long ID, LPCTSTR pFileName, LPCTSTR pFormat)
```

Return values:

- `0`: succeeded
- `-1`: failed

For autofocus, this means the likely LabSpec-compatible capture path is:

```vb
Ret = LabSpec.Video(START_VIDEO)
Do
    VideoID = LabSpec.Video(GET_VIDEO_ID)
Loop Until VideoID > 0
Ret = LabSpec.Save(VideoID, "D:\RamanLab\RamanLab\raman\captures\frame.tif", "tif")
Ret = LabSpec.Video(STOP_VIDEO)
```

This path must run inside LabSpec's VBS/script environment unless a separate
external automation object can be attached.

### Extended video

The installed help documents:

```text
long SetExtendedVideo(long NbImgX, long NbImgY, long MaxSizeX, long MaxSizeY, long OverlapX, long OverlapY)
```

It is marked `LS5 only`, so it should not be treated as the primary route for
LabSpec 6 autofocus frame capture.

### External Python COM probe result

On this machine, `LabSpec64.exe` is running, and the registry contains document
ProgIDs such as:

- `LabSpec6.S` - LabSpec6 Spectrum
- `LabSpec6.I` - LabSpec6 Image
- `LabSpec6.V` - LabSpec6 Video

However, `win32com.client.GetActiveObject("LabSpec6.S")` and the other
`LabSpec6.*` ProgIDs return `Operation unavailable`, and `Dispatch(...)` returns
`No such interface supported`. These ProgIDs are therefore not usable as the
external LabSpec application automation endpoint from Python.

Current implication: saving video frames while LabSpec owns the camera should be
validated with a LabSpec-internal VBS script first. See:

`raman\assets\labspec_scripts\video_save_probe.vbs`
