import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from .client import TokenFactoryClient, UsageLedger
from .config import load_settings
from .pipeline import Pipeline


async def main() -> int:
    parser = argparse.ArgumentParser(prog="postmortem-pilot", description="Generate an evidence-grounded postmortem from log files.")
    parser.add_argument("paths", nargs="+", help="log files, or a sample folder")
    parser.add_argument("--record", help="write the event stream as NDJSON (used for replays)")
    parser.add_argument("--markdown", help="write the final report to this file")
    args = parser.parse_args()
    settings = load_settings()
    if not settings.live:
        print("NEBIUS_API_KEY is not set", file=sys.stderr)
        return 2
    files: list[Path] = []
    for raw in args.paths:
        path = Path(raw)
        files += sorted(p for p in path.iterdir() if p.suffix in {".log", ".txt"}) if path.is_dir() else [path]
    sources = [{"name": f.name, "text": f.read_text()} for f in files]
    client = TokenFactoryClient(settings.api_key, settings.base_url, UsageLedger(settings.usage_log))
    record = open(args.record, "w") if args.record else None
    started = time.perf_counter()
    status = 1
    try:
        async for event in Pipeline(settings, client).run(sources):
            event["t"] = round(time.perf_counter() - started, 3)
            if record:
                record.write(json.dumps(event) + "\n")
            kind = event["type"]
            if kind in {"stage", "extract_chunk", "verdict", "warning", "error"}:
                print(f"{event['t']:7.2f}s {kind:13} " + json.dumps({k: v for k, v in event.items() if k not in {'type', 't'}})[:220], file=sys.stderr)
            if kind == "report":
                if args.markdown:
                    Path(args.markdown).write_text(event["markdown"])
                else:
                    print(event["markdown"])
            if kind == "usage":
                print(json.dumps(event["ledger"], indent=2), file=sys.stderr)
            if kind == "done":
                status = 0
    finally:
        if record:
            record.close()
        await client.aclose()
    return status


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
