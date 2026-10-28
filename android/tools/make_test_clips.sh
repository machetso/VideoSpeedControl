#!/usr/bin/env bash
# Synthetic test clips for the on-device tests, made with the desktop's bundled FFmpeg
# (no private footage). Usage: tools/make_test_clips.sh [OUTDIR]  (default /tmp/opencode/vsc-test)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FF="$ROOT/vendor/ffmpeg/linux-x64/ffmpeg"
OUT="${1:-/tmp/opencode/vsc-test}"
mkdir -p "$OUT"
cd "$OUT"
# BT.709 like real recordings (untagged HD is read as BT.601 by FFmpeg but as BT.709 by Android)
C709=(-vf "scale=out_color_matrix=bt709:out_range=tv" -colorspace bt709 -color_primaries bt709 -color_trc bt709)

# HEVC 240 fps, 960 frames, GOP 48, B-frames (x265 default open GOP)
"$FF" -v error -y -f lavfi -i "testsrc2=size=1280x720:rate=240:duration=4" \
    -c:v libx265 -preset fast -x265-params "keyint=48:min-keyint=48:bframes=4:log-level=error" \
    "${C709[@]}" -pix_fmt yuv420p -tag:v hvc1 synth_hevc240.mp4

# HEVC 240 fps with closed GOPs (every keyframe is an IDR → safe joins for the smart export)
"$FF" -v error -y -f lavfi -i "testsrc2=size=1280x720:rate=240:duration=4" \
    -c:v libx265 -preset fast -x265-params "keyint=48:min-keyint=48:bframes=0:open-gop=0:log-level=error" \
    "${C709[@]}" -pix_fmt yuv420p -tag:v hvc1 synth_hevc_closed.mp4

# H.264 120 fps, 360 frames, GOP 60, B-frames, rotation 90°
"$FF" -v error -y -f lavfi -i "testsrc2=size=1280x720:rate=120:duration=3" \
    -c:v libx264 -preset fast -g 60 -bf 3 "${C709[@]}" -pix_fmt yuv420p tmp_avc.mp4
"$FF" -v error -y -display_rotation 90 -i tmp_avc.mp4 -c copy synth_avc120_rot.mp4
rm tmp_avc.mp4

# Sound tests (pitch measured by zero crossings):
# 240 fps, 4 s, 1000 Hz tone, AAC 48 kHz stereo
"$FF" -v error -y -f lavfi -i "testsrc2=size=640x360:rate=240:duration=4" \
    -f lavfi -i "sine=frequency=1000:sample_rate=48000:duration=4" \
    -c:v libx264 -preset fast -g 48 -pix_fmt yuv420p -c:a aac -b:a 192k -ac 2 -shortest synth_tone240.mp4
# Fake phone slow-mo: tagged 120 fps capture, stored at 30 fps (8 s = 2 s real time),
# sound slowed 4× like a phone does: 250 Hz in the file = 1000 Hz real
"$FF" -v error -y -f lavfi -i "testsrc2=size=640x360:rate=30:duration=8" \
    -f lavfi -i "sine=frequency=250:sample_rate=48000:duration=8" \
    -c:v libx264 -preset fast -g 30 -pix_fmt yuv420p -c:a aac -b:a 192k -ac 2 -shortest \
    -movflags use_metadata_tags -metadata com.android.capture.fps=120.000000 synth_slowmo.mp4

# Sound sync: 240 fps, 4 s, a click every 0.5 s (= every 120 frames) over a quiet 300 Hz tone
"$FF" -v error -y -f lavfi -i "testsrc2=size=320x180:rate=240:duration=4" \
    -f lavfi -i "aevalsrc='if(lt(mod(t,0.5),0.0005)*gt(t,0.1),0.9,0)+0.02*sin(2*PI*300*t)':s=48000:d=4" \
    -c:v libx264 -preset fast -g 24 "${C709[@]}" -pix_fmt yuv420p -c:a aac -b:a 192k -ac 2 -shortest \
    synth_clicks240.mp4
ls -la "$OUT"
