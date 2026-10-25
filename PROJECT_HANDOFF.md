# NabzKhabar Project Handoff

## Scope
- This repository is for the Telegram news channel only.
- Instagram and YouTube work belongs in the private `NabzAI-YouTube` repository.

## Backup and change control
- Immutable-backup candidate branch: `backup/immutable-2026-10-25`
- Backup source snapshot: `c1759b511631334a8c4df399294c203c2398ef90`
- Backup policy: `CHANGE_CONTROL_POLICY.md`
- Editorial review snapshot: `EDITORIAL_GATE_REVIEW.md` on the backup branch.
- The backup branch must be protected in GitHub against force-push and deletion. A branch name alone is not technically immutable.

## Production status
- `run_bot.py` and `v13_ai_extra.py` are the active V13 launch path.
- Atomic JSON/text persistence, tri-state publication outcomes, scheduler hardening, editorial gate, status schema, and health diagnostics are active.
- Latest runtime evidence: `success/healthy`, one published item, zero failed or ambiguous publications, and no missed selected stories.

## Editorial gate review
- The gate uses deterministic vetoes, AI happened/scope/score checks, a wider backfill pool, versioned verdict cache, strategic-position handling, and regional-war rescue.
- Recent blocks were mostly correct speculative/unverified/non-event blocks or `no-ai-fallback-fail-closed` outcomes.
- Do not lower the global score threshold to chase volume. Separate provider-unavailable blocks from editorial rejections and add only narrow, tested event rescues.
- Full recommendations are in `EDITORIAL_GATE_REVIEW.md` on the backup snapshot.

## Known risks
- Telegram accepted-but-lost responses still lack provider-side reconciliation.
- `v13_growth.py` has a direct sender outside the canonical outcome path.
- Some auxiliary state writers remain direct-write and need migration.
- `content/quarantine_manifest.json` is not yet wired into candidate selection.
- Live provider behavior is not proven by static checks alone.

## Required continuation
1. Protect the backup branch in GitHub.
2. Run fresh offline/hardening checks for the latest main documentation commit.
3. Keep editorial fail-closed for speculative/unverified content.
4. Add narrow fixtures before changing rescue rules.
5. Route growth/direct send through canonical outcome and reconcile Telegram provider state.
