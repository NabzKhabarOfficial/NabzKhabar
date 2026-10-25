# NabzKhabar Project Handoff

## Scope
- This repository is for the Telegram news channel only.
- Instagram and YouTube work belongs in the private `NabzAI-YouTube` repository.

## Current branch
- `brain/production-hardening`
- Backup: `brain/production-hardening-backup`

## Production hardening status
- PR: https://github.com/NabzKhabarOfficial/NabzKhabar/pull/15
- Previous helper PR: https://github.com/NabzKhabarOfficial/NabzKhabar/pull/14
- Both PRs remain open and unmerged by design.
- Current PR head before this handoff refresh: `fd88f5651911e6055b29a77f74a708a0327a32cf`.
- This documentation update creates a new head and requires fresh CI before it is called green.

## Verified implementation
- `run_bot.py` and `v13_ai_extra.py` are the active V13 launch path; the production workflow invokes `python v13_ai_extra.py`.
- Atomic JSON/text persistence uses fsync, atomic replacement, and corrupt-state quarantine.
- Daily-board photo outcomes distinguish confirmed success, explicit failure, and ambiguous transport outcomes; ambiguous photo outcomes do not trigger text fallback.
- AI router requires object-shaped JSON and redacts configured/common credential-like values before logging.
- Canonical publication status schema and monitor diagnostics are present.
- Cron self-dispatch keep-alive was removed; scheduled and manual triggers remain.
- `sent_news.txt` is bounded to 5,000 hash entries and atomically replaced, with compaction regression tests.
- Persian language, freshness, duplicate, source-quality, media-claim, editorial, and AI-failure gates are active in the V13 stack.

## Evidence
- Prior complete checks for the previous PR head:
  - Telegram offline regression: https://github.com/NabzKhabarOfficial/NabzKhabar/actions/runs/40159050592/job/121066535511
  - offline: https://github.com/NabzKhabarOfficial/NabzKhabar/actions/runs/40159050594/job/121066535326
  - hardening/offline: https://github.com/NabzKhabarOfficial/NabzKhabar/actions/runs/40159046923/job/121066526149
- Those checks are historical evidence for `fd88f5651911e6055b29a77f74a708a0327a32cf`; fresh checks are required for this handoff commit.
- No live Telegram, RSS, or AI-provider verification has been performed.

## Known remaining risks and blockers
- Primary Telegram sender still lacks a durable provider-side reconciliation ledger for accepted-but-lost responses. Tri-state outcomes prevent blind fallback/retry but do not prove remote state.
- `v13_growth.py` has a direct publication path that does not yet share the canonical outcome/reconciliation contract.
- Remaining state writers in intelligence/rejection history, docs/review, and auxiliary modules need a complete atomic-writer audit/migration.
- `content/quarantine_manifest.json` is documented but not yet wired into the production candidate-selection gate; records require re-extraction from original sources before correction.
- Large content populations (`docs/review/telegram_log.json`, `docs/review/rejected_log.json`, `v13_rejected_news.json`, `sent_news.txt`, and the full `docs/news/` tree) were not fully enumerable in the connector response, so no exhaustive claim is made.
- Live platform behavior remains `NOT VERIFIED`.

## Required continuation
1. Wait for fresh checks for the handoff commit and verify the exact SHA.
2. Wire the quarantine manifest into candidate selection without suppressing legitimate fresh news.
3. Add a durable Telegram reconciliation record and route every direct publication path, including growth/digest, through the canonical outcome contract.
4. Audit and migrate remaining production state writers and add restart/concurrency tests.
5. Keep PRs open and do not merge automatically.
