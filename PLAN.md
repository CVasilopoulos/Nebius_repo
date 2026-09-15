# Plan

## Decision (made 2026-09-16, ~10 min)

Track: **Best Apps and Agents** (powered by Nemotron via Nebius Token Factory).

Project: **Postmortem Pilot** - paste the raw logs of an outage (database log, backup tool, Kubernetes events, app log, alert history) and get an evidence-grounded, blameless postmortem in about a minute. Every claim in the report cites the exact log lines it is based on, and every claim is independently re-checked against those lines before it is shown.

## Why this track and idea

- Solo, no camera, limited credits: a web app whose entire value is visible on screen records well. Physical AI needs hardware footage; Personal AI expects NemoClaw/OpenShell/Hermes tooling that adds setup risk; the Coding track expects Token Factory Sandboxes, which are not verified on this account.
- The track text literally asks for "Nemotron 3 Ultra when you need serious reasoning, and Nano or Super for the fast, everyday calls". A three-tier pipeline makes that split the core of the architecture rather than a checkbox:
  - **Nemotron 3 Nano** (fast, cheap) reads log chunks in parallel and extracts notable events (map).
  - **Nemotron 3 Ultra** (deep reasoning) sees only the compact event timeline plus cited lines, and builds the causal chain, root cause, red herrings and remediations (reduce).
  - **Nemotron 3.5 Lightning** (sub-second) verifies each claim against its cited raw lines, in parallel, flagging anything unsupported.
- Judging criteria mapping:
  - Technological implementation: model routing by task, parallel fan-out, streaming UI, local secret redaction, token ledger showing how much context Ultra did not have to read.
  - Design: a complete flow (load/paste logs, live pipeline, report, export Markdown), not a notebook.
  - Potential impact: every on-call engineer writes postmortems; they take hours and often contain unsupported root-cause guesses. Specific audience (SRE/platform teams), specific pain (time and accuracy).
  - Quality of idea: the non-obvious part is the verifier loop - using the cheapest model as an adversarial fact-checker of the most expensive one, with citations the reader can click.
- Credit-friendly: one full run on the bundled sample is on the order of tens of thousands of tokens, mostly on Nano/Lightning.

## Scope for tonight

1. Python FastAPI backend, async Token Factory client (OpenAI-compatible), NDJSON streaming.
2. Single-page UI (vanilla JS, no build step).
3. Two synthetic sample incidents, record/replay of a real run for the demo and for a zero-cost fallback.
4. Unit tests with a fake client plus live tests against the real API with small caps.
5. README, LICENSE, VIDEO_SCRIPT.md, SUBMISSION.md, DEPLOY.md.

Out of scope: auth, persistence, integrations (PagerDuty/Loki pull) - listed as roadmap.
