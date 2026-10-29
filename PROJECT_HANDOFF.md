# NabzKhabar Project Handoff

## Scope
- This repository is for the Telegram news channel only.
- Instagram and YouTube work belongs in the private `NabzAI-YouTube` repository.

## Latest operational state: 2026-10-29
- Latest bot run correctly failed closed: selected 12, published 0, 1 explicit failed attempt, 11 editorial blocks.
- The explicit IRNA Saudi-explosion item and the Madrid item were later confirmed by owner evidence as already published under different headlines. Neither may be retried or duplicated.
- `sitecustomize.py` already wires `quarantine_guard` launcher, candidate, editor and final guards through the production import lifecycle. Regression coverage is now added in `tests/test_production_guard_wiring.py`.

## Deep audit
- Full re-audit: `docs/review/RE-AUDIT-2026-10-29.md`.
- Large publication corpus remains only partially retrievable through the current connector; do not claim every historical post has been fact-verified.

## Remaining P0/P1 gates
1. Add durable story/source reconciliation for already-published and ambiguous outcomes; block duplicate retries.
2. Add a durable ambiguous-publication registry with request hash, timestamp, and reconciliation state.
3. Keep all known quarantine IDs blocked until each is re-extracted from its original source.
4. Preserve source URL, publisher, retrieval time and claim status internally.
5. Add entity/number/unit/period validation beyond numeric-token presence.

## Manual steps required from the owner
1. Do not resend or delete the Madrid or Saudi-explosion stories.
2. Branch protection for the Nabz AI backup branch is optional and unavailable on the current private-plan integration; keep the snapshot SHA documented.
3. After the next wiring/test commit, run:
```bash
python -m compileall -q .
python -m unittest discover -s tests -v
python scripts/audit_news_corpus.py
python scripts/check_publication_health.py
```
4. Keep `v13_monitor.json` and `v13_health.json` from the same workflow run.

## Guarantee boundary
The system validates deterministic filters and telemetry contracts. It cannot guarantee factual truth, source authenticity, or delivery after an ambiguous network timeout.
