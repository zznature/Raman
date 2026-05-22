

LabSpec.Acq 0, 1, 1, 0, 0
Do
  DataID = LabSpec.GetAcqID()
Loop Until DataID > 0
LabSpec.Message "Acquisition done: " & DataID, 0