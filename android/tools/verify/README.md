Laptop-side checks of exports made by the on-device tests (run inside /tmp/opencode/vsc-test after
`tools/make_test_clips.sh`, the device tests, and pulling the outputs with
`adb exec-out run-as com.alexvulcu.videospeedcontrol cat cache/out/X.mp4 > X.mp4`).
Argument: path of the desktop's bundled ffprobe / ffmpeg (vendor/ffmpeg/linux-x64/).

- check_packets.py FFPROBE – lossless exports: packets bit-identical, timestamps, section borders
- check_pitch.py FFMPEG FILES… – sound: pitch per 0.5 s by zero crossings, length
- check_frames.py FFMPEG – re-encodes: every output frame shows the expected source frame
