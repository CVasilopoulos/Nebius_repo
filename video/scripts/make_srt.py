import re, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
N = pathlib.Path(__file__).resolve().parent / "narration"
OUT = ROOT / "video" / "postmortem-pilot-demo.srt"

windows = [
    (1, 6.000000, 18.875465),
    (2, 20.875465, 36.839184),
    (3, 38.839184, 53.490975),
    (4, 55.490975, 71.710113),
    (5, 73.710113, 91.833288),
    (6, 93.833288, 109.982766),
    (7, 111.982766, 127.505306),
    (8, 129.505306, 145.051066),
]

def fmt(t):
    h = int(t // 3600); t -= h * 3600
    m = int(t // 60); t -= m * 60
    s = int(t)
    ms = round((t - s) * 1000)
    if ms == 1000:
        ms = 0; s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def split_text(text, max_len=84):
    sentences = [s.strip() for s in re.split(r'(?<=[.])\s+', text.strip()) if s.strip()]
    chunks = []
    for sent in sentences:
        words = sent.split()
        cur = ""
        for w in words:
            if len(cur) + len(w) + 1 > max_len:
                chunks.append(cur.strip())
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            chunks.append(cur.strip())
    return chunks

cues = []
for n, start, end in windows:
    text = (N / f"seg{n}.txt").read_text().strip().replace("\n", " ").replace("M I T", "MIT")
    chunks = split_text(text)
    total_chars = sum(len(c) for c in chunks) or 1
    dur = end - start
    t = start
    for c in chunks:
        share = len(c) / total_chars * dur
        c_end = t + share
        cues.append((t, c_end, c))
        t = c_end

lines = []
for i, (s, e, text) in enumerate(cues, 1):
    lines.append(str(i))
    lines.append(f"{fmt(s)} --> {fmt(e)}")
    lines.append(text)
    lines.append("")

OUT.write_text("\n".join(lines), encoding="utf-8")
print("wrote", OUT, "cues:", len(cues))
