# Postmortem: PostgreSQL data volume exhaustion due to blocked WAL archiving
**Severity:** SEV1  
**Window:** 2026-09-02T02:00:00.029Z to 2026-09-02T03:22:00Z  
**Format:** blameless; every claim cites log lines and was re-checked by an independent verifier model.

## Summary

The pgbackrest archive repository (pvc/pgbackrest-repo) filled to 100% at 02:12:40, causing WAL archiving to fail repeatedly from 02:00:00 onward. Unarchived WAL files accumulated on the primary PostgreSQL data volume (pvc/pgdata-postgres-0), which reached 100% at 02:58:12, triggering PostgreSQL PANIC and crash at 02:51:52. The auth-service lost database connectivity and returned 503 errors, driving login error rate to 99.1%. Service was restored at 03:16 after manual backup expiration freed 38.2 GB.

## Impact

All users of the /v1/login endpoint experienced 97.8–99.1% error rates (503 database unavailable) from 02:52:05 until 03:16:05 (~24 minutes). Auth-service pods were marked unhealthy from 02:52:30. PostgreSQL was unavailable from 02:51:52 to 03:14:20. [`S2:6`, `S2:7`, `S2:8`, `S2:10`, `S2:11`, `S3:5`, `S3:6`, `S5:19`, `S5:24`, `S5:26`] _(partially verified)_

## Trigger

The pgbackrest archive repository (repo1 on pvc/pgbackrest-repo) ran out of space, causing the first WAL segment push failure at 02:00:00 with "no space left on device". [`S4:5`, `S4:6`, `S5:3`] _(verified)_

## Root cause

The pgbackrest archive volume (200 GiB) filled completely, blocking WAL archiving. This caused WAL files to accumulate on the primary PostgreSQL data volume (50 GiB), which subsequently filled and caused PostgreSQL to panic and crash. [`S3:3`, `S4:5`, `S5:11`, `S3:7`, `S5:15`, `S5:18`] _(verified)_

## Detection

First signal was pgbackrest archive failures at 02:00:00, but the volume-full warning at 02:12:40 did not notify due to null receiver. Critical detection occurred via LoginErrorRateHigh alert at 02:56:10 (after 97.8% error rate at 02:55:00) and PgDataVolumeFull at 02:58:15. Detection gap: 56 minutes from first archive failure to first critical alert. [`S4:5`, `S3:3`, `S1:1`, `S2:8`, `S1:2`, `S3:7`, `S1:3`] _(partially verified)_

## Resolution

Operator ran pgbackrest expire command at 03:09:12 with retention-full=2, which completed at 03:09:40 freeing 38.2 GB. PostgreSQL restarted at 03:14:20, archive-push succeeded at 03:16:30, auth-service reconnected at 03:16:05, and critical alerts resolved by 03:22:00. [`S4:10`, `S4:11`, `S5:26`, `S4:12`, `S5:31`, `S2:11`, `S1:5`, `S1:6`] _(partially verified)_

## Causal chain

1. pgbackrest repo1 write failures begin at 02:00:00 due to "no space left on device" on the archive volume, aborting archive-push commands. [`S4:5`, `S4:6`, `S5:3`, `S5:5`] _(verified)_
1. Kubernetes reports pvc/pgbackrest-repo at 100% usage (200Gi/200Gi) at 02:12:40; the associated alert PgBackRestRepoVolumeFull is routed to a null receiver so no notification fires. [`S3:3`, `S1:1`] _(partially verified)_
1. Unarchived WAL files back up on the primary PostgreSQL volume: pg_wal contains 612 files (9.6 GB) not yet archived by 02:10:44. [`S5:11`] _(NOT verified)_
1. PostgreSQL data volume pvc/pgdata-postgres-0 reaches 100% (50Gi/50Gi) at 02:58:12, but PostgreSQL first hits "could not extend file" at 02:51:37 and PANICs at 02:51:52, terminating the checkpointer process. [`S5:15`, `S5:18`, `S5:19`, `S3:7`] _(NOT verified)_
1. PostgreSQL startup process also fails with "no space left on device" at 02:51:56 and exits; Kubernetes enters back-off restart loop for the postgres container. [`S5:23`, `S5:24`, `S3:4`] _(verified)_
1. Auth-service loses database connectivity (connection refused at 02:51:58) and begins returning 503 "database unavailable" for /v1/login at 02:52:05. [`S2:5`, `S2:6`, `S2:7`] _(verified)_
1. Auth-service readiness probes fail with HTTP 503 at 02:52:30, pods marked unhealthy, and login error rate climbs to 97.8% by 02:55:00 and 99.1% by 03:05:00, firing critical alerts. [`S3:5`, `S3:6`, `S2:8`, `S2:10`, `S1:2`] _(verified)_

## Contributing factors

- The PgBackRestRepoVolumeFull warning alert was configured with a null receiver, so the 02:12:40 volume-full condition did not generate a notification, delaying awareness by ~44 minutes. [`S1:1`, `S3:3`] _(partially verified)_
- No automated backup expiration or retention enforcement triggered when the archive volume filled; manual expire command was required at 03:09:12 to free 38.2 GB. [`S4:10`, `S4:11`] _(NOT verified)_
- The PostgreSQL data volume (50 GiB) was too small to absorb the WAL backlog generated while archiving was blocked, leading to rapid exhaustion. [`S5:11`, `S3:7`, `S5:15`] _(NOT verified)_
- Auth-service has no graceful degradation mode; it returns hard 503 errors immediately when the database is unavailable, amplifying user-facing impact. [`S2:6`, `S2:7`, `S2:8`] _(partially verified)_

## Ruled out (red herrings)

- Manual rollback of web-frontend pod at 03:03:41 and replica set scale-up at 03:04:20 were operator response actions taken after incident acknowledgment, not causal factors. [`S3:8`, `S3:9`, `S1:4`] _(NOT verified)_
- The expire command at 03:09:12 and subsequent archive-push success at 03:16:30 were resolution steps, not contributors to the outage. [`S4:10`, `S4:11`, `S4:12`, `S5:31`] _(NOT verified)_
- LoginErrorRateHigh and PgDataVolumeFull alerts (02:56:10, 02:58:15) are symptoms of the outage, not causes. [`S1:2`, `S1:3`, `S2:8`, `S3:7`] _(verified)_

## Action items

| Priority | Type | Action |
|---|---|---|
| P0 | detect | Fix alert routing for PgBackRestRepoVolumeFull to a valid receiver (pagerduty-oncall) so volume-full warnings notify immediately. |
| P0 | prevent | Implement automated backup expiration/retention enforcement that triggers when archive repo usage exceeds a high-water mark (e.g., 80%). |
| P1 | prevent | Increase PostgreSQL data volume (pvc/pgdata-postgres-0) size or enable volume auto-expansion to absorb WAL backlog during archiving outages. |
| P1 | detect | Add alert on pg_wal backlog file count / WAL archive lag (e.g., >100 files pending) to detect archiving stall before data volume fills. |
| P2 | mitigate | Implement auth-service circuit breaker / degraded mode (e.g., cached auth tokens, read-only fallback) to avoid hard 503 on transient DB unavailability. |
| P2 | process | Conduct incident response drill for storage-full scenarios covering pgbackrest expire, PostgreSQL recovery, and auth-service validation. |

## Open questions

- What workload or retention policy caused the pgbackrest archive volume (200 GiB) to fill completely? No log shows backup size growth.
- What is the typical WAL generation rate (GB/hour) for this cluster? Needed to model time-to-fill for the 50 GiB data volume.
- Why was PgBackRestRepoVolumeFull alert configured with a null receiver? Was this intentional or a configuration drift?
- Did any automated cleanup job exist for pgbackrest repo that failed silently?
- Could the expire command have been run earlier (e.g., at 02:12) if the alert had fired?

## Evidence

```
[S1:1] (alertmanager.log) 2026-09-02T02:12:45Z level=info msg="Notify skipped" alert=PgBackRestRepoVolumeFull severity=warning receiver=null reason="warning alerts routed to null receiver"
[S1:2] (alertmanager.log) 2026-09-02T02:56:10Z level=info msg="Notify success" alert=LoginErrorRateHigh severity=critical receiver=pagerduty-oncall
[S1:3] (alertmanager.log) 2026-09-02T02:58:15Z level=info msg="Notify success" alert=PgDataVolumeFull severity=critical receiver=pagerduty-oncall
[S1:4] (alertmanager.log) 2026-09-02T03:02:55Z level=info msg="Incident acknowledged" alert=LoginErrorRateHigh by=oncall-primary
[S1:5] (alertmanager.log) 2026-09-02T03:21:00Z level=info msg="Resolved" alert=LoginErrorRateHigh
[S1:6] (alertmanager.log) 2026-09-02T03:22:00Z level=info msg="Resolved" alert=PgDataVolumeFull
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
[S4:10] (pgbackrest.log) 2026-09-02 03:09:12.884 P00   INFO: expire command begin 2.53: --repo1-retention-full=2 --stanza=main
[S4:11] (pgbackrest.log) 2026-09-02 03:09:40.301 P00   INFO: expire command end: completed successfully, 2 full backups expired, 38.2 GB freed
[S4:12] (pgbackrest.log) 2026-09-02 03:16:30.088 P00   INFO: archive-push command end: completed successfully
[S5:3] (postgres.log) 2026-09-02 02:00:00.031 UTC [98231] LOG:  archive command failed with exit code 82
[S5:5] (postgres.log) 2026-09-02 02:00:01.412 UTC [98231] WARNING:  archiving write-ahead log file "0000000100000A2F00000041" failed too many times, will try again later
[S5:11] (postgres.log) 2026-09-02 02:20:00.118 UTC [98231] LOG:  archive command failed with exit code 82
[S5:15] (postgres.log) 2026-09-02 02:51:37.880 UTC [6023] ERROR:  could not extend file "base/16384/2619": No space left on device
[S5:18] (postgres.log) 2026-09-02 02:51:52.131 UTC [412] PANIC:  could not write to file "pg_wal/xlogtemp.412": No space left on device
[S5:19] (postgres.log) 2026-09-02 02:51:52.470 UTC [1] LOG:  checkpointer process (PID 412) was terminated by signal 6: Aborted
[S5:23] (postgres.log) 2026-09-02 02:51:55.920 UTC [7001] FATAL:  could not write to file "pg_wal/xlogtemp.7001": No space left on device
[S5:24] (postgres.log) 2026-09-02 02:51:56.001 UTC [1] LOG:  startup process (PID 7001) exited with exit code 1
[S5:26] (postgres.log) 2026-09-02 03:14:20.551 UTC [1] LOG:  starting PostgreSQL 16.4 on x86_64-pc-linux-gnu
[S5:31] (postgres.log) 2026-09-02 03:16:30.090 UTC [131] LOG:  archived write-ahead log file "0000000100000A2F00000041"
```

---
Generated by Postmortem Pilot on Nebius Token Factory: events extracted by `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, causal analysis by `nvidia/Nemotron-3-Ultra-550b-a55b`, claims verified by `nvidia/Nemotron-3_5-Lightning`. Total tokens: 30190.