# Acq

Description : Start an acquisition
Keywords : acquisition integration time accumulation extended range
Type : AutoVBSAct
Category : Collect Data

--------------------------------------------------------------------------------

long Acq(long Mode, double IntegrationTime, long AccumulationNum, double From, double To) 

Start an Acquisition 

Mode : Acquisition Mode : 
                 0 : ACQ_SPECTRUM Start a Spectrum Acquisition 
                 1 : ACQ_IMAGE Start a CCD Image Acquisition 
                 2 : ACQ_LABSPEC_PARAM Start Spectrum Acquisition with LabSpec interface parameters 
                 3 : ACQ_SPECTRAL_IMAGE Start Spectral Image Acquisition with LabSpec interface parameters 
                                 if IntegrationTime set to -1, Mapping acquisition will start with LabSpec interface parameters 
                 4 : ACQ_GET_TEMPERATURE Get the current Detector Temperature 
                 5 : ACQ_SPECTRUM_RTD Start RTD Acquisition 
                 6 : ACQ_SET_PMT_PARAMETER Set PMT Step (Use IntegrationTime Parameter to specify PMT Step). Only sets the PMT Step. does not start PMT Acquisition. 
                 7 : ACQ_MACRO_SPOT Start/Stop Macro spot (duo-scan option is required). 
                                IntegrationTime=0 : Macro Spot ON. 
                                IntegrationTime=1 : MacroSpot OFF. 
                 8 : ACQ_CANCEL Cancel current acquisition. 
                 9 : ACQ_PMT_CCD Set current detector 
                                IntegrationTime=1 : PMT 
                                IntegrationTime=2 : CCD 
                                PLEASE NOTE : in PMT mode, you will have to open the shutter before starting the acquisition : 
                                LabSpec.MoveMotor("DetectorShutter",1,"",MOTOR_VALUE), and close it after the acquisition : 
                                LabSpec.MoveMotor("DetectorShutter",0,"",MOTOR_VALUE) 

                10 : ACQ_AUTO_SHOW Add to any other Acquisition Mode : Automatically show acquired data 
                100 : ACQ_NO_SPIKE_REMOVING Add this constant disable Spike removing function 
                200 : ACQ_SINGLE_SPIKE_REMOVING Add this constant to use Single pass Spike removing function 
                300 : ACQ_DOUBLE_SPIKE_REMOVING Add this constant to use double pass Spike removing function 
                400 : ACQ_DOUBLE_AUTOADD_SPIKE_REMOVING Add this constant to use double pass Spike removing function with auto add feature (automatically add 1 extra accumulation) 

                1000 : ACQ_AUTO_SCANNING Add this constant to use AutoScanning 
                2000 : ACQ_NO_CLOSE_SHUTTER Do not close the shutter after the acquisition 
                10000 : ACQ_ACCUMULATION_MODE Change accumulation mode (Average/Sum/Detector) 
                100000 : ACQ_NO_ICS Disable ICS 
                200000 : ACQ_ICS Enable ICS 
                1000000 : ACQ_NO_DARK Disable dark correction 
                2000000 : ACQ_DARK Enable dark correction 

IntegrationTime : Spectrum Integration time (in seconds) (ignored if ACQ_LABSPEC_PARAM) 
                         0 : Use autoexposure function 
                         ACQ_ACCUMULATION_MODE  : 0=Average ; 1=Sum ; 2=Detector 

AccumulationNum : Number of spectrum accumulation (ignored if ACQ_LABSPEC_PARAM) 

From, To : Acquisition range (in nm, use ConvertUnit to use cm-1). If From=To, the acquisition width will be the detector width. (ignored if ACQ_LABSPEC_PARAM) 

Return Values : 

if ACQ_GET_TEMPERATURE : Returns the detector temperature or -1000 if an error has occured 
else : always return 0 

Constants List : 


Const ACQ_SPECTRUM = 0 
Const ACQ_IMAGE = 1 
Const ACQ_LABSPEC_PARAM = 2 
Const ACQ_SPECTRAL_IMAGE = 3 
Const ACQ_GET_TEMPERATURE = 4 
Const ACQ_SPECTRUM_RTD = 5 
Const ACQ_SET_PMT_PARAMETER = 6 
Const ACQ_MACRO_SPOT = 7 
Const ACQ_CANCEL=8 
Const ACQ_PMT_CCD=9 
Const ACQ_AUTO_SHOW = 10 
Const ACQ_LABSPEC_SPIKE_REMOVING = 0 
Const ACQ_NO_SPIKE_REMOVING = 100 
Const ACQ_SINGLE_SPIKE_REMOVING = 200 
Const ACQ_DOUBLE_SPIKE_REMOVING = 300 
Const ACQ_DOUBLE_AUTOADD_SPIKE_REMOVING = 400 
Const ACQ_AUTO_SCANNING = 1000 
Const ACQ_NO_CLOSE_SHUTTER = 2000 
Const ACQ_ACCUMULATION_MODE = 10000 
Const ACQ_NO_ICS = 100000 
Const ACQ_ICS = 200000 
Const ACQ_NO_DARK = 1000000 
Const ACQ_DARK = 2000000 


--------------------------------------------------------------------------------

Example 

This example starts an acquisition and wait for the data to be ready. 


' Start 1 sec integration time, 1 accumulation, no multiwindow acquisition 
LabSpec.Acq ACQ_SPECTRUM+ACQ_AUTO_SHOW,1,1,0,0 

' Wait Until Acquisition is done 
do 
       SpectrumID=LabSpec.GetAcqID() 
Loop Until SpectrumID>0 

 

Dim SpectrumID 

StartAcq() 
WaitForAcquisition() 

LabSpec.Message "Acquisition done.",0 

Private Sub StartAcq() 

   Dim Mode 
   Dim IntegrationTime 
   Dim AccumulationNum 
   Dim AcqFrom 
   Dim AcqTo 

   Mode=ACQ_SPECTRUM 
   IntegrationTime=1.5 ' 1.5 sec acquisition 
   AccumulationNum=2   ' 2 Accumulations 
   AcqFrom=0 ' From=To => No MultiWindows 
   AcqTo=0 

   LabSpec.Acq Mode,IntegrationTime,AccumulationNum,AcqFrom,AcqTo 

End Sub 

Private Sub WaitForAcquisition() 
   
   do 
       SpectrumID=LabSpec.GetAcqID() ' Wait until Spectrum is ready (acquisition is done)   
   Loop Until SpectrumID>0 
   
   LabSpec.Exec SpectrumID , SHOW_SPECTRUM, Param ' Show Spectrum 
End Sub 

 
--------------------------------------------------------------------------------

See Also GetAcqID 