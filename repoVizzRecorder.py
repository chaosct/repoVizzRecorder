import os.path

# Data sources

# BITalino

import bitalino

try:
    import bluetooth
except ImportError:
    bluetooth = None

# config: possible BITalino serial devices
#
devices = ["/dev/rfcomm0", "/dev/tty.bitalino-DevB"]
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
        for n in range(data.shape()[1]):
            for signal, label in enumerate(labels):
                yield label, data[signal][data]

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

if __name__ == "__main__":
    test_a_source(R_IoT_source)