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
- The regression root cause was `v13_hardening._halfspace_text`: regex replacement strings contained `\\u200c`, causing `bad escape \\u` and aborting history persistence. Replacements now use callable functions.
- A fresh CI run is required after this handoff update; do not merge until all checks are green.

## Automatic alerting
- Added `scripts/check_publication_health.py`.
- Added `.github/workflows/publication-watchdog.yml` on `main`, corrected in commit `a946c7c0757321b325eb5bf52903c22b8a0d130c`.
- The watchdog fails on stale/missing telemetry, runtime/publication failure, or all feeds returning zero candidates, then opens/comments on a `publication-outage` issue.

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
1. Verify all PR #17 checks are green, then merge PR #17.
2. Run one manual workflow dispatch and inspect per-feed diagnostics.
3. Reconcile PR #3 and PR #5 against current `NabzAI-YouTube/main`; keep `buffer_max=10` disabled.
4. Perform only the one-item `buffer_max=1` smoke test after current-main CI is green and provider state can be independently verified.
