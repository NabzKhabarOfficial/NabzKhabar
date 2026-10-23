# NabzKhabar Project Handoff

## Scope
- This repository is for the Telegram news channel only.
- Instagram and YouTube work belongs in the private `NabzAI-YouTube` repository.

## Current branch
- `main`

## Completed fixes
- Fixed the freshness-rescue/editorial-patch compatibility issue: the active `_critical` predicate and legacy `_is_critical` name are both supported.
- Added concurrency-safe freshness rescue compatibility behavior.
- Hardened content duplicate state handling and runtime health reporting.
- Added `tests/test_runtime_imports.py` for dynamically loaded runtime modules.
- Added the offline CI workflow at `.github/workflows/offline-tests.yml` when repository workflow permissions allow it.

## Important runtime files
- `run_bot.py`: launcher and stack wiring.
- `v13_standalone.py`: Telegram collection, filtering, media, and publishing.
- `v13_freshness_rescue.py`: freshness and consequential-story rescue.
- `v13_editorial_final_patch.py`: final freshness/editorial calibration.
- `v13_story_dedup.py`: publication duplicate guard.
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

## Known verification boundary
- Static code and workflow wiring have been reviewed.
- Live GitHub Actions, Telegram, RSS, and AI provider behavior still requires an actual CI/workflow run.
