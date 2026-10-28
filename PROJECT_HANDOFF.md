# NabzKhabar Project Handoff

## Scope
- This repository is for the Telegram news channel only.
- Instagram and YouTube work belongs in the private `NabzAI-YouTube` repository.

## Incident: publication gap on 2026-10-28
- Last confirmed Telegram publication: `2026-10-28T01:35:18Z` (`05:05:18` Iran time).
- GitHub Actions continued committing runtime state after that point.
- `v13_health.json` stayed on the old engine run while `v13_monitor.json` advanced its own `checked_at`, so the monitor falsely looked healthy.
- The strongest hypothesis is feed freshness/collection starvation or an engine early-exit path, but stale telemetry could not distinguish RSS errors, stale-only feeds, zero candidates, or a pre-telemetry crash.

## Root-cause patch
- PR #17: [diagnose feed starvation and stale runtime health](https://github.com/NabzKhabarOfficial/NabzKhabar/pull/17)
- Branch: `brain/root-cause-feed-observability`
- Adds startup heartbeat, per-feed collection diagnostics, feed summary persistence, and fail-closed stale-run detection.
- CI: compile/offline/audit checks pass; Telegram regression still fails. Its complete log is not exposed through the connected GitHub endpoint, so do not claim this PR is green or merge it yet.

## Automatic alerting
- Added `scripts/check_publication_health.py`.
- It fails on stale/missing telemetry, runtime/publication failure, or all feeds returning zero candidates.
- A GitHub Actions watchdog workflow was prepared but GitHub rejected the workflow-file write because this connection lacks `workflow` scope. The workflow still needs to be added manually or by a connection with workflow permission. Do not claim the automatic alert is active until that file exists on `main`.

## NabzAI-YouTube Instagram status
- 150 staged English/Persian mystery stories are merged on `main`; story validation and post-merge checks are green.
- PR #3 Buffer safety remains open and stale against current `main`; do not merge or run `buffer_max=10`.
- PR #5 production hardening remains open with a stale/diverged branch; historical checks do not prove current-main safety.
- Rebase or recreate both fixes on current `NabzAI-YouTube/main`, run current CI, then perform only the approved `buffer_max=1` smoke test.
- No live Buffer/Meta/provider verification is proven.

## Known risks
- Telegram accepted-but-lost responses still lack provider-side reconciliation.
- `v13_growth.py` has a direct sender outside the canonical outcome path.
- Some auxiliary state writers remain direct-write and need migration.
- `content/quarantine_manifest.json` is not yet wired into candidate selection.
- Live provider behavior is not proven by static checks alone.

## Required continuation
1. Obtain the complete Telegram regression log from an authenticated GitHub Actions session or rerun it where logs are accessible.
2. Fix the exact failing assertion and require all PR #17 checks to pass.
3. Merge PR #17 only after the green check set is verified.
4. Run one manual workflow dispatch and inspect per-feed diagnostics.
5. Reconcile PR #3 and PR #5 against current `NabzAI-YouTube/main`; keep `buffer_max=10` disabled.
