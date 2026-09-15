# Getting a live public demo URL

Devpost requires "a URL to a working demo" and judges may test it until the judging period ends (**15 Dec 2026**). The app is one small stateless container (FastAPI, ~150 MB image, idles at well under 256 MB RAM, no GPU). All model inference happens on Nebius Token Factory, so the host only needs a tiny CPU.

Nothing below has been done yet. Pick one option in the morning.

## Recommended: Nebius Serverless Endpoint (CPU), with a spend guard

Why: the track text encourages Nebius Serverless Endpoints, it keeps the whole project on Nebius (a point in "Technological Implementation"), and the key stays inside Nebius.

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
- Put the endpoint's public URL (HTTP) in the Devpost "demo URL" field. If only an IP:port is given, that is acceptable for Devpost but a hostname looks better; a Cloudflare DNS record on cvrealm.com could point at it (optional, free).
- The recorded replay works even if the key is revoked or credits run out, so the URL never shows a broken page.

## Alternative A: replay-only static-ish demo, near $0

Run the container **without** `NEBIUS_API_KEY` on any free tier container host (Render free web service, Fly.io, Hugging Face Spaces Docker). The page loads the bundled sample and replays the recorded real Token Factory run; "Analyze live" is disabled with a clear message. Cost: $0. Downside: judges cannot run their own logs, and it is not on Nebius (weaker on "runs on Nebius" optics, although the rules requirement is satisfied by the runtime Token Factory calls in the repo and video).

## Alternative B: self-host on existing homelab (limnos + gateway/cloudflared)

The existing cvrealm.com Cloudflare tunnel pattern could expose `postmortem.cvrealm.com` at no extra cost. Downsides: availability depends on the homelab until mid-December, the Token Factory key sits on a public-facing home service, and it is not Nebius infrastructure. Only if the Nebius options are blocked.

## Recommendation

Nebius Serverless Endpoint on the smallest CPU preset with a dedicated, credit-limited Token Factory key, `RUNS_PER_IP_PER_DAY=10`; stop it after submission and start it again for 1-15 Dec if you want to minimise cost (~$20-35 total), or leave it on (~$55-110) for zero-maintenance. Needs your approval before anything is created.
