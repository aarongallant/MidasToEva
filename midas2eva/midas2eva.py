#import sys
import os
import commands
from struct import pack
from math import floor
from os.path import basename
from collections import Counter
import xml.etree.cElementTree as ET
import re
import ast

# ATG October 2013:
# changed the 'l's in writeEVAFile to 'i's. This should allow us to
# use titan01 to convert the data files.


class MissingEvent(Exception):
    def __init__(self, cycleNumber):
        self.cycleNumber = cycleNumber

    def __str__(self):
        return ("Possible missing event near cycle number "
                + str(self.cycleNumber))


class MissingTDCOpen(Exception):
    def __init__(self, cycleNumber):
        self.cycleNumber = cycleNumber

    def __str__(self):
        return ("Missing TDCOpen event at cycle number "
                + str(self.cycleNumber))


class MissingTDCClose(Exception):
    def __init__(self, cycleNumber):
        self.cycleNumber = cycleNumber

    def __str__(self):
        return ("Missing TDCClose event at cycle number "
                + str(self.cycleNumber))


class MidasToEva:

    def __init__(self, filename):
        if os.path.isfile(filename) and filename.endswith('.mid'):
            self.status = 1
            self.filename = filename
        else:
            print(filename + " is not a valid MIDAS file.")
            self.status = 0

    def extractXML(self):
        if self.status:
            try:
                datafile = open(self.filename, 'r')
                data = datafile.read()
                datafile.close()

                startindex = data.find('<odb')
                endindex = data.find('</odb>') + 6
                self.domag = ET.fromstring(data[startindex:endindex])

                secstartindex = data.rfind('<odb')
                secendindex = data.rfind('</odb>') + 6
                self.dom2ag = ET.fromstring(data[secstartindex:secendindex])
            except IOError:
                print("Could not open " + self.filename)
                self.status = 0

    def getAttribute(self, xml, dirpath, dirname, keyname, castfunc=str):
        '''
        getAttribute(xml, dirpath, dirname, keyname, castfunc) searches the
        given ElementTree for the 'keyname' in the 'dirname' directory at
        the specified level 'dirpath'. 'castfunc' casts the returned result
        into the specified type. Default is to cast into a str.

        Example:
            /Experiment/Variables/Center Frequency
            dirpath = './dir/dir'        - Variables is 2 dirs from '/'
            dirname = 'Variables'        - name of the directory
            keyname = 'Center Frequency' - name of key to extract value from
        '''
        try:
            return castfunc(xml.find(dirpath + "/[@name='" + dirname + "']")
                            .find("key/[@name='" + keyname + "']").text)
        except:
            raise Exception("readmidas: Error accessing odb element: " +
                            dirpath + " " + dirname + " " + keyname)

    def getOdbVariable(self, xml, dirpath, dirname, keyname, castfunc,
                       var, varcastfunc):
        if var is not None:
            var = varcastfunc(var)
        else:
            var = self.getAttribute(xml, dirpath, dirname, keyname, castfunc)
        return var

    def getBaseFreq(self):
        if self.status == 1 and len(self.xmldata) > 0:
            elementlist = self.dom.getElementsByTagName('key')
            self.basefreq = -1

            for element in elementlist:
                if element.getAttribute('name') == 'Base Frequency':
                    self.basefreq = float(element.firstChild.data)

            if self.basefreq == -1:
                print 'Could not determine base frequency.'

    def getAmplitude(self, rfamp=None):
        self.amplitude = self.getOdbVariable(self.domag, './dir/dir',
                                             'Variables', 'MPETRFAmp', float,
                                             rfamp, float)
        print 'RF amplitude = ' + str(self.amplitude) + ' Volts'

    def getStartFreq(self, startf=None):
        # Need to use the second odb dump in the mid file
        # Commandline is in Hz, convert to MHz in varcastfunc
        self.startfreq = self.getOdbVariable(self.dom2ag, './dir/dir',
                                             'Variables', 'StartFreq (MHz)',
                                             float, startf,
                                             lambda x: float(x) / 1e6)
        self.startfreq *= 1e6
        print 'Start frequency = ' + str(self.startfreq) + ' Hertz'

    def getStopFreq(self, stopf=None):
        # Need to use the second odb dump in the mid file
        # Commandline is in Hz, convert to MHz in varcastfunc
        self.stopfreq = self.getOdbVariable(self.dom2ag, './dir/dir',
                                            'Variables', 'EndFreq (MHz)',
                                            float, stopf,
                                            lambda x: float(x) / 1e6)
        self.stopfreq *= 1e6
        print 'Stop frequency = ' + str(self.stopfreq) + ' Hertz'

    def getNumFreqSteps(self, nfreq=None):
        self.numfreqsteps = self.getOdbVariable(self.dom2ag,
                                                './dir/dir/dir/dir',
                                                'begin_ramp',
                                                'loop count',
                                                float,
                                                nfreq,
                                                float)
        print 'Number of frequency steps = ' + str(self.numfreqsteps)

    def getNumCycles(self, numcycles=None):
        self.numcycles = self.getOdbVariable(self.dom2ag,
                                             './dir/dir/dir/dir',
                                             'begin_scan',
                                             'loop count',
                                             float,
                                             numcycles,
                                             float)

    def getCycleTime(self):
        pass

    def getStartTime(self, startt=None):
        self.starttime = self.getOdbVariable(self.domag, './dir', 'Runinfo',
                                             'Start time binary', float,
                                             startt, float)
        print 'Start time = ' + str(self.starttime)

    def getEndTime(self, stopt=None):
        self.endtime = self.getOdbVariable(self.dom2ag, './dir', 'Runinfo',
                                           'Stop time binary', float,
                                           stopt, float)
        print 'End time = ' + str(self.endtime)

    def getElem(self, mass=None):
        self.mass = self.getOdbVariable(self.domag, './dir/dir', 'Variables',
                                        'Species', str, mass, str)
        print 'Element = ' + self.mass

    def getZ(self, Z=None):
        self.charge = self.getOdbVariable(self.domag, './dir/dir',
                                          'Variables', 'Charge', str,
                                          Z, str)

        self.charge = [int(x) for x in self.charge.split(';')]
        self.charge = self.charge[0]

        print 'Charge = ' + str(self.charge)

    def getRFTime(self, trf=None):
        '''if no trf value is passed, search the midas file for it.
           If a trf value is passed, use that value.

           Passed trf is in seconds.'''

        if trf is not None:
            # Commandline input is in ms, convert to s
            self.trf = float(trf) * 1000.0
        else:
            transNum = 2
            # loop over even multiples of 'transition_QUAD' to get all of the
            # rf times.
            self.trf = 0
            while True:
                try:
                    self.trf += self.getAttribute(self.domag,
                                                  "./dir/dir/dir/dir",
                                                  "transition_QUAD" +
                                                  str(transNum),
                                                  "time offset (ms)",
                                                  float)
                except:
                    # No more 'transition_QUAD's were found,
                    # so return the rftime
                    break
                transNum += 2

        # Convert from ms to sec
        self.trf /= 1000.

        print 'RF Time = ' + str(self.trf) + ' s'

    def setTdcGateWidth(self, tdcTime=None):
        self.tdcTime = self.getOdbVariable(self.domag, "./dir/dir/dir/dir",
                                           "pul_TDCGate", "pulse width (ms)",
                                           lambda x: float(x) * 1000.0,
                                           tdcTime, float)
        print 'TDC Gate Width = ' + str(self.tdcTime) + ' us'

    def collectMdumpData(self):
        '''
        collectMdumpData stores the output from the mdump program after a
        coarse pass through the data.

        The data is passed through twice. Once to extract the data for the
        MPET event bank, the second to extract any position data.
        '''
        comstring = 'mdump -b MPET -x ' + self.filename
        status, data = commands.getstatusoutput(comstring)

        self.mdumpdata = self.extractBankData('Bank:MPET', data)

        self.posdata = self.extractBankData('Bank:MCPP', data)

    def extractBankData(self, BankName, data):
        mdumpdata = []

        if BankName in data:
            for match in re.finditer(BankName, data):
                leftindex = match.end()
                tempindex = data.find('Length: ', leftindex)
                tempstring = data[tempindex + 8: tempindex + 18]
                temp = tempstring.split('(')
                numentries = int(temp[0]) / 4

                for counter in xrange(numentries):
                    midindex = data.find('0x', leftindex)
                    mdumpdata.append(data[midindex:midindex + 10])
                    leftindex = midindex + 1
        else:
            print 'No valid ' + BankName + ' banks found in file.'

        return mdumpdata

    def reorganizeMdumpData(self):
        '''
        reorganizeMdumpData() takes the raw mdump data and generates an array
        of tuples. Each tupole contains the 'event type', 'secondary type' and
        'tof' for each detected ion.

        event type = type of event. 8 or a = Start of TDC Gate, 1 or 3 = End
            of TDC Gate, 4 or 6 = Out of TDC Gate ion, 2 = In TDC Gate ion,
            0 = Timestamp.

        Event types 8, 1, and 4 are followed by timestamp events.
        '''
        if len(self.mdumpdata) == 0:
            print 'No mdump data available.  Run collectMdumpData().'
            return

        mdumparray = []
        errarray = []
        mdumpdata = self.mdumpdata

        arraylen = len(mdumpdata)

        # Extract Event type and timestamp
        for i in xrange(0, arraylen, 2):
            firsthex = mdumpdata[i]
            sechex = mdumpdata[i + 1]
            evtype = firsthex[2]
            if(evtype == 'a'):
                errarray.append(firsthex)
                evtype = '8'
            elif(evtype == '6'):
                errarray.append(firsthex)
                evtype = '4'
            elif(evtype == '3'):
                errarray.append(firsthex)
                evtype = '1'
            cyclenum = int(firsthex[3:6], 16)
            tof = float(int(sechex[2:], 16)) * 0.01
            temp = (int(evtype), cyclenum, tof)
            mdumparray.append(temp)
        self.mdumparray = mdumparray
        self.errarray = errarray

    def binMdumpData(self, binwidth=0.1, maxtof=100):
        '''
        binMdumpData bins the data collected from mdump.

        The binned data is saved as in array for each cycle.
        This array is then appended to a 'master' tof array
        that contains the tof info for each type of event.

        We also check to ensure that the event cycle counter
        is updated correctly through the MIDAS file. This
        checks if a TDCOpen or TDCClose event is missing,
        and also checks if there are any missing events.
        If a missing gate or event is detected, an
        exception will be thrown, and any further file
        conversion will be aborted.
        '''
        # binwidth and maxtof are in units of us

        cyclecounter = 0
        self.numchannels = int(maxtof / binwidth)
        self.bindata = []
        #tofbin=self.numchannels*[0]
        tofbin = []
        self.binwidth = binwidth

        for entry in self.mdumparray:
            if entry[0] == 8:
                startTdcGateCounter = entry[1]
                continue
            elif entry[0] == 1:
                endTdcGateCounter = entry[1]
                # Check that the start and end GateCounters are correct
                self.checkStartEndGateCounters(startTdcGateCounter,
                                               endTdcGateCounter,
                                               cyclecounter)

                #print endTdcGateCounter, (startTdcGateCounter % 1024)
                # Increment cycle counter
                cyclecounter = cyclecounter + 1

                # Check that cycle counter is updating correctly
                self.checkCycleCounter(startTdcGateCounter, cyclecounter)

                # Append tof bin data
                self.bindata.append(tofbin)

                # reset tof bin
                tofbin = []
                continue
            elif entry[0] == 4:
                continue
            else:
                if entry[2] < maxtof:
                    bin = int(floor(entry[2] / binwidth))
                    #tofbin[bin]=tofbin[bin]+1
                    tofbin.append(bin)

    def checkStartEndGateCounters(self, startTdcGateCounter,
                                  endTdcGateCounter, cyclecounter):
        '''Check if the start and end TDC gate counters are the same.
           If not, raise an exception with the cycle counter that
           gave the error.'''
        if startTdcGateCounter != endTdcGateCounter:
            print "ERROR: Gate counters out of sync."
            if startTdcGateCounter < endTdcGateCounter:
                print "ERROR: missing TDCGateOpen event"
                raise MissingTDCOpen(cyclecounter)
            else:
                print "ERROR: missing TDCGateClose event"
                raise MissingTDCClose(cyclecounter)

    def checkCycleCounter(self, startTdcGateCounter, cyclecounter):
        '''Check if the current cycle counter is correct.
        This will only catch cases where an extraction
        cycle is missed by the DAQ (i.e. counter 2 -> 4,
        where event 3 is missing from the data stream).'''
        # Cycle counter resets at 1024, so we check that the
        # mod of the GateCounter is correct
        if startTdcGateCounter != (cyclecounter % 1024):
            print "ERROR: Gate counters out of sync."
            print "ERROR: Possible event missing in MIDAS banks"
            raise MissingEvent(cyclecounter)

    def writeEvaFile(self, mass, charge, amp, extime,
                     path='/triumfcs/trshare/titan/MPET/Data/'):
        '''
        writeEVAFile writes the collected and binned mdump data to an EVA file.

        In order to determine the frequencies that were used the function
        'genFreqList' is called.
        '''

        evafilename = self.filename[:-4] + '_eva.dat'
        path = path + basename(evafilename)
        try:
            datafile = open(path, 'w')
        except IOError:
            print 'Could not open ' + path + ' for writing.'
            return

        # this will be the header length
        datafile.write(pack('i', 1))
        # this will be the start of the binary TOF data
        datafile.write(pack('i', 2))

        # Write the header info
        datafile.write('\n\n[Mass]\n Mass=' + self.mass +
                       ' ,Charge= ' + str(self.charge) + '\n\n')
        datafile.write('[Switch]\n NrCycles=-1\n\n')
        datafile.write('[Excit]\n Mass=' + self.mass +
                       ' ,Charge= ' + str(self.charge) + ',Freq =')
        datafile.write(str((self.stopfreq - self.startfreq) / 2) + ', Amp= ')
        datafile.write(str(self.amplitude) + ',Time=' + str(self.trf) + '\n\n')
        datafile.write('[MCA]\n MCA=sim,TimePerChannel=' + str(self.binwidth))
        datafile.write('\xB5' + 's,Channels= ' + str(self.numchannels))
        datafile.write(',Pipse=   0\n\n')
        datafile.write('[SCAN0]\n Dev=AFG, Fct=SetFrequency, Spec=,\n')
        datafile.write(' Start=' + str(self.startfreq))
        datafile.write(', Stop=' + str(self.stopfreq))
        datafile.write(', Step=' + str((self.stopfreq - self.startfreq)
                                       / self.numfreqsteps))
        datafile.write(', Unit=Hz\n\n[SCAN1]\n Dev=*, Fct=*, Spec=,\n')
        datafile.write(' Start=0.000000, Stop=0.000000,' +
                       'Step=1.000000, Unit=1\n\n')
        datafile.write('*---------------here the binary' +
                       'part begins---------------*\n')
        headerlen = int(datafile.tell()) - 8
        datafile.seek(0)
        datafile.write(pack('i', headerlen))
        datafile.seek(0, 2)

        datafile.write(pack('i', int(self.numfreqsteps)))

        # write the list of applied frequencies
        for freq in self.genFreqList():
            datafile.write(pack('d', freq))
        datafile.write(pack('i', 1))
        datafile.write(pack('d', 0))

        # get and write the position of the binary data start
        datastart = int(datafile.tell())
        datafile.seek(4)
        datafile.write(pack('i', datastart))
        datafile.seek(datastart)

        # Time that each frequncy point took
        dtime = (self.endtime - self.starttime) / float(len(self.bindata))

        # pack the data into a string to write later
        datastring = ''
        for i in xrange(len(self.bindata)):
            hist = Counter(self.bindata[i])
            numemptychan = self.numchannels - len(hist)
            # if there is lots of tof data then don't pack the data
            if numemptychan < self.numchannels / 2:
                datastring += (pack('h', self.numchannels * 2 + 4))
                datastring += (pack('i', self.starttime
                                    + float(i) * dtime))
                for j in hist:
                    datastring += (pack('h', hist[j]))
            # Not a lot of tof data, so pack the data
            else:
                datastring += (pack('h', (self.numchannels - numemptychan)
                                    * 4 + 4))
                datastring += (pack('i', self.starttime
                                    + float(i) * dtime))
                for j in hist:
                    datastring += (pack('h', j))
                    datastring += (pack('h', hist[j]))

        datafile.write(datastring)
        datafile.close()

    def writePosData(self, path='/titan/data5/mpet/tmp/'):
        if len(self.posdata) == 0:
            return

        posfilename = self.filename[:-4] + '_pos.dat'
        path = path + basename(posfilename)

        try:
            datafile = open(path, 'w')
        except IOError:
            print 'Could not open ' + path + ' for writing.'
            return

        for num in self.posdata:
            x = int(num[6:8], 16)
            y = int(num[8:10], 16)
            datafile.write(str(x) + ' ' + str(y) + '\n')

        datafile.close()

    def writeMdumpData(self, path='/triumfcs/trshare/titan/MPET/Data/'):
        dumpfilename = self.filename[:-4] + '_dump.dat'
        path = path + basename(dumpfilename)

        try:
            datafile = open(path, 'w')
        except IOError:
            print 'Could not open ' + path + ' for writing.'
            return
        for entry in self.mdumpdata:
            datafile.write(str(entry) + '\n')

        datafile.close()

    def writeErrorData(self, path='/triumfcs/trshare/titan/MPET/Data/'):
        if len(self.errarray) == 0:
            return

        errfilename = self.filename[:-4] + '_err.dat'
        path = path + basename(errfilename)

        if(len(self.errarray) > 0):
            try:
                datafile = open(path, 'w')
            except IOError:
                print 'Could not open ' + path + ' for writing.'
                return
            for entry in self.errarray:
                datafile.write(str(entry) + '\n')

            datafile.close()

    def genFreqList(self):
        '''
        genFreqList generates the frequency list to be written to the EVA file.

        First we try to read the 'Quad FreqList' variable in the midas file ODB
        dump.  If it exists then we generate the list.

        If it doesn't exist, then we use the start and stop frequencies and the
        number of steps to generate the frequency list.

        ATG: Tested 16.10.13 with file 187070.mid and 187036.mid
        '''
        FreqList = []
        try:
            fl = self.getAttribute(self.dom2ag, './dir/dir', 'Variables',
                                   'Quad FreqList')
            print fl
            fl = fl.split(';')
            print fl
            fl = [ast.literal_eval(x.strip()) for x in fl]
            print fl
            for x in fl:
                df = 2. * float(x[1]) / (float(x[2]) - 1.)
                for i in range(int(x[2])):
                    FreqList.append(float(x[0]) - float(x[1]) + i * df)
        except:
            dfreq = ((float(self.stopfreq) - float(self.startfreq))
                     / (float(self.numfreqsteps) - 1.))
            for i in range(int(self.numfreqsteps)):
                FreqList.append(float(self.startfreq) + i * dfreq)

        print FreqList
        return FreqList
