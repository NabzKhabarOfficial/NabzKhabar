# NabzKhabar Project Handoff

## Scope
- This repository is for the Telegram news channel only.
- Instagram and YouTube work belongs in the private `NabzAI-YouTube` repository.

## Current branch
- `brain/production-hardening`
- Backup branch: `brain/production-hardening-backup`

## Production hardening status
- PR: https://github.com/NabzKhabarOfficial/NabzKhabar/pull/15
- Previous helper PR: https://github.com/NabzKhabarOfficial/NabzKhabar/pull/14
- PRs remain open and unmerged by design.
- Latest hardening evidence commit: https://github.com/NabzKhabarOfficial/NabzKhabar/commit/de213df544a3532a9d39d975908c2b9d30216f2c
- Latest content quarantine commit: https://github.com/NabzKhabarOfficial/NabzKhabar/commit/77fb6b7d97ca59caefb5444abe9cf3414b2829ed

## Completed and verified
- Atomic JSON/text persistence helpers with fsync, atomic replacement, and corrupt-state quarantine.
- Daily-board photo outcomes distinguish confirmed success, explicit failure, and ambiguous transport outcomes; ambiguous photo outcomes do not trigger text fallback.
- AI router requires object-shaped JSON and redacts configured/common credential-like values before logging.
- Canonical publication status schema and monitor diagnostics restored.
- Cron self-dispatch keep-alive removed; scheduled and manual triggers remain.
- `sent_news.txt` bounded to 5,000 hash entries and atomically replaced, with compaction regression tests.
- Offline compile/import/regression checks have passed on the current hardening line; latest Telegram regression check was still running at the last observation.
- Content audit completed for all 100 `docs/guard_log.json` events and 15 confirmed defective records visible in `docs/items.json`.
- Added `CONTENT_AUDIT.md` and `content/quarantine_manifest.json` for verified defective records that must not be republished before re-sourcing.

## Latest CI observation
- Latest observed workflow: https://github.com/NabzKhabarOfficial/NabzKhabar/actions/runs/40158642188
- Offline check: passed.
- Telegram offline regression: queued/in progress at the last observation; re-check before merge.
- No live Telegram, RSS, or AI provider verification has been performed.

## Known remaining risks and blockers
- Primary Telegram sender still lacks a durable provider-side reconciliation ledger for accepted-but-lost responses; tri-state outcomes prevent blind fallback/retry but do not prove remote state.
- `v13_growth.py` has a direct publication path that needs to share the canonical outcome/reconciliation contract.
- Remaining state writers in intelligence/rejection history, docs/review, and some auxiliary modules need a complete atomic-writer audit/migration.
- The quarantine manifest is documented but must be wired into the production selection gate and each record re-extracted from its original source before correction.
- Large content populations (`docs/review/telegram_log.json`, `docs/review/rejected_log.json`, `v13_rejected_news.json`, `sent_news.txt`, and the full `docs/news/` tree) were not fully enumerable in the connector response; no exhaustive claim is made for them.
- Live platform behavior remains unverified.

## Required continuation procedure
1. Inspect `main`, latest commits, current workflows, and state schemas before changing anything.
2. Run offline CI before changing behavior; never repeat completed fixes blindly.
3. Keep import compatibility, atomic persistence, duplicate prevention, outcome classification, and health reporting mandatory.
4. Never use real API calls in offline tests.
5. Keep Telegram code in this repository; do not copy Instagram or YouTube modules here.
6. After every code, workflow, dependency, state, content, or documentation change, update this handoff with the latest commit, changed files, verification, blockers, and next action.
7. Separate static/offline verification from live-platform verification.

## Handoff update format
- Last change: `<commit URL>`
- Changed files: `<paths>`
- Verification: `<CI/test/static status>`
- Blockers: `<none or exact blocker>`
- Next action: `<concrete continuation step>`

## Next action
- Re-check the latest Telegram regression workflow.
- Wire `content/quarantine_manifest.json` into the production candidate-selection gate.
- Add a durable Telegram reconciliation record and route all direct publication paths, including growth/digest, through the canonical outcome contract.
- Audit and migrate the remaining state writers, then rerun full offline CI.
- Do not merge PRs automatically.
