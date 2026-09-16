# Devpost submission fields

## Project name
Postmortem Pilot

## Tagline (max ~200 chars)
Raw outage logs in, evidence-grounded blameless postmortem out. Nemotron Nano reads, Nemotron Ultra reasons, Nemotron Lightning fact-checks every claim, all on Nebius Token Factory.

## Track
Best Apps and Agents

## Built with
python, fastapi, httpx, javascript, html, css, docker, nebius-token-factory, nvidia-nemotron, nemotron-3-ultra, nemotron-3-nano, nemotron-3.5-lightning

## Demo URL
https://cvasilopoulos.github.io/Nebius_repo/ (static GitHub Pages build replaying a real recorded Token Factory run; see DEPLOY.md for a live-inference alternative)

## Repository URL
TODO (public GitHub repo with MIT license)

## Video URL
TODO (public YouTube link)

## Description (Markdown)

### Inspiration
Every on-call engineer knows the hangover after an outage: five browser tabs of logs, a Slack thread, and a postmortem document that someone has to write while tired. The root-cause section is too often a plausible story rather than something traced to evidence. Pasting logs into a chatbot makes that worse, because it produces confident prose and invents causes. We wanted a tool that is fast like an LLM but disciplined like a good incident reviewer: nothing gets written unless the logs prove it.

### What it does
Postmortem Pilot takes the raw logs from an incident (database, backup tool, Kubernetes events, application, alerting) and produces a structured blameless postmortem in about a minute: impact, trigger, root cause, causal chain, contributing factors, ruled-out red herrings, detection gaps, resolution, prioritised action items and open questions.

- Every claim carries citation chips such as `S3:12`; click one to see the raw log line.
- Every claim is independently fact-checked against only the lines it cites, and marked supported, partial or unsupported with a one-line reason. The report shows an overall evidence score.
- Secrets (passwords in connection strings, bearer tokens, JWTs, API keys, emails) are redacted before any model call.
- The pipeline streams live to the browser, and the result exports as Markdown with an evidence appendix.

### How we built it
A FastAPI backend streams NDJSON events to a no-build vanilla JS front end. The pipeline routes each task to the Nemotron model that fits it, all through the OpenAI-compatible Nebius Token Factory API:

1. **Extract - NVIDIA Nemotron 3 Nano 30B-A3B.** Logs are split per source into chunks and read in parallel with thinking disabled for speed. Nano returns notable events with line references; references that do not exist are dropped, and events are merged into one time-ordered timeline.
2. **Reason - NVIDIA Nemotron 3 Ultra 550B-A55B.** One call with reasoning enabled. Ultra sees only the distilled timeline and the cited raw lines (a fraction of the raw log tokens), and must cite every statement. It separates trigger from root cause and explicitly explains why coincidental events (like a deploy in the same minute) are not causal.
3. **Verify - NVIDIA Nemotron 3.5 Lightning.** One small parallel call per claim, with only that claim and its cited lines. A different model from the reasoner acts as an independent, adversarial checker.

A token ledger tracks prompt, completion and reasoning tokens per model and stage, and the UI shows it after each run. A recorder captures real runs so the demo can be replayed at zero cost.

### Challenges we ran into
- Reasoning budgets: Nano and Lightning are reasoning models by default. In our first full run, Nano used its entire output budget thinking and returned nothing for three of five log sources. Turning thinking off for the extraction and verification calls (`chat_template_kwargs.enable_thinking=false`) made those calls several times faster and far cheaper, while keeping full reasoning for Ultra, where it matters.
- Keeping the verifier fair: too strict and everything is "partial", too lenient and it rubber-stamps. Asking the verifier for its reason before its verdict, and asking Ultra to cite both the cause and the effect line for each link, made verdicts much more meaningful.
- Grounding: models sometimes cite lines that do not exist. Every reference is validated against the parsed corpus before it is shown or verified.

### Accomplishments that we're proud of
- A verifier loop that visibly catches overreach in a 550B model's analysis in about three seconds. In our recorded run it caught Ultra quoting a timestamp that is not in the cited log line.
- A full five-source analysis in under 30 seconds and about 30k tokens (roughly one to two cents), with 25 model calls, 24 of them on the small fast models.
- A complete product flow: samples, paste your own logs, live pipeline, clickable evidence, export.

### What we learned
Model routing is a product decision, not just a cost decision. The cheapest models are excellent at narrow reading and yes/no checking, and the big reasoning model is at its best when it is given less, cleaner context. Token Factory's single OpenAI-compatible endpoint for all three models made that routing trivial to build and tune.

### What's next
- Pull logs directly for an incident window from Loki, OpenSearch or CloudWatch.
- Post the report to Confluence, Notion or a Git wiki, and open tickets for action items.
- Batch mode on Nebius Serverless Jobs for very large incidents and for back-testing old postmortems.
- A follow-up chat that answers "why" questions grounded in the same cited evidence.

### Built with AI assistance
The code, prompts, synthetic sample logs and documentation were developed with the help of an AI coding assistant (Anthropic's Claude via Claude Code), directed and reviewed by the entrant. The product's own runtime AI is exclusively NVIDIA Nemotron on Nebius Token Factory.

## Feedback on Nebius Token Factory, AI Cloud and NVIDIA tools

**What worked well**
- The OpenAI-compatible API made integration take minutes: one base URL and one key serve Nemotron 3 Nano, Nemotron 3 Ultra and Nemotron 3.5 Lightning, so per-stage model routing is just a string.
- Latency was good for a 550B-parameter model: Ultra returned a full structured analysis with about 2.4k reasoning tokens in 14 seconds for our sample, and Lightning answered 19 parallel checks in under 3 seconds of wall time.
- `usage` includes `completion_tokens_details.reasoning_tokens` for Ultra and Lightning, which made cost accounting per stage easy.
- `chat_template_kwargs.enable_thinking=false` works on Nano and Lightning and is essential for high-volume calls.

**What could be better**
- Reasoning-token behaviour is inconsistent between models: Nano returns its thinking in `message.reasoning` and reports no `reasoning_tokens` detail, while Ultra and Lightning use `reasoning_content` and report reasoning tokens. A consistent schema would simplify clients.
- When a reasoning model exhausts `max_tokens` during thinking, the response is `finish_reason: length` with empty content. A documented per-request reasoning budget (for example `reasoning_effort` or a thinking-token cap that is guaranteed to leave room for the answer) would prevent silent empty answers. `reasoning_effort: low` did not reliably shorten Lightning's thinking in our tests.
- The thinking on/off switch (`chat_template_kwargs`) is not obvious from the model cards in the console; a documented toggle per model, with defaults, would save new users time and credits.
- JSON mode or structured output guarantees for all Nemotron models would remove the need for defensive JSON extraction.
- Per-model prices for newer models (for example Nemotron 3.5 Lightning) were harder to find than the model itself; showing price next to each model in the playground and in `/v1/models` would help credit planning.
- For hackathon builders, a per-key spend limit that can be set when creating a key would make it safer to deploy public demos.
- Serverless Endpoints: clearer CPU-only examples (a small web app container calling Token Factory) and a price calculator for the smallest CPU preset would make "deploy the app on Nebius" an easy default.
