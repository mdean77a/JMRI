# StartTrain.py created by Mike Dean May 2021
# Hoping to set up automation for train club meeting later this week
# Edited November 2023 (yes two years) to eliminate Amtrak and set up more trains

import jarray
import jmri

global TrainNW8997 
TrainNW8997 = jmri.util.FileUtil.getExternalFilename("scripts:MikeStartNW8997.py")
global TrainSW5488
TrainSW5488 = jmri.util.FileUtil.getExternalFilename("scripts:MikeStartSW5488.py")

class ExecuteTrains(jmri.jmrit.automat.AbstractAutomaton):

    def checkTrainDone(self):
        trainDone = memories.provideMemory("Train Done").getValue()
        while trainDone != "Yes":
            self.waitMsec(10000)
            trainDone = memories.provideMemory("Train Done").getValue()
        print("Escaped from the loop")
        memories.provideMemory("Train Done").setValue("No")
        return
        
    def init(self):    
        return

    def handle(self):
	memories.provideMemory("Train Done").setValue("No")
        execfile(TrainNW8997)
        self.checkTrainDone()
        execfile(TrainSW5488)
        self.checkTrainDone()
        #execfile(TrainNW8997)
        #self.checkTrainDone()
        return False

a = ExecuteTrains()

a.start()
