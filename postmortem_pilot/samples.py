import json
from pathlib import Path


def list_samples(directory: Path) -> list[dict]:
    samples = []
    if not directory.is_dir():
        return samples
    for folder in sorted(p for p in directory.iterdir() if p.is_dir()):
        meta_file = folder / "meta.json"
        if not meta_file.exists():
            continue
        meta = json.loads(meta_file.read_text())
        sources = [{"name": f.name, "text": f.read_text()} for f in sorted(folder.iterdir()) if f.suffix in {".log", ".txt"}]
        samples.append({"order": meta.get("order", 99), "id": folder.name, "title": meta.get("title", folder.name), "description": meta.get("description", ""), "sources": sources, "has_recording": (folder / "run.ndjson").exists()})
    return sorted(samples, key=lambda s: (s["order"], s["id"]))


def recording_path(directory: Path, sample_id: str) -> Path | None:
    if not sample_id.replace("-", "").replace("_", "").isalnum():
        return None
    path = directory / sample_id / "run.ndjson"
    return path if path.exists() else None
