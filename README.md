# Postmortem Pilot

**Raw outage logs in, evidence-grounded blameless postmortem out, in about a minute.**

Postmortem Pilot turns the pile of logs you have after an incident (database log, backup tool, Kubernetes events, application log, alert history) into a structured, blameless postmortem: impact, trigger, root cause, causal chain, contributing factors, ruled-out red herrings, detection gaps and prioritised action items.

The difference from "paste logs into a chatbot": **every claim cites the exact log lines it relies on, and every claim is independently fact-checked against those lines by a second model before you see it.** Click any citation chip to see the raw line. Unsupported claims are flagged in red instead of silently shipped into your incident doc.

Built for the **Nebius x NVIDIA Global AI Hackathon**, track **Best Apps and Agents**. It runs entirely on **Nebius Token Factory** using three **NVIDIA Nemotron** open models.

## Why

Every on-call team writes postmortems. They take hours of log archaeology, they are written when everyone is tired, and the root-cause section is often a plausible guess that nobody traces back to evidence. Generic LLM summaries make that worse: they sound confident and hallucinate causes. Postmortem Pilot is designed around the opposite principle - cheap models do the reading and the checking, the expensive reasoning model only sees distilled evidence, and nothing is shown without a citation.

## How it works

```
 your log files ──► 1. Redact (local regex) ──► 2. Extract (Nemotron 3 Nano, parallel, one call per chunk)
                                                          │  notable events + refs like [S3:12]
                                                          ▼
                                            merged, time-ordered timeline + cited raw lines
                                                          │
                                                          ▼
                                   3. Reason (Nemotron 3 Ultra 550B-A55B, one call)
                                      trigger, root cause, causal chain, red herrings,
                                      detection gap, action items - every statement with refs
                                                          │
                                                          ▼
                              4. Verify (Nemotron 3.5 Lightning, parallel, one call per claim)
                                 claim + only its cited lines -> supported / partial / unsupported
                                                          │
                                                          ▼
                              streaming web UI + Markdown report with an evidence appendix
```

1. **Redact (no model).** Passwords in connection strings, bearer tokens, JWTs, API keys, AWS keys, private-key headers and emails are scrubbed on the server before anything leaves it. Each line gets a stable reference `S<source>:<line>`.
2. **Extract (map, NVIDIA Nemotron 3 Nano 30B-A3B).** Each source is split into chunks and sent to Nano in parallel. Nano returns only the notable events with their refs. Refs that do not exist in the input are discarded (hallucination guard), and events are merged into one timeline using parsed timestamps.
3. **Reason (reduce, NVIDIA Nemotron 3 Ultra 550B-A55B).** Ultra never sees the full log dump - only the timeline and the raw text of the cited lines. On the small bundled sample (about 80 lines) that is roughly the same size as the raw logs; on real incidents with thousands of routine lines the distilled context stays small while the raw logs grow. It separates trigger from root cause, builds the causal chain, explicitly rules out coincidental events (for example a deploy that happened at the same time), identifies detection gaps and proposes action items. Refs it cites that are not in the evidence are stripped.
4. **Verify (NVIDIA Nemotron 3.5 Lightning).** Every claim is re-checked in isolation: the verifier gets the claim and only the lines it cites, and must answer supported, partial or unsupported. Claims with no valid citation are marked unsupported without a model call. The UI shows an evidence score and per-claim badges with the verifier's reason.

Results stream to the browser as NDJSON events, so you watch the pipeline work: parallel Nano calls completing, Ultra reasoning, and verdict badges flipping on each claim.

## Which NVIDIA models, and why

| Stage | Model on Token Factory | Why this model |
|---|---|---|
| Extract | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | High-volume, low-difficulty reading. 3B active parameters, called with thinking disabled: fast and cheap enough to fan out over every chunk in parallel. |
| Reason | `nvidia/Nemotron-3-Ultra-550b-a55b` | The one step that needs real multi-hop causal reasoning across sources and the judgement to reject red herrings. Called once per incident, on distilled evidence. |
| Verify | `nvidia/Nemotron-3_5-Lightning` | Many small, independent judgements where latency matters; called with thinking disabled and asked for its reason before its verdict, about one second per check in our runs. Using a different model than the reasoner makes the check independent of the reasoner's own biases. |

This is the routing the track describes ("Ultra for serious reasoning, Nano for the fast, everyday calls"), applied so that the expensive model reads the least text. All three model ids are configurable by environment variable.

## Nebius Token Factory usage

- All inference goes through the OpenAI-compatible Token Factory API at `https://api.tokenfactory.nebius.com/v1` (`/chat/completions`), via a small async `httpx` client (`postmortem_pilot/client.py`) with retries on 429/5xx and a token ledger.
- The ledger records prompt, completion and reasoning tokens per model and per stage; the UI shows it after each run, and `USAGE_LOG=usage.jsonl` appends one line per call for cost tracking.
- Token Factory made the three-model design practical: the same API key and endpoint serve a 30B MoE, a 550B MoE and Lightning, so switching models per stage is a one-string change, with no GPU provisioning.
- Thinking is switched off for the high-volume stages (`chat_template_kwargs: {"enable_thinking": false}`) and left on for Ultra. In our first run with thinking on, Nano spent its whole 3,000-token budget reasoning and returned nothing for 3 of 5 sources; with thinking off every chunk returned in 5-10 s.

### Measured run (bundled sample "Login outage: Postgres volume full", 5 sources, 80 lines)

| Stage | Model | Calls | Prompt tok | Completion tok (reasoning) | Wall time |
|---|---|---|---|---|---|
| Extract | Nemotron 3 Nano 30B-A3B | 5 parallel | 5,617 | 3,237 (0) | 9.9 s |
| Reason | Nemotron 3 Ultra 550B-A55B | 1 | 5,427 | 4,985 (2,362) | 14.0 s |
| Verify | Nemotron 3.5 Lightning | 19 parallel | 9,212 | 1,712 (0) | 2.9 s |
| **Total** | | **25** | | **30,190 tokens** | **26.8 s** |

At published Token Factory prices for Nano ($0.05 / $0.20 per 1M tokens) and Ultra ($0.50 / $2.20 per 1M tokens), plus Lightning, a full run costs roughly one to two cents. In that run the verifier marked 7 claims supported, 6 partial and 6 unsupported. Among the unsupported ones, it correctly caught Ultra citing a WAL backlog "by 02:10:44" when the log line says 02:40:02. That is exactly the kind of error that otherwise ends up in a real postmortem. The full generated report is in [docs/example-postmortem.md](docs/example-postmortem.md).

## Setup

Requirements: Python 3.11+ (or Docker) and a Nebius Token Factory API key (https://tokenfactory.nebius.com).

```bash
git clone <this repo> postmortem-pilot && cd postmortem-pilot
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export NEBIUS_API_KEY=...            # never commit this
uvicorn postmortem_pilot.app:app --port 8080
# open http://localhost:8080
```

With Docker:

```bash
docker build -t postmortem-pilot .
docker run --rm -p 8080:8080 -e NEBIUS_API_KEY postmortem-pilot
```

Without an API key the app starts in replay-only mode: the bundled sample can be replayed from a recorded real run (`samples/*/run.ndjson`), which costs nothing.

### Command line

```bash
python -m postmortem_pilot.cli samples/pgbackrest-disk-full --markdown postmortem.md
python -m postmortem_pilot.cli /var/log/myapp.log k8s-events.txt --record run.ndjson
```

### Configuration

| Variable | Default |
|---|---|
| `NEBIUS_API_KEY` | required for live runs |
| `TOKEN_FACTORY_BASE_URL` | `https://api.tokenfactory.nebius.com/v1` |
| `EXTRACT_MODEL` / `REASON_MODEL` / `VERIFY_MODEL` | Nano / Ultra / Lightning ids above |
| `MAX_LINES` | `1500` total lines per run (cost guard) |
| `CHUNK_LINES` | `60` lines per extraction call |
| `EXTRACT_MAX_TOKENS` / `REASON_MAX_TOKENS` / `VERIFY_MAX_TOKENS` | `3000` / `9000` / `1200` (include reasoning tokens) |
| `RUNS_PER_IP_PER_DAY` | `20` live runs per client address (public demo guard) |
| `USAGE_LOG` | optional JSONL file with per-call token usage |

### Tests

```bash
pip install -r requirements-dev.txt
pytest -q                              # offline tests use a mock Token Factory transport
NEBIUS_API_KEY=... pytest -q -s        # also runs live tests: each model once, plus the full pipeline on the small sample
```

## Project layout

```
postmortem_pilot/
  app.py        FastAPI app: /api/analyze (NDJSON stream), /api/replay/{sample}, /api/samples, /api/health
  pipeline.py   redact -> extract (Nano) -> reason (Ultra) -> verify (Lightning)
  client.py     Token Factory client + usage ledger
  prompts.py    system prompts for the three stages
  logs.py       redaction, line refs, chunking, timestamp parsing
  report.py     deterministic Markdown report with evidence appendix
  cli.py        command-line runner and recorder
static/         single-page UI, no build step
samples/        synthetic incidents (no real company data) + a recorded real run
tests/          offline and live tests
```

## Limitations and roadmap

- Timestamps are parsed from ISO-like formats; exotic formats fall back to file order.
- Very large incidents are capped by `MAX_LINES`; a pre-filter (severity keywords) or Serverless Jobs batch mode would lift that.
- Next: pull logs directly from Loki / OpenSearch / CloudWatch for an incident window, post the report to a wiki or ticket, and a "what if" follow-up chat grounded in the same evidence.

## AI assistance disclosure

This project was built with substantial help from an AI coding assistant (Anthropic's Claude, via Claude Code). The entrant chose the problem and direction, and the assistant drafted most of the code, prompts, sample logs and documentation under the entrant's direction and review. The sample incident logs are synthetic. The runtime AI in the product itself is exclusively NVIDIA Nemotron models served by Nebius Token Factory.

## License

MIT, see [LICENSE](LICENSE).
