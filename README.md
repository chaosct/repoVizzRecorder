repoVizz Recorder
=================

Records signals, synchronizes video, and uploads data recordings to repoVizz.

Install dependencies with `pip install -r requirements.txt`.


Recording
---------

The script will generate a sound just before and after the recording. This will be used to synchonize the audio and video, so start recording the video file before starting the script and stop it at the end.

```
$ python repoVizzRecorder.py record riot #record data from a R-IoT
$ python repoVizzRecorder.py record bitalino #record data from a BITalino
```

Press `Ctrl-C` to stop recording. This will generate a `recording_N.zip` Datapack file.


Video Sync
----------

```
$ python repoVizzRecorder.py video video.mp4 recording_N.zip
```

This will locate the sounds from the recording phase and will cut the audio and video accordingly. It will generate the file `recording_N-AudioVideo.zip`.


Uploading
---------

You can upload directly to repoVizz with the script:

```
$ python repoVizzRecorder.py upload recording_N-AudioVideo.zip 
Please enter your repoVizz API key: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
repoVizz user: cfjulia
Datapack name: CLI upload 2
Datapack folder: SIC
{"status": "ok", "message": "Datapack recording_N-AudioVideo.zip processed ok"  , "url": "http://repovizz.upf.edu/repo/Vizz/1365"}
```

