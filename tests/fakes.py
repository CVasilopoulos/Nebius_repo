import json
import re

import httpx

from postmortem_pilot.client import TokenFactoryClient, UsageLedger


def fake_handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    model = body["model"]
    system = body["messages"][0]["content"]
    user = body["messages"][1]["content"]
    if "log triage" in system:
        refs = re.findall(r"^\[(S\d+:\d+)\]", user, re.M)
        events = [{"ref": r, "time": "", "kind": "error" if i == 0 else "info", "summary": f"event {r}"} for i, r in enumerate(refs[:3])]
        events.append({"ref": "S99:1", "kind": "error", "summary": "hallucinated"})
        content = "```json\n" + json.dumps({"events": events}) + "\n```"
    elif "postmortem" in system and "fact-checker" not in system:
        refs = re.findall(r"^\[(S\d+:\d+)\] \d", user, re.M) or re.findall(r"\[(S\d+:\d+)\]", user)
        content = json.dumps({
            "title": "Disk full",
            "severity": "SEV2",
            "summary": "The disk filled up.",
            "impact": {"statement": "Logins failed", "refs": refs[:1]},
            "window": {"start": "a", "end": "b"},
            "trigger": {"statement": "Archive failed", "refs": refs[:1]},
            "root_cause": {"statement": "Retention too long", "refs": refs[1:2] + ["S42:7"]},
            "causal_chain": [{"statement": "step one", "refs": refs[:1]}, {"statement": "step two", "refs": []}],
            "contributing_factors": [{"statement": "Alert routed to null", "refs": refs[-1:]}],
            "red_herrings": [],
            "detection": {"statement": "Paged late", "refs": refs[-1:]},
            "resolution": {"statement": "Expired backups", "refs": refs[-1:]},
            "action_items": [{"action": "Lower retention", "type": "prevent", "priority": "P0"}],
            "open_questions": ["Why was retention 4?"],
        })
    else:
        verdict = "partial" if "Retention" in user else "supported"
        content = json.dumps({"verdict": verdict, "reason": "lines show it"})
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "completion_tokens_details": {"reasoning_tokens": 20}}
    return httpx.Response(200, json={"choices": [{"message": {"content": content, "reasoning_content": "thinking"}, "finish_reason": "stop"}], "usage": usage, "model": model})


def fake_client(handler=fake_handler) -> TokenFactoryClient:
    return TokenFactoryClient("test-key", "https://example.invalid/v1", UsageLedger(), transport=httpx.MockTransport(handler))
