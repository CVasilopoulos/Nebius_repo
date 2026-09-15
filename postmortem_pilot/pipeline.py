import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from .client import TokenFactoryClient, TokenFactoryError
from .config import Settings
from .jsonx import extract_json
from .logs import Corpus, LogLine, build_corpus, chunk, render, timestamp_key
from . import prompts
from .report import to_markdown

KINDS = {"error", "warning", "change", "alert", "recovery", "info"}
VERDICTS = {"supported", "partial", "unsupported"}
CLAIM_SECTIONS = ("trigger", "root_cause", "causal_chain", "contributing_factors", "red_herrings", "detection", "resolution", "impact")


@dataclass
class Claim:
    id: str
    section: str
    statement: str
    refs: list[str]


def approx_tokens(chars: int) -> int:
    return max(1, chars // 4)


def normalise_ref(ref) -> str:
    return str(ref or "").strip().strip("[]").replace(" ", "")


def clip_text(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in (". ", "! ", "? "):
        index = cut.rfind(sep)
        if index != -1:
            return cut[:index + 1]
    index = cut.rfind(" ")
    return cut[:index] if index != -1 else cut


def clean_events(payload, valid: dict[str, LogLine]) -> tuple[list[dict], int]:
    items = payload.get("events", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []
    events, dropped = [], 0
    for item in items:
        if not isinstance(item, dict):
            dropped += 1
            continue
        ref = normalise_ref(item.get("ref"))
        if ref not in valid:
            dropped += 1
            continue
        kind = str(item.get("kind") or "info").lower()
        events.append({
            "ref": ref,
            "time": str(item.get("time") or "")[:40],
            "kind": kind if kind in KINDS else "info",
            "summary": str(item.get("summary") or valid[ref].text)[:240],
            "sort": timestamp_key(valid[ref].text) or timestamp_key(str(item.get("time") or "")),
        })
    return events, dropped


def merge_timeline(events: list[dict], valid: dict[str, LogLine]) -> list[dict]:
    seen: dict[str, dict] = {}
    for event in events:
        seen.setdefault(event["ref"], event)
    order = {ref: index for index, ref in enumerate(valid)}
    return sorted(seen.values(), key=lambda e: (e["sort"] or "9999", order.get(e["ref"], 0)))


def collect_claims(analysis: dict, valid: dict[str, LogLine]) -> list[Claim]:
    claims: list[Claim] = []
    for section in CLAIM_SECTIONS:
        value = analysis.get(section)
        items = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        cleaned = []
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not str(item.get("statement") or "").strip():
                continue
            refs = [r for r in (normalise_ref(x) for x in (item.get("refs") or []) if x) if r in valid]
            item["refs"] = refs
            claim_id = f"{section}-{index}" if isinstance(value, list) else section
            item["id"] = claim_id
            cleaned.append(item)
            claims.append(Claim(claim_id, section, str(item["statement"]), refs))
        if isinstance(value, list):
            analysis[section] = cleaned
    return claims


def cited_lines(refs: list[str], valid: dict[str, LogLine]) -> list[LogLine]:
    return [valid[r] for r in dict.fromkeys(refs) if r in valid]


class Pipeline:
    def __init__(self, settings: Settings, client: TokenFactoryClient):
        self.settings = settings
        self.client = client

    async def run(self, sources: list[dict]) -> AsyncIterator[dict]:
        s = self.settings
        corpus = build_corpus(sources, s.max_lines)
        valid = corpus.by_ref()
        yield {"type": "corpus", "sources": corpus.sources, "lines": {l.ref: l.text for l in corpus.lines}, "redactions": corpus.redactions, "truncated": corpus.truncated}
        if not corpus.lines:
            yield {"type": "error", "message": "No log lines to analyse."}
            return

        chunks = chunk(corpus, s.chunk_lines)
        yield {"type": "stage", "stage": "extract", "status": "start", "model": s.extract_model, "calls": len(chunks)}
        names = {src["id"]: src["name"] for src in corpus.sources}
        semaphore = asyncio.Semaphore(s.extract_concurrency)

        async def extract(index: int, lines: list[LogLine]):
            async with semaphore:
                result = await self.client.chat(
                    s.extract_model,
                    [{"role": "system", "content": prompts.EXTRACT_SYSTEM}, {"role": "user", "content": prompts.EXTRACT_USER.format(source_name=names[lines[0].source_id], lines=render(lines))}],
                    stage="extract", max_tokens=s.extract_max_tokens, temperature=0.1, thinking=s.extract_thinking,
                )
                events, dropped = clean_events(extract_json(result.content), valid)
                return index, events, dropped, result

        all_events: list[dict] = []
        failures = 0
        tasks = [asyncio.create_task(extract(i, c)) for i, c in enumerate(chunks)]
        for future in asyncio.as_completed(tasks):
            try:
                index, events, dropped, result = await future
            except (TokenFactoryError, ValueError) as exc:
                failures += 1
                yield {"type": "warning", "stage": "extract", "message": str(exc)[:300]}
                continue
            all_events.extend(events)
            yield {"type": "extract_chunk", "index": index, "source": names[chunks[index][0].source_id], "lines": len(chunks[index]), "events": len(events), "dropped_refs": dropped, "seconds": round(result.seconds, 2), "tokens": int(result.usage.get("total_tokens") or 0)}
        if failures == len(chunks):
            yield {"type": "error", "message": "Event extraction failed for every chunk."}
            return
        timeline = merge_timeline(all_events, valid)
        yield {"type": "timeline", "events": [{k: v for k, v in e.items() if k != "sort"} for e in timeline]}
        yield {"type": "stage", "stage": "extract", "status": "done"}

        evidence = cited_lines([e["ref"] for e in timeline], valid)
        timeline_text = "\n".join(f"[{e['ref']}] {e['time']} {e['kind'].upper()}: {e['summary']}" for e in timeline)
        sources_text = "\n".join(f"{src['id']}: {src['name']} ({src['lines']} lines)" for src in corpus.sources)
        reason_prompt = prompts.REASON_USER.format(sources=sources_text, timeline=timeline_text, evidence=render(evidence))
        yield {"type": "stage", "stage": "reason", "status": "start", "model": s.reason_model, "context_tokens_estimate": approx_tokens(len(reason_prompt)), "raw_tokens_estimate": approx_tokens(corpus.raw_chars)}
        analysis = None
        for attempt in range(2):
            try:
                result = await self.client.chat(
                    s.reason_model,
                    [{"role": "system", "content": prompts.REASON_SYSTEM}, {"role": "user", "content": reason_prompt}],
                    stage="reason", max_tokens=s.reason_max_tokens, temperature=0.3,
                )
                analysis = extract_json(result.content)
                if isinstance(analysis, dict):
                    break
                analysis = None
            except (TokenFactoryError, ValueError) as exc:
                yield {"type": "warning", "stage": "reason", "message": str(exc)[:300]}
        if analysis is None:
            yield {"type": "error", "message": "The reasoning model did not return a usable analysis."}
            return
        claims = collect_claims(analysis, valid)
        yield {"type": "analysis", "data": analysis, "seconds": round(result.seconds, 2), "reasoning_tokens": int(((result.usage.get("completion_tokens_details") or {}).get("reasoning_tokens")) or 0)}
        yield {"type": "stage", "stage": "reason", "status": "done"}

        yield {"type": "stage", "stage": "verify", "status": "start", "model": s.verify_model, "calls": sum(1 for c in claims if c.refs)}
        verify_semaphore = asyncio.Semaphore(s.verify_concurrency)

        async def verify(claim: Claim):
            if not claim.refs:
                return claim, "unsupported", "No valid log lines were cited.", None
            async with verify_semaphore:
                result = await self.client.chat(
                    s.verify_model,
                    [{"role": "system", "content": prompts.VERIFY_SYSTEM}, {"role": "user", "content": prompts.VERIFY_USER.format(claim=claim.statement, lines=render(cited_lines(claim.refs, valid)))}],
                    stage="verify", max_tokens=s.verify_max_tokens, temperature=0.0, thinking=s.verify_thinking,
                )
                payload = extract_json(result.content)
                verdict = str(payload.get("verdict", "")).lower() if isinstance(payload, dict) else ""
                reason = clip_text(str(payload.get("reason", "")), 480) if isinstance(payload, dict) else ""
                return claim, verdict if verdict in VERDICTS else "partial", reason, result

        counts = {"supported": 0, "partial": 0, "unsupported": 0}
        verdicts: dict[str, dict] = {}
        for future in asyncio.as_completed([asyncio.create_task(verify(c)) for c in claims]):
            try:
                claim, verdict, reason, result = await future
            except (TokenFactoryError, ValueError) as exc:
                yield {"type": "warning", "stage": "verify", "message": str(exc)[:300]}
                continue
            counts[verdict] += 1
            verdicts[claim.id] = {"verdict": verdict, "reason": reason}
            yield {"type": "verdict", "claim_id": claim.id, "section": claim.section, "verdict": verdict, "reason": reason, "seconds": round(result.seconds, 2) if result else 0}
        yield {"type": "stage", "stage": "verify", "status": "done", "counts": counts}

        yield {"type": "report", "markdown": to_markdown(analysis, verdicts, corpus, self.client.ledger.snapshot(), s), "counts": counts}
        yield {"type": "usage", "ledger": self.client.ledger.snapshot()}
        yield {"type": "done"}


async def run_to_list(settings: Settings, client: TokenFactoryClient, sources: list[dict]) -> list[dict]:
    return [event async for event in Pipeline(settings, client).run(sources)]


__all__ = ["Pipeline", "run_to_list", "Corpus"]
