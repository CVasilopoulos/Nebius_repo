import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from postmortem_pilot.config import load_settings
from postmortem_pilot.samples import list_samples

STATIC = ROOT / "static"
SAMPLES = ROOT / "samples"
DOCS = ROOT / "docs"


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def build() -> None:
    settings = load_settings()
    out_static = DOCS / "static"
    out_data = DOCS / "data"
    shutil.rmtree(out_static, ignore_errors=True)
    shutil.rmtree(out_data, ignore_errors=True)

    html = (STATIC / "index.html").read_text().replace('"/static/', '"static/')
    write(DOCS / "index.html", html)
    write(out_static / "style.css", (STATIC / "style.css").read_text())

    js = (STATIC / "app.js").read_text()
    marker = "const STATIC_MODE = false;"
    if marker not in js:
        raise SystemExit("STATIC_MODE flag not found in static/app.js")
    write(out_static / "app.js", js.replace(marker, "const STATIC_MODE = true;"))

    health = {
        "ok": True,
        "live": False,
        "models": {
            "extract": settings.extract_model,
            "reason": settings.reason_model,
            "verify": settings.verify_model,
        },
        "max_lines": settings.max_lines,
    }
    write(out_data / "health.json", json.dumps(health))

    samples = list_samples(SAMPLES)
    write(out_data / "samples.json", json.dumps(samples))

    recorded = 0
    for sample in samples:
        recording = SAMPLES / sample["id"] / "run.ndjson"
        if recording.exists():
            write(out_data / "samples" / sample["id"] / "run.ndjson", recording.read_text())
            recorded += 1

    print(f"built {DOCS}: {len(samples)} samples, {recorded} recordings")


if __name__ == "__main__":
    build()
