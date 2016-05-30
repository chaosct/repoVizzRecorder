import re
import os
import os.path
import time
import threading
# Data sources

# BITalino

import bitalino
import datetime

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

    labels = ["Digital/D0", "Digital/D1", "Digital/D2", "Digital/D3",
              "Analog/A0", "Analog/A2", "Analog/A3", "Analog/A4", "Analog/A5"]

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

    server.addMsgHandler("default", handle_data)

    yield dict(sampling_rate=1500)

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

class Record(object):
    def __init__(self, label, data, fname, conf):
        self.label = label
        self.min = data
        self.max = data
        self.fname = fname
        self.file = open(fname+'_0', 'wb')
        self.begin = time.clock()
        self.end = 0.0
        self.nelements = 0
        self.conf = conf
        self.add(data)
        self.framerate = 0

    def add(self, data):
        self.end = time.clock()
        self.min = min(self.min, data)
        self.max = max(self.max, data)
        self.nelements += 1
        self.file.write('{},'.format(data))

    def save(self):
        self.file.close()
        with open(self.fname,'wb') as realfile:
            print "Saving", self.label

            # minimum and maximum values!
            # repovizz assumes maxval > 0
            # and minval = 0 or minval = -maxval
            if self.max <= 0:
                if self.min < 0:
                    self.max = -self.min
                else:  # self.min == 0 and self.max == 0
                    self.min = -1
                    self.max = 1
            elif self.min >= 0:
                self.min = 0
            else:  # self.min < 0
                self.max = max(self.max, -self.min)
                self.min = -self.max

            print "\tdetected minval:", self.min
            print "\tdetected maxval:", self.max

            # detecting sampling rate

            rate = self.conf["sampling_rate"]
            if self.begin != self.end:
                rate = (self.nelements-1)/(self.end-self.begin)
                print "\tdetected framerate:", rate
            else:
                print "\tnot enough data to detect framerate, using specified:", rate

            self.framerate = rate

            # repovizz header

            realfile.write("repovizz,framerate={},minval={},maxval={}\n".format(rate, self.min, self.max))

            with open(self.fname+'_0', 'rb') as rfile:
                data = rfile.read(4096)
                while data:
                    realfile.write(data)
                    data = rfile.read(4096)
            os.remove(self.fname+'_0')


def record_a_source(source):
    s = source()
    conf = next(s)
    print "CONF:", conf
    records = {}
    mydir = "recording"
    i = 0
    while os.path.exists(mydir):
        mydir = "recording_{}".format(i)
        i += 1
    os.makedirs(mydir)
    print "Recording in", mydir
    running = True
    total_received = 0

    def reporter():
        last_reported = total_received
        while running:
            if total_received != last_reported:
                print "Received {} datapoints".format(total_received)
                last_reported = total_received
            time.sleep(1)

    thread = threading.Thread(target=reporter)
    thread.daemon = True
    thread.start()
    try:
        for label, data in s:
            if label not in records:
                print "Discovered signal: ", label
                records[label] = Record(label, data, os.path.join(mydir, sanitize_name(label)+'.csv'), conf)
            else:
                records[label].add(data)
            total_received += 1
    except KeyboardInterrupt:
        pass

    running = False
    thread.join()

    # let's save files

    for f in records.values():
        f.save()

    return mydir, records


import scipy.io.wavfile as wav
from moviepy.video.io.VideoFileClip import VideoFileClip
import numpy
import stft
from skimage.feature import match_template
import peakutils


def samples_to_seconds(index, overlap, sr):
    """Convert STFT window positions to seconds"""
    return index*(float(1024)/overlap)/sr


def detect_start_end_times(pattern_wav, recording_wav, sr, overlap):
    """Find matches for the start/end pattern within the recorded audio"""

    # Compute the STFT of the recordings
    specgram1 = numpy.array(stft.spectrogram(pattern_wav, overlap=overlap))
    specgram2 = numpy.array(stft.spectrogram(recording_wav, overlap=overlap))

    # Restrict the spectrum to the frequency band occupied by the start/end pattern
    pattern = abs(specgram1[7:16,:])
    recording = abs(specgram2[7:16,:])

    # Search for matches of the pattern in the input recording and return a confidence score
    # for each time position of the input recording
    confidence = match_template(recording, pattern)

    # Search for peaks in the confidence score, and choose the two highest peaks
    peaks = peakutils.indexes(confidence[0], thres=0.5, min_dist=50)
    start, end = sorted(peaks)
    return samples_to_seconds(start, overlap, sr), samples_to_seconds(end, overlap, sr)


def cut_video(recording_path, datapack_path):
    datapack_folder = os.path.dirname(datapack_path)

    # Read the start/end pattern
    sr1, pattern_wav = wav.read('pattern.wav')

    # Open the video file
    clip = VideoFileClip(recording_path)

    # Save its audio track temporarily on disk
    clip.audio.write_audiofile("temp_audio.wav")

    # Read the audio samples, mix down to mono (if necessary), and delete the temporary audio track
    sr2, recording_wav = wav.read('temp_audio.wav')
    if recording_wav.shape[1]>1:
        recording_wav = numpy.mean(recording_wav,1)
    os.remove('temp_audio.wav')

    # Detect the start and end audio pattern
    start, end = detect_start_end_times(pattern_wav, recording_wav, sr2, 4)

    # Cut the video and write it into two separate video and audio files
    clip.subclip(start+0.4, end).write_videofile(os.path.join(datapack_folder, 'temp','video.mp4'), codec='libx264')
    clip.subclip(start+0.4, end).audio.write_audiofile(os.path.join(datapack_folder, 'temp','audio.wav'))


import zipfile
import xml.etree.ElementTree as etree

def get_csv_duration(csv_path):
    with open(csv_path, 'r') as f:
        header = f.readline().split(",")
        data = f.readline()

    # Get the sampling rate and number of samples
    if header[1][-1]=='\n':
        sr = float(header[1][-5:-1])
    else:
        sr = float(header[1][-4:])

    num_samples = float(data.count(","))

    return float(num_samples)*(1/sr)

# Zips an entire directory using zipfile
def zipdir(path, zip_handle):
    for root, dirs, files in os.walk(path):
        for file in files:
            zip_handle.write(os.path.join(root, file),file)

def modify_datapack(datapack_path, recording_path):
    datapack_folder = os.path.dirname(datapack_path)

    # Unzip the datapack into a temp folder
    with zipfile.ZipFile(datapack_path, "r") as z:
        z.extractall(os.path.join(datapack_folder, 'temp'))

    # Get the duration of each csv file, and it
    durations = []
    for f in os.listdir(os.path.join(datapack_folder, 'temp')):
        if f.endswith(".csv"):
            durations.append(get_csv_duration(os.path.join(datapack_folder,'temp',f)))

    print 'Datapack length (according to the .csv files): ' + ''.join(str(e) for e in list(set(durations)))

    sr, audiofile = wav.read(os.path.join(datapack_folder, 'temp','audio.wav'))
    num_channels = audiofile.shape[1]

    # Load the XML file
    tree = etree.parse(os.path.join(datapack_folder, 'temp', 'LoggedData.xml'))
    root = tree.getroot()

    # Create a External node
    external_node = etree.Element('Generic')
    external_node.set('Category', 'External')
    external_node.set('Expanded', '1')
    external_node.set('ID', 'ROOT0_Exte0')
    external_node.set('Name', 'External video and audio')
    external_node.set('_Extra', '')

    # Create an Audio node
    audio_node = etree.Element('Audio')
    audio_node.set('BytesPerSample', '2')
    audio_node.set('Category', 'Camera audio')
    audio_node.set('DefaultPath', '0')
    audio_node.set('EstimatedSampleRate', '0.0')
    audio_node.set('Expanded', '1')
    audio_node.set('FileType', 'WAV')
    audio_node.set('Filename', 'audio.wav')
    audio_node.set('FrameSize', '1')
    audio_node.set('ID', 'ROOT0_Exte0_Micr0')
    audio_node.set('Name', 'Audio')
    audio_node.set('NumChannels', str(num_channels))
    audio_node.set('NumSamples', str(audiofile.shape[0]))
    audio_node.set('ResampledFlag', '-1')
    audio_node.set('SampleRate', str(sr))
    audio_node.set('SpecSampleRate', '0.0')
    audio_node.set('_Extra', 'canvas=-1,color=0,selected=1')
    external_node.insert(0, audio_node)

    # Create a Video node
    video_node = etree.Element('Video')
    video_node.set('Category', 'HQ')
    video_node.set('DefaultPath', '0')
    video_node.set('Expanded', '1')
    video_node.set('FileType', 'MP4')
    video_node.set('Filename', 'video.mp4')
    video_node.set('ID', 'ROOT0_Exte0_HQ0')
    video_node.set('Name', 'Video')
    video_node.set('_Extra', 'canvas=-1,color=0,selected=1')
    external_node.insert(1, video_node)

    root.insert(0,external_node)

    # Write the updated XML structure
    with open(os.path.join(datapack_folder, 'temp', 'LoggedData.xml'), "w") as text_file:
        text_file.write(etree.tostring(root))

    # Re-zip the datapack
    with zipfile.ZipFile(datapack_path[:-4]+'_video_audio.zip', 'w') as z:
        zipdir(os.path.join(datapack_folder, 'temp'), z)

import requests

def upload_datapack(filename):
    # Read the api key from disk
    with open('assets/api_key.txt', 'r') as myfile:
        api_key=myfile.read().replace('\n', '')

    # Construct the HTTP request payload
    payload = {
        'name': 'Treadmill with video ('+datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")+')',
        'folder': 'Reactable_tests',
        'user': 'panpap',
        'desc': '-',
        'api_key': api_key,
        'keywords': 'audio, video, coremotion',
        'computeaudiodesc': '0',
        'computemocapdesc': '0',
        'computesourceseparation': '0',
        'file': open(filename,'rb')}

    # Open an HTTP session
    s = requests.Session()

    # Upload the datapack
    r = s.post("http://repovizz.upf.edu/repo/api/datapacks/upload",files=payload,stream=True)

    print r.text


def enumerate_siblings(father_node, child_node):
    """ Calculates the number of nodes on the same level that will have the same ID, and returns the final number to be
    appended (_0, _1 etc) """
    siblings = father_node.findall("./")
    sibling_counter = 0
    for node in siblings:
        if node.get('Category')[:4]==child_node.get('Category')[:4]:
            sibling_counter += 1
    return father_node.get('ID')+'_'+child_node.get('Category')[:4]+str(sibling_counter-1)


def create_recorded_xml():
    mypath, records = record_a_source(R_IoT_source)

    IDS = {}

    ROOT = etree.Element("ROOT")
    ROOT.set("ID", "ROOT0")
    for record in records.values():
        labelcomponents = record.label.strip('/').split('/')
        label = labelcomponents[-1]
        groups = labelcomponents[:-1]
        root = ROOT
        prev = ["ROOT0"]
        for g in groups:
            node = None
            name = g
            prev.append(g)
            node = IDS.get('_'.join(prev))
            if not node:
                node = etree.SubElement(root, "Generic", attrib=dict(
                    Name=name,
                    Category="SensorGroup",
                    _Extra="",
                    Expanded="1"
                ))
                node.set('ID', enumerate_siblings(root, node))
                IDS['_'.join(prev)] = node

            root = node
        node = etree.SubElement(root, "Signal", attrib=dict(
            NumSamples="",
            Name=label,
            BytesPerSample="",
            _Extra="canvas=-1,color=0,selected=1",
            Category="Sensor",
            FileType="CSV",
            FrameSize="",
            DefaultPath="0",
            SpecSampleRate="0.0",
            EstimatedSampleRate="0.0",
            MaxVal="",
            Filename=os.path.basename(record.fname),
            NumChannels="",
            ResampledFlag="-1",
            MinVal="",
            Expanded="1",
            SampleRate=str(record.framerate)
        ))
        node.set('ID', enumerate_siblings(root, node))

    # Write the updated XML structure
    with open(os.path.join(mypath, 'LoggedData.xml'), "w") as text_file:
        text_file.write(etree.tostring(ROOT))

    with zipfile.ZipFile(mypath+'.zip', 'w') as z:
        zipdir(mypath, z)




if __name__ == "__main__":
    # test_a_source(R_IoT_source)
    #record_a_source(R_IoT_source)
    create_recorded_xml()