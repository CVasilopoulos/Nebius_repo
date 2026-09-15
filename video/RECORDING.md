# Regenerating the demo video

Output: `postmortem-pilot-demo.mp4` (1920x1080, H.264 + AAC stereo, ~2:33), `postmortem-pilot-demo.srt`, `frames/*.jpg`.
Built entirely from the bundled replay recording (`samples/pgbackrest-disk-full/run.ndjson`) — no Nebius API key involved.

## One-time setup

```bash
cd nebius-hackathon
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install playwright piper-tts
playwright install chromium

mkdir -p video/.work/voices
curl -fL -o video/.work/voices/en_US-lessac-medium.onnx \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
curl -fL -o video/.work/voices/en_US-lessac-medium.onnx.json \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"
```

ffmpeg must be on PATH (`brew install ffmpeg` on macOS). No `NEBIUS_API_KEY` should be set — the app must start in replay-only mode.

## Regenerate

```bash
. .venv/bin/activate
uvicorn postmortem_pilot.app:app --port 8080 --host 127.0.0.1 &
sleep 2
bash video/scripts/build.sh
kill %1
```

`build.sh` does everything: synthesizes the 8 narration lines in `scripts/narration/*.txt` with Piper, builds silence padding, drives a real Chromium browser (Playwright, headless, 1920x1080) through the app's replay mode following `VIDEO_SCRIPT.md`'s shot list, renders the title/end cards from `scripts/cards/*.html`, concatenates everything with ffmpeg, muxes the narration track, writes the `.srt`, and pulls 4 verification frames into `video/frames/`.

Intermediate files live in `video/.work/` (gitignored-worthy scratch dir; safe to delete after a successful build).

## How the pacing works

The real replay of the bundled run finishes in ~27 seconds (see the `t` fields in `run.ndjson`); the narration is deliberately slower and more explanatory. `record_demo.py` does not click "Replay recorded run" and wait on real timing — it loads the recorded events into the page and replays them itself through the app's own `handle()` renderer, on a piecewise-linear time warp so that the Extract/Reason/Verify stages roughly line up with the narration segments that talk about them (segment durations were measured from the actual Piper output, see the `windows` list in `make_srt.py`). Every value shown on screen is still from the one real recorded run — only the pacing is synthetic.

## If you change the narration text

1. Edit `scripts/narration/seg*.txt`.
2. Re-run Piper for the changed segments and re-check durations with `ffprobe -show_entries format=duration seg*.wav`.
3. Update the `windows` list in `make_srt.py` and the scene `time.sleep(...)` calls in `record_demo.py` to match the new durations (each scene's sleep = its segment's audio duration + a small gap; see the comments-free but sequential structure of the script — scene boundaries are in the same order as `VIDEO_SCRIPT.md`'s shot list).
4. Re-run `bash video/scripts/build.sh`.

## Voice

Piper TTS, voice `en_US-lessac-medium` (single-speaker, Apache-2.0 licensed, downloaded from the `rhasspy/piper-voices` model repo on Hugging Face).

## Captions

Sidecar only (`postmortem-pilot-demo.srt`), not burned in. Upload it alongside the video as a YouTube caption track.
