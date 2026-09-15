# Demo video script (target 2:40, hard limit under 3:00)

Format: screen recording of the app in a browser at 1440p or 1080p, plus a voice-over. The narration below is written for text-to-speech (plain sentences, no symbols; model names spelled out). Roughly 360 words at ~140 words per minute = ~2:35.

Recording tips:
- Browser zoom 110-125 %, hide bookmarks bar, dark OS theme.
- Record the live run once for real; if Token Factory latency is high, you may speed up the waiting parts (label it "sped up 2x" on screen) or use "Replay recorded run", which replays a real recorded run at its original timing.
- No music is needed. If you add music it must be royalty-free and credited.
- Show the README models table and a terminal `pytest` line briefly at the end if time allows.

## Shot list and narration

| # | Time | On screen | Narration |
|---|---|---|---|
| 1 | 0:00-0:15 | App home page, sample "Login outage: Postgres volume full" selected, tabs showing five log files. | It is three in the morning, logins are down, and forty minutes later you are left with five different log files and a postmortem to write. Postmortem Pilot turns those raw logs into an evidence grounded, blameless postmortem in about a minute. |
| 2 | 0:15-0:35 | Click through tabs: postgres.log, pgbackrest.log, kube-events, auth-service.log with the password in the DSN visible, alertmanager.log. | This sample incident has a Postgres log, backup tool output, Kubernetes events, the auth service log, and alert history. It also contains a database password and a bearer token, and a frontend deploy that happened at the same time, which is a classic red herring. |
| 3 | 0:35-0:55 | Click "Analyze live on Token Factory". Redact stage turns green showing secrets redacted; Extract stage shows parallel bars filling. | First, secrets are redacted locally, before any model call. Then NVIDIA Nemotron 3 Nano, running on Nebius Token Factory, reads every log source in parallel and extracts only the events that matter, each with a reference to its exact line. |
| 4 | 0:55-1:20 | Reason stage running (about 14 seconds). Results panel appears with title, causal chain. | The expensive model never reads the raw dump. Nemotron 3 Ultra, the five hundred fifty billion parameter reasoning model, gets only the merged timeline and the lines that matter. It separates trigger from root cause, builds the causal chain, and explicitly rules out the coincidental deploy. |
| 5 | 1:20-1:45 | Verify stage: verdict badges flip from "checking" to supported, partial, unsupported. Evidence score appears. | Now the part that makes this trustworthy. Every single claim is fact checked by a third model, Nemotron 3.5 Lightning, which sees only that claim and the lines it cites. These checks run in parallel and take a second or two. Anything the logs do not prove is flagged instead of quietly ending up in your incident report. |
| 6 | 1:45-2:05 | Click a citation chip on the root cause: raw log line expands. Click the red "unsupported" causal chain step about the WAL backlog and show the verifier reason (Ultra quoted 02:10:44, the log says 02:40:02). Scroll to action items and ruled-out section. | Click any citation to see the raw log line behind it. Here the verifier caught the reasoning model quoting a time that is not in the log line it cited. Below are prioritised action items, like fixing backup retention and routing the repository full alert to on call instead of a null receiver. |
| 7 | 2:05-2:20 | Scroll to Token Factory usage cards, then click "Download .md" and show the Markdown report briefly. | The usage panel shows how the work was split: many fast, cheap calls to Nano and Lightning, one deep call to Ultra. A full run on this incident costs about one or two cents on Token Factory. The report exports as Markdown with an evidence appendix, ready for your wiki. |
| 8 | 2:20-2:40 | README section "Which NVIDIA models, and why" or the architecture diagram; end card with app name and repo URL. | Postmortem Pilot runs entirely on Nebius Token Factory with three NVIDIA Nemotron open models, each chosen for the job it does best: Nano to read, Ultra to reason, Lightning to verify. The code is open source under the MIT license. Thanks for watching. |

## Checklist before upload

- [ ] Duration under 3:00 (aim for 2:40).
- [ ] Audio clearly mentions Nebius Token Factory and the NVIDIA Nemotron models (shots 3, 4, 5, 8).
- [ ] The app is visibly working (live run or clearly labelled real replay).
- [ ] No third-party logos or copyrighted music.
- [ ] YouTube visibility: Public (not Unlisted, not Private).
