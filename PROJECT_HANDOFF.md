# NabzKhabar Project Handoff

## Scope
- This repository is for the Telegram news channel only.
- Instagram and YouTube work belongs in the private `NabzAI-YouTube` repository.

## Audit snapshot: 2026-10-29
- Deep re-audit recorded in `docs/review/RE-AUDIT-2026-10-29.md`.
- Open issue: [#18 publication stopped or telemetry is stale](https://github.com/NabzKhabarOfficial/NabzKhabar/issues/18).
- Open hardening PR: [#14](https://github.com/NabzKhabarOfficial/NabzKhabar/pull/14). Do not merge wholesale without recreating its remaining fixes on current `main`.

## Current state
- `v13_monitor.py` reports `publication_gap` when stories were selected but confirmed publications are zero.
- The observed runtime failure was correctly fail-closed: editorial blocks were separated from one ambiguous Telegram outcome.
- Full corpus content verification is not yet complete because large publication files were only partially retrievable.

## P0 gates before broad publication
1. Wire and test `quarantine_guard`, `v13_final_guard`, and `v13_review_log` from the production launcher.
2. Reconcile the ambiguous Madrid train-crash Telegram attempt with the channel/provider before retrying it.
3. Add a durable ambiguous-publication registry and block blind retries.
4. Keep all known quarantine IDs blocked until each is re-extracted from its original source.

## Manual steps required from the owner
1. Open the Telegram channel and search for the Madrid train-crash headline. Record whether it exists and its Telegram message ID.
2. If it exists, do not republish it; send the message ID and timestamp for reconciliation.
3. If it does not exist, do not manually resend it; report that it is absent so the code can create a safe, explicit retry path.
4. Do not edit quarantined HTML or JSON records by guessing names, numbers, or wording.
5. Run the exact current-main verification commands only after the wiring patch lands:
```bash
python -m compileall -q .
python -m unittest discover -s tests -v
python scripts/audit_news_corpus.py
python scripts/check_publication_health.py
```
6. Keep `v13_monitor.json` and `v13_health.json` from the same workflow run.

## Guarantee boundary
The system can validate deterministic filters and telemetry contracts. It cannot guarantee factual truth, source authenticity, or delivery after an ambiguous network timeout.
