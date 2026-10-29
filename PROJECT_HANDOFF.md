# NabzKhabar Project Handoff

## Scope
- This repository is for the Telegram news channel only.
- Instagram and YouTube work belongs in the private `NabzAI-YouTube` repository.

## Latest operational state: 2026-10-29
- The latest bot run correctly failed closed.
- `v13_health.json`: `selected_for_publication=12`, `published=0`, `failed_publications=1`, `ambiguous_publications=0`.
- The failed publication source was IRNA story `شنیده شدن صدای انفجار در شرق و جنوب عربستان`; the owner provided matching channel evidence that the event was already published as `انفجارها شرق عربستان را لرزاند؛ پروازها در فرودگاه ملک فهد دمام متوقف شد` at 04:34 on 27 February. Treat it as already published and do not retry or duplicate it. A Telegram message ID/permalink was not provided, so ID-level reconciliation remains incomplete.
- The Madrid train-crash story is also confirmed present in the Telegram channel by owner-provided channel evidence. Do not republish it. A Telegram message ID/permalink was not provided.
- `v13_monitor.status=publication_failure` is the intended fail-closed result, not a healthy run.

## Deep audit
- Full re-audit: `docs/review/RE-AUDIT-2026-10-29.md`.
- Large publication corpus remains only partially retrievable through the current connector; do not claim every historical post has been fact-verified.

## P0 gates before broad publication
1. Wire and test `quarantine_guard`, `v13_final_guard`, and `v13_review_log` from the production launcher.
2. Preserve both Madrid and Saudi-explosion stories as already published; do not retry either.
3. Add a durable publication registry that can reconcile by story/source identity even when Telegram message IDs are unavailable.
4. Keep all known quarantine IDs blocked until each is re-extracted from its original source.

## Manual steps required from the owner
1. No resend or deletion is needed for either reconciled story.
2. If convenient, capture each Telegram message ID/permalink from the channel UI and store it, but this is not a reason to resend.
3. Do not edit quarantined HTML/JSON records by guessing names, numbers, or wording.
4. After the wiring patch lands, run:
```bash
python -m compileall -q .
python -m unittest discover -s tests -v
python scripts/audit_news_corpus.py
python scripts/check_publication_health.py
```
5. Keep `v13_monitor.json` and `v13_health.json` from the same workflow run.

## Guarantee boundary
The system can validate deterministic filters and telemetry contracts. It cannot guarantee factual truth, source authenticity, or delivery after an ambiguous network timeout.
