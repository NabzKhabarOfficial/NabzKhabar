# NabzKhabar Project Handoff

## Scope
- This repository is for the Telegram news channel only.
- Instagram and YouTube work belongs in the private `NabzAI-YouTube` repository.

## Current branch
- `brain/production-hardening`

## Completed fixes
- Fixed the freshness-rescue/editorial-patch compatibility issue: the active `_critical` predicate and legacy `_is_critical` name are both supported.
- Added concurrency-safe freshness rescue compatibility behavior.
- Hardened content duplicate state handling and runtime health reporting.
- Added `tests/test_runtime_imports.py` for dynamically loaded runtime modules.
- Added the offline CI workflow at `.github/workflows/offline-tests.yml` when repository workflow permissions allow it.
- Restored the full `v13_story_dedup.py` API (`_health`, `COMMON`, number/speaker anchors, follow-up matching). The earlier rewrite had silently disabled the AI event judge (`v13_event_judge`), which depends on these names.

## Important runtime files
- `run_bot.py`: launcher and stack wiring.
- `v13_standalone.py`: Telegram collection, filtering, media, and publishing.
- `v13_freshness_rescue.py`: freshness and consequential-story rescue.
- `v13_editorial_final_patch.py`: final freshness/editorial calibration.
- `v13_story_dedup.py`: publication duplicate guard (also installs text polish, incident dedup, event judge, importance rescue).
- `v13_event_judge.py`: AI same-event judge, active only through `v13_story_dedup.install()`.
- `v13_monitor.py`: runtime and publication health report.
- `.github/workflows/bot.yml`: scheduled production workflow.
- `.github/workflows/offline-tests.yml`: offline compile/import/pytest workflow.

## Required continuation procedure
1. Inspect `main` and the latest commits before changing anything.
2. Run or inspect offline CI first; do not repeat completed fixes.
3. Treat import compatibility, state persistence, duplicate prevention, and health reporting as mandatory.
4. Never use real API calls in offline tests.
5. Do not move Instagram or YouTube code into this repository.
6. After every code, workflow, dependency, state, or documentation change, update this handoff with the latest commit, changed files, current status, blockers, and next action.
7. Verify the exact changed files and report any unverified live behavior honestly.

## Handoff update format
- Last change: `<commit URL>`
- Changed files: `<paths>`
- Verification: `<CI/test/static status>`
- Blockers: `<none or exact blocker>`
- Next action: `<concrete continuation step>`

## Latest update
- Last change: https://github.com/NabzKhabarOfficial/NabzKhabar/commit/f2e42da4956431dc73504ab8bb4d8c9b569d5e87
- Changed files: `v13_story_dedup.py` (restored to the original `e38a027` content, blob 92226d62, byte-identical).
- Verification: static review of `v13_event_judge.py`, `v13_text_polish.py`, `v13_incident_dedup.py`, and `v13_ai_router.py` confirmed the names they use now exist. Not run in live CI yet.
- Blockers: none for code. Remaining known issues below.
- Next action: add an offline test that imports `v13_story_dedup`, calls `install()` with a stub core, and asserts that `v13_event_judge` installed. Then review `v13_monitor.py` (dropped diagnostics; check the health `status` values it gates on) and `voice_check.write_report` (missing `_BEATS`/`_REASON` reset).

## Known verification boundary
- Static code and workflow wiring have been reviewed.
- Live GitHub Actions, Telegram, RSS, and AI provider behavior still requires an actual CI/workflow run.

## Known open risks
- `daily_boards` photo+text duplicate on an ambiguous timeout.
- Non-atomic `_save_health` in `v13_ai_router` (plain write, can corrupt on crash).
- `sent_news.txt` hashes are unbounded.
- `quality_fix` is only installed when Mistral is configured.
- Token leakage risk in logs.
- Cron plus self-dispatch can cause duplicate runs.
- `v13_monitor.py` rewrite dropped diagnostics (`important_missed`, `editorial_blocked`, `skipped_duplicate`, `ai_pool`, `no_publication_candidate`), and the fail-closed gate may misfire on unexpected health statuses.
- `voice_check.write_report` no longer resets `_BEATS` / `_REASON`.
- Private repo CI runs with `NABZ_VOICE_CHECK=0`, so voice check is untested there.


## Production hardening — 2026-10-25
- Current branch: `brain/production-hardening`; safety snapshot: `brain/production-hardening-backup` (both branched from `main`).
- Last change: https://github.com/NabzKhabarOfficial/NabzKhabar/commit/2ccc3e29886dd7dbcdee3663d794912c5ad82955
- Changed files: `daily_boards.py`, `v13_ai_router.py`, `v13_monitor.py`, `v13_status.py`, `.github/workflows/bot.yml`, `tests/test_daily_boards_outcomes.py`, `tests/test_ai_router_safety.py`, `tests/test_status_schema.py`.
- Verified by static inspection: daily-board photo outcomes now distinguish confirmed success, explicit rejection, and ambiguous transport outcomes; ambiguous photo outcomes do not trigger text fallback. Daily-board JSON state and AI health writes use atomic persistence. AI router rejects non-object JSON and redacts configured/common token patterns in exception logs. Monitor uses the canonical publication status schema and reports the requested diagnostics. Removed the self-dispatch keep-alive scheduler; the existing cron and manual dispatch remain.
- Verification: GitHub file reads/writes succeeded. Tests and compile checks have **not yet been run** against this branch; do not treat this batch as green until branch CI completes.
- Blockers/remaining: production state writers across `v13_standalone.py`, intelligence/rejection history, sent-news history, and docs still need atomic migration; publication outcome/reconciliation still needs integration into the primary Telegram sender; workflow YAML validation and full offline CI are pending; voice-check state reset remains an earlier known risk.
- Next action: run all offline checks on this branch, fix any failures, then migrate the next narrow set of production writers and re-run tests. Do not merge PRs automatically.
