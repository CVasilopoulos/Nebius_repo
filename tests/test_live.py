import asyncio
import os
from dataclasses import replace

import pytest

from postmortem_pilot.client import TokenFactoryClient, UsageLedger
from postmortem_pilot.config import load_settings
from postmortem_pilot.jsonx import extract_json
from postmortem_pilot.pipeline import run_to_list
from postmortem_pilot.samples import list_samples

pytestmark = pytest.mark.skipif(not os.environ.get("NEBIUS_API_KEY"), reason="NEBIUS_API_KEY not set")


def client(settings):
    return TokenFactoryClient(settings.api_key, settings.base_url, UsageLedger(settings.usage_log))


@pytest.mark.parametrize("attr", ["extract_model", "verify_model", "reason_model"])
def test_each_nemotron_model_answers_json(attr):
    settings = load_settings()

    async def go():
        c = client(settings)
        try:
            return await c.chat(getattr(settings, attr), [{"role": "user", "content": 'Reply with JSON only: {"ok": true, "sum": 2+3 as an integer}'}], stage="live-test", max_tokens=600)
        finally:
            await c.aclose()

    result = asyncio.run(go())
    assert extract_json(result.content).get("sum") == 5
    assert int(result.usage["total_tokens"]) > 0


def test_full_pipeline_on_small_sample():
    settings = replace(load_settings(), reason_max_tokens=8000)
    sources = {s["id"]: s for s in list_samples(settings.samples_dir)}["expired-webhook-cert"]["sources"]
    c = client(settings)

    async def go():
        try:
            return await run_to_list(settings, c, sources)
        finally:
            await c.aclose()

    events = asyncio.run(go())
    types = [e["type"] for e in events]
    assert "error" not in types, [e for e in events if e["type"] in {"error", "warning"}]
    assert types[-1] == "done"
    timeline = next(e for e in events if e["type"] == "timeline")["events"]
    assert len(timeline) >= 4
    analysis = next(e for e in events if e["type"] == "analysis")["data"]
    assert analysis["root_cause"]["refs"]
    assert "issuer" in (analysis["root_cause"]["statement"] + analysis["trigger"]["statement"]).lower() or "cert" in analysis["root_cause"]["statement"].lower()
    verdicts = [e["verdict"] for e in events if e["type"] == "verdict"]
    assert verdicts and verdicts.count("unsupported") <= len(verdicts) // 2
    usage = next(e for e in events if e["type"] == "usage")["ledger"]
    print("LIVE_PIPELINE_TOKENS", usage["total_tokens"], usage["by_stage"])
