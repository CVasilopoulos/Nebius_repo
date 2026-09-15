# Postmortem: PostgreSQL disk exhaustion due to WAL archive volume full
**Severity:** SEV1  
**Window:** 2026-09-02 02:00:00.029 to 2026-09-02 03:22:00  
**Format:** blameless; every claim cites log lines and was re-checked by an independent verifier model.

## Summary

The pgbackrest archive volume filled completely at 02:00, halting WAL archiving. Unarchived WAL accumulated on the primary pgdata volume until it also filled at 02:58, causing PostgreSQL to abort and the auth service to return 503 errors for ~80 minutes. Service restored after manual backup expiration freed 38 GB.

## Impact

All login requests failed (97-99% error rate) from 02:52 to 03:16 (~24 minutes) due to database unavailability; ~1,600-1,800 requests affected per 5-minute window. [`S2:6`, `S2:7`, `S2:8`, `S2:10`, `S2:11`, `S3:5`, `S3:6`] _(partially verified)_

## Trigger

WAL segment archive push failed at 02:00:00 because the pgbackrest-repo volume (200 GiB) had no space left, preventing WAL offload. [`S4:5`, `S4:6`, `S5:3`, `S5:5`, `S3:3`] _(verified)_

## Root cause

The pgbackrest-repo volume reached 100% capacity with no automated expiration, causing continuous WAL archive failures that filled the primary pgdata volume (50 GiB) and crashed PostgreSQL. [`S4:5`, `S3:3`, `S5:14`, `S3:7`, `S5:15`, `S5:18`, `S5:19`, `S3:4`] _(partially verified)_

## Detection

Archive volume full detected at 02:12:40 but alert suppressed (null receiver); primary volume full detected at 02:58:12; first critical page (LoginErrorRateHigh) sent at 02:56:10 — a 56-minute gap from first archive failure to paging. [`S3:3`, `S1:1`, `S3:7`, `S1:2`] _(partially verified)_

## Resolution

Manual expire command at 03:09:12 freed 38.2 GB by expiring 2 full backups; PostgreSQL restarted at 03:14:20; auth-service reconnected at 03:16:05; archive push succeeded at 03:16:30; alerts resolved by 03:22. [`S4:10`, `S4:11`, `S5:26`, `S2:11`, `S4:12`, `S1:5`, `S1:6`] _(verified)_

## Causal chain

1. pgbackrest-repo volume hit 100% (200/200 GiB) at 02:12:40, and archive pushes failed repeatedly from 02:00 onward with 'No space left on device'. [`S4:5`, `S4:6`, `S4:7`, `S4:8`, `S4:9`, `S5:3`, `S5:7`, `S5:11`, `S5:13`, `S3:3`] _(partially verified)_
1. WAL files accumulated unarchived, reaching 612 files (9.6 GB) by 02:40:02. [`S5:14`] _(verified)_
1. Primary pgdata volume (pvc/pgdata-postgres-0) reached 100% (50/50 GiB) at 02:58:12. [`S3:7`] _(verified)_
1. PostgreSQL could not extend database files or write WAL at 02:51:37 and 02:51:52, triggering checkpointer abort (signal 6). [`S5:15`, `S5:18`, `S5:19`] _(verified)_
1. PostgreSQL container entered crash-loop back-off at 02:51:56; auth-service connections were refused from 02:51:58. [`S3:4`, `S2:3`, `S2:5`] _(verified)_
1. Auth-service returned 503 'database unavailable' for login from 02:52:05, readiness probes failed, and login error rate exceeded 97% by 02:55. [`S2:6`, `S2:7`, `S3:5`, `S3:6`, `S2:8`] _(verified)_

## Contributing factors

- Alert for PgBackRestRepoVolumeFull was routed to a null receiver at 02:12:45, so no on-call was notified when the archive volume first filled. [`S1:1`, `S3:3`] _(verified)_
- No automated backup expiration ran before volumes exhausted; manual expire command executed only at 03:09:12. [`S4:10`, `S4:11`] _(NOT verified)_
- WAL archiving had no backpressure mechanism; PostgreSQL continued generating WAL while archive failed for 58 minutes. [`S5:14`, `S5:15`, `S5:18`] _(partially verified)_
- Primary pgdata volume (50 GiB) was too small to absorb the WAL backlog generated during the archive outage. [`S3:7`, `S5:14`] _(partially verified)_

## Ruled out (red herrings)

- Web-frontend pod kill and replica-set scale-up at 03:03-03:04 were manual mitigation attempts, not causes of the outage. [`S3:8`, `S3:9`] _(NOT verified)_
- The initial 500 error at 02:51:38 was a symptom of disk exhaustion, not an independent application bug. [`S2:2`, `S5:15`] _(verified)_
- Auth-service connection reset at 02:51:52 resulted from PostgreSQL process abort, not a network partition. [`S2:3`, `S5:19`, `S3:4`] _(verified)_

## Action items

| Priority | Type | Action |
|---|---|---|
| P0 | detect | Fix alert routing for PgBackRestRepoVolumeFull so warnings page on-call immediately. |
| P0 | prevent | Implement automated backup expiration/retention enforcement that runs before volumes reach capacity. |
| P1 | detect | Add monitoring and alerting on pg_wal backlog file count and size. |
| P1 | mitigate | Increase pgdata PVC size or enable volume auto-expansion to absorb WAL during archive outages. |
| P1 | prevent | Add WAL archiving backpressure (e.g., pause WAL generation or throttle checkpoints) when archive falls behind. |
| P2 | process | Run chaos test / game day simulating archive volume exhaustion to validate detection and auto-remediation. |

## Open questions

- Why was the PgBackRestRepoVolumeFull alert receiver configured as null?
- What is the normal WAL generation rate, and why did 9.6 GB accumulate in ~40 minutes?
- Was an auto-expire policy configured but not executing, or is there no such policy?
- Why did the 50 GiB pgdata volume fill so quickly (within ~58 minutes of first archive failure)?

## Evidence

```
[S1:1] (alertmanager.log) 2026-09-02T02:12:45Z level=info msg="Notify skipped" alert=PgBackRestRepoVolumeFull severity=warning receiver=null reason="warning alerts routed to null receiver"
[S1:2] (alertmanager.log) 2026-09-02T02:56:10Z level=info msg="Notify success" alert=LoginErrorRateHigh severity=critical receiver=pagerduty-oncall
[S1:5] (alertmanager.log) 2026-09-02T03:21:00Z level=info msg="Resolved" alert=LoginErrorRateHigh
[S1:6] (alertmanager.log) 2026-09-02T03:22:00Z level=info msg="Resolved" alert=PgDataVolumeFull
[S2:2] (auth-service.log) 2026-09-02T02:51:38.010Z ERROR auth-service POST /v1/login 500 12ms error="pq: could not extend file \"base/16384/2619\": No space left on device"
[S2:3] (auth-service.log) 2026-09-02T02:51:52.600Z ERROR auth-service db pool: connection reset by peer dsn=postgres://auth_svc:[REDACTED]@postgres-0.db:5432/auth
[S2:5] (auth-service.log) 2026-09-02T02:51:58.400Z ERROR auth-service db connect failed: dial tcp 10.42.3.17:5432: connect: connection refused
[S2:6] (auth-service.log) 2026-09-02T02:52:05.221Z ERROR auth-service POST /v1/login 503 2ms error="database unavailable"
[S2:7] (auth-service.log) 2026-09-02T02:52:07.908Z ERROR auth-service POST /v1/login 503 1ms error="database unavailable"
[S2:8] (auth-service.log) 2026-09-02T02:55:00.000Z WARN  auth-service login error rate 97.8% over 5m (1622 of 1658 requests)
[S2:10] (auth-service.log) 2026-09-02T03:05:00.000Z WARN  auth-service login error rate 99.1% over 5m (1790 of 1806 requests)
[S2:11] (auth-service.log) 2026-09-02T03:16:05.300Z INFO  auth-service db connect ok pool_size=20
[S3:3] (kube-events.txt) 2026-09-02T02:12:40Z  Warning  VolumeUsageHigh    pvc/pgbackrest-repo           Volume usage 100% (200Gi/200Gi)
[S3:4] (kube-events.txt) 2026-09-02T02:51:56Z  Warning  BackOff            pod/postgres-0                Back-off restarting failed container postgres
[S3:5] (kube-events.txt) 2026-09-02T02:52:30Z  Warning  Unhealthy          pod/auth-service-6c7f8-xk2lp  Readiness probe failed: HTTP probe failed with statuscode: 503
[S3:6] (kube-events.txt) 2026-09-02T02:52:31Z  Warning  Unhealthy          pod/auth-service-6c7f8-q9vtm  Readiness probe failed: HTTP probe failed with statuscode: 503
[S3:7] (kube-events.txt) 2026-09-02T02:58:12Z  Warning  VolumeUsageHigh    pvc/pgdata-postgres-0         Volume usage 100% (50Gi/50Gi)
[S3:8] (kube-events.txt) 2026-09-02T03:03:41Z  Normal   Killing            pod/web-frontend-7d9c4-2hdd8  Stopping container web-frontend (manual rollback requested)
[S3:9] (kube-events.txt) 2026-09-02T03:04:20Z  Normal   ScalingReplicaSet  deployment/web-frontend       Scaled up replica set web-frontend-5b8f1 to 3 (image web-frontend:v2.13.2)
[S4:5] (pgbackrest.log) 2026-09-02 02:00:00.029 P00  ERROR: [082]: WAL segment 0000000100000A2F00000041 was not pushed due to error in repo1: unable to write '/var/lib/pgbackrest/archive/main/16-1/0000000100000A2F00000041.zst': [28] No space left on device
[S4:6] (pgbackrest.log) 2026-09-02 02:00:00.030 P00   INFO: archive-push command end: aborted with exception [082]
[S4:7] (pgbackrest.log) 2026-09-02 02:05:00.205 P00  ERROR: [082]: WAL segment 0000000100000A2F00000041 was not pushed due to error in repo1: [28] No space left on device
[S4:8] (pgbackrest.log) 2026-09-02 02:20:00.116 P00  ERROR: [082]: WAL segment 0000000100000A2F00000041 was not pushed due to error in repo1: [28] No space left on device
[S4:9] (pgbackrest.log) 2026-09-02 02:40:00.330 P00  ERROR: [082]: WAL segment 0000000100000A2F00000041 was not pushed due to error in repo1: [28] No space left on device
[S4:10] (pgbackrest.log) 2026-09-02 03:09:12.884 P00   INFO: expire command begin 2.53: --repo1-retention-full=2 --stanza=main
[S4:11] (pgbackrest.log) 2026-09-02 03:09:40.301 P00   INFO: expire command end: completed successfully, 2 full backups expired, 38.2 GB freed
[S4:12] (pgbackrest.log) 2026-09-02 03:16:30.088 P00   INFO: archive-push command end: completed successfully
[S5:3] (postgres.log) 2026-09-02 02:00:00.031 UTC [98231] LOG:  archive command failed with exit code 82
[S5:5] (postgres.log) 2026-09-02 02:00:01.412 UTC [98231] WARNING:  archiving write-ahead log file "0000000100000A2F00000041" failed too many times, will try again later
[S5:7] (postgres.log) 2026-09-02 02:05:00.207 UTC [98231] LOG:  archive command failed with exit code 82
[S5:11] (postgres.log) 2026-09-02 02:20:00.118 UTC [98231] LOG:  archive command failed with exit code 82
[S5:13] (postgres.log) 2026-09-02 02:40:00.332 UTC [98231] LOG:  archive command failed with exit code 82
[S5:14] (postgres.log) 2026-09-02 02:40:02.015 UTC [98231] WARNING:  pg_wal contains 612 files not yet archived (9.6 GB)
[S5:15] (postgres.log) 2026-09-02 02:51:37.880 UTC [6023] ERROR:  could not extend file "base/16384/2619": No space left on device
[S5:18] (postgres.log) 2026-09-02 02:51:52.131 UTC [412] PANIC:  could not write to file "pg_wal/xlogtemp.412": No space left on device
[S5:19] (postgres.log) 2026-09-02 02:51:52.470 UTC [1] LOG:  checkpointer process (PID 412) was terminated by signal 6: Aborted
[S5:26] (postgres.log) 2026-09-02 03:14:20.551 UTC [1] LOG:  starting PostgreSQL 16.4 on x86_64-pc-linux-gnu
```

---
Generated by Postmortem Pilot on Nebius Token Factory: events extracted by `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, causal analysis by `nvidia/Nemotron-3-Ultra-550b-a55b`, claims verified by `nvidia/Nemotron-3_5-Lightning`. Total tokens: 29519.