import os
import os.path
from tempfile import mkdtemp
import re
# Data sources

# BITalino

import bitalino

try:
    import bluetooth
except ImportError:
    bluetooth = None

# config: possible BITalino serial devices
#
devices = ["/dev/rfcomm0", "/dev/tty.bitalino-DevB", "/dev/tty.BITalino-DevB"]
BITalino_SamplingRate = 1000
BITalino_nSamples = 50


def BITalino_source():
    BITalino_macAddr = None
    for d in devices:
        if os.path.exists(d):
            BITalino_macAddr = d
    if not BITalino_macAddr:
        print "ERROR: DEVICE NOT FOUND"
        print "list of possible devices:"
        print "\n".join(devices)
        print
        print "May be you want to run:"
        print "$ sudo rfcomm connect rfcomm0"
        exit(1)

    # setting up BITalino
    device = bitalino.BITalino()
    if not device.open(BITalino_macAddr, BITalino_SamplingRate):
        print "Error opening BITalino"
        print "addr: {} , sampling rate: {}".format(BITalino_macAddr, BITalino_SamplingRate)
        exit()

    # print "Device version:"
    # print device.version()
    # Start Acquisition in all Analog Channels
    device.start()

    # first yield is conf
    yield dict(sampling_rate=BITalino_SamplingRate)

    labels = ["D0", "D1", "D2", "D3", "A0", "A2", "A3", "A4", "A5"]

    # led ON
    #    device.trigger([0,0,0,1])
    while True:
        data = device.read(BITalino_nSamples)
        for n in range(data.shape[1]):
            for signal, label in enumerate(labels):
                yield label, data[signal][n]

    # device.stop()
    # device.close()

# R-IoT

import OSC


def R_IoT_source():
    OSC.OSCServer.timeout = None # this is ugly, but you should be able to modify this in the constructor...
    server = OSC.OSCServer(("", 8888))
    lastdata = []

    def handle_data(addr, tags, data, client_address):
        for n, element in enumerate(data):
            lastdata.append(("{}/{}".format(addr,n), element))

    server.addDefaultHandlers("default", handle_data)

    yield dict(sampling_rate=100)

    while True:
        server.handle_request()
        for d in lastdata:
            yield d
        lastdata[:] = []


def test_a_source(source):
    s = source()
    conf = next(s)
    for label, data in s:
        print label, data

sanitize_name_pattern = re.compile('[\W_]+')
def sanitize_name(n):
    return sanitize_name_pattern.sub('_', n)

def record_a_source(source):
    s = source()
    conf = next(s)
    print "CONF:", conf
    minmax = {}
    files = {}
    mydir = "recording"
    i = 0
    while os.path.exists(mydir):
        mydir = "recording_{}".format(i)
        i += 1
    os.makedirs(mydir)
    print "Recording in", mydir
    try:
        for label, data in s:
            if label not in minmax:
                minmax[label]=(data,data)
                files[label] = open(os.path.join(mydir,sanitize_name(label)+'.csv_0'),'wb')
            else:
                mi, ma = minmax[label]
                minmax[label] = (min(mi,data),max(ma,data))
            files[label].write('{},\n'.format(data))
    except KeyboardInterrupt:
        pass

    # let's close files

    for f in files.values():
        f.close()

    # let's create the real csv

    for label, mm in minmax.items():
        fname = os.path.join(mydir,sanitize_name(label)+'.csv')
        with open(fname,'wb') as realfile:
            realfile.write("min={},max={}\n".format(*mm))
            with open(fname+'_0','rb') as rfile:
                for l in rfile:
                    realfile.write(l)
            os.remove(fname+'_0')





if __name__ == "__main__":
    record_a_source(BITalino_source)