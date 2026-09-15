import asyncio
import json
from dataclasses import replace

from fastapi.testclient import TestClient

from postmortem_pilot.app import create_app
from postmortem_pilot.config import load_settings
from postmortem_pilot.pipeline import run_to_list
from postmortem_pilot.samples import list_samples
from tests.fakes import fake_client


def sample_sources():
    settings = load_settings()
    return {s["id"]: s for s in list_samples(settings.samples_dir)}["expired-webhook-cert"]["sources"]


def test_pipeline_end_to_end_with_fake_models():
    settings = replace(load_settings(), api_key="x")
    events = asyncio.run(run_to_list(settings, fake_client(), sample_sources()))
    types = [e["type"] for e in events]
    assert types[0] == "corpus" and types[-1] == "done"
    assert "error" not in types
    chunks = [e for e in events if e["type"] == "extract_chunk"]
    assert len(chunks) == 3 and all(c["dropped_refs"] == 1 for c in chunks)
    timeline = next(e for e in events if e["type"] == "timeline")["events"]
    assert all(not e["ref"].startswith("S99") for e in timeline)
    assert timeline == sorted(timeline, key=lambda e: e["ref"]) or len(timeline) == 9
    analysis = next(e for e in events if e["type"] == "analysis")["data"]
    assert analysis["root_cause"]["refs"] and "S42:7" not in analysis["root_cause"]["refs"]
    verdicts = {e["claim_id"]: e["verdict"] for e in events if e["type"] == "verdict"}
    assert verdicts["causal_chain-1"] == "unsupported"
    assert verdicts["root_cause"] == "partial"
    assert verdicts["trigger"] == "supported"
    report = next(e for e in events if e["type"] == "report")
    assert "# Postmortem: Disk full" in report["markdown"] and "NOT verified" in report["markdown"]
    usage = next(e for e in events if e["type"] == "usage")["ledger"]
    assert set(usage["by_stage"]) == {"extract", "reason", "verify"}
    assert usage["by_stage"]["extract"]["calls"] == 3


def test_api_streams_ndjson_and_rate_limits():
    settings = replace(load_settings(), runs_per_ip_per_day=1)
    app = create_app(settings, client_factory=fake_client)
    with TestClient(app) as http:
        assert http.get("/api/health").json()["live"] is True
        samples = http.get("/api/samples").json()
        assert any(s["id"] == "pgbackrest-disk-full" for s in samples)
        response = http.post("/api/analyze", json={"sources": sample_sources()})
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines() if line]
        assert events[-1]["type"] == "done" and all("t" in e for e in events)
        assert http.post("/api/analyze", json={"sources": sample_sources()}).status_code == 429
        assert http.get("/").status_code == 200
        assert http.get("/api/replay/does-not-exist").status_code == 404


def test_api_without_key_refuses_live_runs():
    app = create_app(replace(load_settings(), api_key=""))
    with TestClient(app) as http:
        assert http.get("/api/health").json()["live"] is False
        assert http.post("/api/analyze", json={"sources": [{"name": "a", "text": "b"}]}).status_code == 503
