# Getting a public demo URL

Devpost requires "a URL to a working demo" and judges may test it until the judging period ends (**15 Dec 2026**).

## Default: GitHub Pages (free, recorded replay)

Live at **https://cvasilopoulos.github.io/Nebius_repo/**, built from `docs/` on `main`. `scripts/build_static.py` exports the same UI (`static/index.html` + `static/app.js`, with a `STATIC_MODE` flag flipped on) to `docs/`, wired to replay the bundled real Token Factory recording (`samples/pgbackrest-disk-full/run.ndjson`) client-side instead of streaming it from the FastAPI server. Same citation chips, evidence score and Markdown export as the live app. No server, no API key, $0, never goes down or runs out of credit.

Rebuild after any change to `static/` or `samples/`:

```bash
python3 scripts/build_static.py
git add docs && git commit -m "..." && git push
```

Pages source is `main` / `/docs` (set with `gh api repos/CVasilopoulos/Nebius_repo/pages`). "Analyze live on Token Factory" is disabled on this build since there is no server; only the recorded replay runs.

## Paid alternative: Nebius Serverless Endpoint (live inference)

Why: the track text encourages Nebius Serverless Endpoints, it keeps the whole project on Nebius (a point in "Technological Implementation"), and the key stays inside Nebius. Use this only if you want judges to run their own logs live against Token Factory, and accept the running cost below. The app is one small stateless container (FastAPI, ~150 MB image, idles at well under 256 MB RAM, no GPU); all model inference happens on Nebius Token Factory, so the host only needs a tiny CPU.

Cost estimate (Nebius price list, Sep 2026: CPU-only Intel Ice Lake instances "from $0.05/hour", public IP free, disk about $0.065-0.08 per GiB-month):

| Item | Estimate |
|---|---|
| Smallest CPU endpoint, always on, 30 Oct - 15 Dec (~46 days, ~1,100 h) | about **$55-110** (at $0.05-0.10/h; confirm the exact preset price in the console before creating) |
| Same, only while judging is active (1 Dec - 15 Dec, ~340 h), stopped otherwise | about **$17-34** |
| Token Factory usage per live demo run (measured, see README) | about **$0.01-0.02** |
| Worst case with the built-in guard (20 live runs per IP per day) | small; add a Token Factory spend limit or a dedicated key with limited credits |

Steps (Nebius CLI; verify flag names with `nebius ai endpoint create --help`, the Serverless CLI is new):

```bash
REGION=eu-north1
REGISTRY=cr.$REGION.nebius.cloud/<registry-id>
nebius iam get-access-token | docker login cr.$REGION.nebius.cloud --username iam --password-stdin
docker build --platform linux/amd64 -t $REGISTRY/postmortem-pilot:1.0 .
docker push $REGISTRY/postmortem-pilot:1.0

nebius ai endpoint create \
  --name postmortem-pilot \
  --image $REGISTRY/postmortem-pilot:1.0 \
  --platform cpu-e2 \
  --container-port 8080 \
  --env NEBIUS_API_KEY=<demo key with a small credit limit> \
  --env RUNS_PER_IP_PER_DAY=10 \
  --env MAX_LINES=800 \
  --public

nebius ai endpoint stop <endpoint-id>      # pause billing
nebius ai endpoint delete <endpoint-id>    # after 15 Dec
```

Notes:
- Prefer a separate Token Factory API key for the demo, so it can be revoked without touching the development key. Do not reuse the key stored on limnos in a public deployment unless you accept that risk.
- If you stand this up, put its URL in the README/SUBMISSION demo field instead of (or alongside) the GitHub Pages one, and say plainly which URL is live and which is a recorded replay.
- The GitHub Pages replay keeps working even if this endpoint's key is revoked or credits run out, so there is always a demo URL that never shows a broken page.

## Alternative: self-host on existing homelab (limnos + gateway/cloudflared)

The existing cvrealm.com Cloudflare tunnel pattern could expose `postmortem.cvrealm.com` at no extra cost, with `NEBIUS_API_KEY` set for live inference. Downsides: availability depends on the homelab until mid-December, the Token Factory key sits on a public-facing home service, and it is not Nebius infrastructure. Only worth it if the Serverless Endpoint option above is blocked and live inference (not just the GitHub Pages replay) is required.
