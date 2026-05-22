# Send
  
Description : Send Data To an external device
Keywords : AFM Communication network ethernet RS232 GPIB
Type : AutoVBSAct
Category : Communication


--------------------------------------------------------------------------------

VARIANT Send(LPCTSTR To, LPCTSTR Command, const VARIANT FAR& Param, long Mode, VARIANT FAR* Status) 

Send data to an external device. Return value is the received value from the external device. 

To : Device Name (i.e. "JPKAFM" or "RS232") 

Command : Command to send. 
             RS232_OPEN : Command must be : ComPort ; ComParams ; TimeOut (i.e. "COM1;19200,n,8n1;7000"). COM port number must be in the 1-9 range. 
             RS232_SEND : Command to send 
             RS232_RECEIVE : number of bytes to receive 

             GPIB_OPEN : Command must be : GPIB BoardNum ; Dev DeviceNum (i.e. "GPIB0;Dev1") 
             GPIB_SEND : Command to send 
             GPIB_RECEIVE : number of bytes to receive 

             HTTP_GET : Command must be : host/url (i.e. "www.myserver.com/page1.html" or "http://192.168.1.100/mypage.php?var1=Myvar1&var2=Myvar2") 

             HTTP_POST : Command must be : host/url (i.e. "www.myserver.com/page1.php") 
                        Param must include the variables and/or files to post. 
                        The variables must be set before the files. 
                        Variables and files sections are separated by #. i.e. : "var1=Myvar1&var2=Myvar2#MyFile=d:MyFile.jpg" 

             HTTP_DOWNLOAD : Command must be : host/url (i.e. "www.myserver.com/myfile.pdf" or "http://192.168.1.100/dir1/MyFile.zip"). 
                         Param must include the downloaded file path (i.e. "d:MyDownloadedFile.pdf") 
                         If download is successfull, Status=0 and function returns file size 
                         If download fails, Status<0 and function returns an error message 

Param : Optional Parameter (for interpreted commands, see mode) 

Mode : Communication Mode : 
             RAW : Directly send the command to the hardware 
             INTERPRETED : Command will be interpreted by LabSpec before being sent to the hardware 

             RS232_OPEN : Open RS232 communication 
             RS232_SEND : Send RS232 command 
             RS232_RECEIVE : Receive RS232 communication 

             GPIB_OPEN : Open GPIB communication 
             GPIB_SEND : Send GPIB command 
             GPIB_RECEIVE : Receive GPIB communication 

Status : Commad Status (only for INTERPRETED Mode) 
            SUCCESS if command successfully executed 
            FAILED if command failed 

return Value : 

RAW : Received command from the device 
INTERPRETED : Interpreted result 
HTTP : Requested data. 


--------------------------------------------------------------------------------


JPK AFM Interpreted commands Specifications : 

Command : "ForceConnection" Try to connect to the AFM if not connected 
Param : not used 
Return Values : not used 

Command : "MoveToPoint" Move to the specified Point 
Param : Point Index 
Return Values : SUCCESS : Array (2) filled with X and Y coords 
                            FAILED : Error Message 

Command : "StartHeightMeasurement" Start AFM Height Measurements 
Param : N/A 
Return Values : SUCCESS : OK 
                            FAILED : Error Message 

Command : "FinishHeightMeasurement" Stop and Get AFM Height Measurements 
Param : N/A 
Return Values : SUCCESS : Array (3) filled with Average Height, RMS and Accumulation Time 
                            FAILED : Error Message 

Command : "GetSampleScannerRange" Get Sample Scanner Range 
Param : N/A 
Return Values : SUCCES : Array (4) filled with xMin, yMin, xMax, yMax 
                            FAILED : Error Message 

Command : "GetListSize" Get Point List Size 
Param : N/A 
Return Value : Number of Points. 

Command : "GetPointCoords" Get Point Coordonates 
Param : Point Index 
Return Values : SUCCESS : Array (2) filled with X and Y coords 
                            FAILED : Error Message 

Command : "GetList" Get Current List 
Param : Mode : NATIVE (return either the point list or the point grid) or FORCE_LIST (return a point list) 
Return Value : Array (ListSize*2+1) if LIST - (7+1) if GRID : First Value (Value(0)) = LIST or GRID. 
                            if Value(0) = LIST : Value(1) to Value (ListSize*2) : Point List X0, Y0, X1, Y1, .. 
                            if Value(0) = GRID : Value(1) to Value(8) : x0, y0, dU, dV, iLenght, jLenght, theta 


--------------------------------------------------------------------------------


Constant List : 


Const INTERPRETED = 0 
Const RAW = 1 
Const SUCCESS = 0 
Const FAILED = 1 
Const LIST = 0 
Const GRID = 1 
Const NATIVE = 0 
Const FORCE_LIST = 1 

Const RS232_OPEN = 0 
Const RS232_SEND = 1 
Const RS232_RECEIVE = 2 

Const GPIB_OPEN = 0 
Const GPIB_SEND = 1 
Const GPIB_RECEIVE = 2 

 



--------------------------------------------------------------------------------


Example : 


' Get List Size 
ListSize=LabSpec.Send("JPKAFM", "GetListSize", Param, INTERPRETED, Status) 
LabSpec.Message "List Size :" & ListSize, ID_OK 

' Get Full List or Grid 
Values=LabSpec.Send("JPKAFM", "GetList", NATIVE, Param, Status) 
LabSpec.Message "List Type:" & Values(0), ID_OK 
   
if Values(0) = LIST then ' LIST 
    for i=0 to ListSize-1 
        LabSpec.Message "Point " & i & " X:" & Values(i*2+1) & " Y:" & Values(i*2+2), ID_OK 
    next 
else  ' GRID 
    for i=1 to 7 
        LabSpec.Message "GRID Param " & i & " :" & Values(i), ID_OK 
    next 
end if 

for i=0 to ListSize-1 ' For Each point in the List 

    ' Move to the Point 
    Values = LabSpec.Send ("JPKAFM", "MoveToPoint", INTERPRETED, Param, Status) 
    if Status = SUCCESS then 
        LabSpec.Message "Current AFM Position X:" & Values(0) & " Y:" & Values(1), ID_OK 
    end if 

    ' Start AFM Measurement during the Raman Measurement         
    Values = LabSpec.Send ("JPKAFM", "StartHeightMeasurement", INTERPRETED, Param, Status) 
         
    ' Start Raman Acquisition 
    LabSpec.Acq Mode,IntegrationTime,AccumulationNum,AcqFrom,AcqTo 
    do 
        SpectrumID=LabSpec.GetAcqID() ' Wait untill Spectrum is ready (acquisition is done) 
    Loop Until SpectrumID>0 

    ' Show Raman Spectrum         
    LabSpec.Exec SpectrumID, SHOW_DATA, Param 

    ' Get AFM Results 
    Values = LabSpec.Send ("JPKAFM", "FinishHeightMeasurement", INTERPRETED, Param, Status) 
    if Status=SUCCESS then 
        LabSpec.Message "Average Height:" & Values(0) & " RMS:" & Values(1) & " Accumulation Time:" & Values(2), ID_OK 
    ' Set RMS the the Spectrum Parameters Table 
        LabSpec.PutDataInfo SpectrumID, "Acq", "RMS", Values(1) 
    else 
        LabSpec.Message Values, ID_OK 
    end if 

next 

 


RS232 Example (Get Temperature from a linkam stage) 

Dim Param 
Dim Status 
Dim ret 

' Init RS232 communication 
LabSpec.Send "RS232","COM1;19200,n,8,1;7000",Param,GPIB_OPEN,Status 
' Send Value to RS232 
LabSpec.Send "RS232","T" & vbCr,Param,GPIB_SEND,Status 
' Retreive 6 bytes from RS232 (status bytes) 
ret=LabSpec.Send ("RS232","6",Param,GPIB_RECEIVE,Status) 
' Retreive 4 bytes from RS232 (temperature value) 
ret=LabSpec.Send ("RS232","4",Param,GPIB_RECEIVE,Status) 
' Convert and display current temperature 
LabSpec.Message "Current Temp : " & Hextodec(ret)*0.1 & " C",0 
' retreive final data 
ret=LabSpec.Send ("RS232","1",Param,GPIB_RECEIVE,Status) 

 


GPIB Example (Display SR830 Data in the Status bar) 

Const GPIB_OPEN = 0 
Const GPIB_SEND = 1 
Const GPIB_RECEIVE = 2 
Dim param 
Dim ret 

' Initialize PGIB communication With SR830 
LabSpec.Send "GPIB","GPIB0;Dev8",param,GPIB_OPEN,param 

' Start Acquisition 
LabSpec.Send "GPIB","STRT",param,GPIB_SEND,param 

' Continuously read data from the Lock-in 
Do 

    ' Ask For Data 
    LabSpec.Send "GPIB","OUTP?3",param,GPIB_SEND,param 

    ' Read Data (size=20 bytes) 
    ret=LabSpec.Send ("GPIB","20",param,GPIB_RECEIVE,param) 

    ' Display Data in the StatusBar 
    LabSpec.Message "SR830 Data : " & ret,6 

Loop 

 
