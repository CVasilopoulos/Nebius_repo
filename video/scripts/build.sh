#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$ROOT/video/.work"
SCRIPTS="$ROOT/video/scripts"
VOICE="$WORK/voices/en_US-lessac-medium.onnx"

mkdir -p "$WORK/narration" "$WORK/build" "$ROOT/video/frames"

for i in 1 2 3 4 5 6 7 8; do
  python3 -m piper -m "$VOICE" -f "$WORK/narration/seg${i}.wav" < "$SCRIPTS/narration/seg${i}.txt"
done

ffmpeg -y -f lavfi -i anullsrc=r=22050:cl=mono -t 6.0 -c:a pcm_s16le "$WORK/narration/silence6.wav" -loglevel error
ffmpeg -y -f lavfi -i anullsrc=r=22050:cl=mono -t 2.0 -c:a pcm_s16le "$WORK/narration/silence2.wav" -loglevel error
ffmpeg -y -f lavfi -i anullsrc=r=22050:cl=mono -t 8.0 -c:a pcm_s16le "$WORK/narration/silence8.wav" -loglevel error

cat > "$WORK/narration/list.txt" << EOF
file 'silence6.wav'
file 'seg1.wav'
file 'silence2.wav'
file 'seg2.wav'
file 'silence2.wav'
file 'seg3.wav'
file 'silence2.wav'
file 'seg4.wav'
file 'silence2.wav'
file 'seg5.wav'
file 'silence2.wav'
file 'seg6.wav'
file 'silence2.wav'
file 'seg7.wav'
file 'silence2.wav'
file 'seg8.wav'
file 'silence8.wav'
EOF
(cd "$WORK/narration" && ffmpeg -y -f concat -safe 0 -i list.txt -c:a pcm_s16le narration_full.wav -loglevel error)

python3 "$SCRIPTS/record_demo.py"
BROWSER_WEBM=$(ls -t "$WORK/browser"/*.webm | head -1)

ffmpeg -y -loop 1 -i "$WORK/cards/title.png" -t 6.0 -r 25 -pix_fmt yuv420p -vf "scale=1920:1080" -an \
  -c:v libx264 -profile:v high -crf 18 "$WORK/build/title_clip.mp4" -loglevel error
ffmpeg -y -ss 1.058413 -i "$BROWSER_WEBM" -t 123.501587 -r 25 -pix_fmt yuv420p -vf "scale=1920:1080" -an \
  -c:v libx264 -profile:v high -crf 18 "$WORK/build/browser_clip.mp4" -loglevel error
ffmpeg -y -loop 1 -i "$WORK/cards/end.png" -t 23.545760 -r 25 -pix_fmt yuv420p -vf "scale=1920:1080" -an \
  -c:v libx264 -profile:v high -crf 18 "$WORK/build/end_clip.mp4" -loglevel error

cat > "$WORK/build/vlist.txt" << EOF
file 'title_clip.mp4'
file 'browser_clip.mp4'
file 'end_clip.mp4'
EOF
(cd "$WORK/build" && ffmpeg -y -f concat -safe 0 -i vlist.txt -c copy video_only.mp4 -loglevel error)

ffmpeg -y -i "$WORK/build/video_only.mp4" -i "$WORK/narration/narration_full.wav" \
  -map 0:v:0 -map 1:a:0 \
  -c:v libx264 -pix_fmt yuv420p -profile:v high -crf 18 -movflags +faststart \
  -c:a aac -b:a 160k -ar 44100 -ac 2 \
  -shortest \
  "$ROOT/video/postmortem-pilot-demo.mp4" -loglevel error

python3 "$SCRIPTS/make_srt.py"

ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 "$ROOT/video/postmortem-pilot-demo.mp4"
for t in 10 45 100 145; do
  ffmpeg -y -ss $t -i "$ROOT/video/postmortem-pilot-demo.mp4" -frames:v 1 -q:v 2 "$ROOT/video/frames/frame_${t}s.jpg" -loglevel error
done

echo "done: $ROOT/video/postmortem-pilot-demo.mp4"
