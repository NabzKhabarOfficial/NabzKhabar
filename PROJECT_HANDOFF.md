# NabzKhabar Project Handoff

## Scope
- This repository is for the Telegram news channel only.
- Instagram and YouTube work belongs in the private `NabzAI-YouTube` repository.

## Latest operational state: 2026-10-29
- The latest bot run correctly failed closed.
- `v13_health.json`: `selected_for_publication=12`, `published=0`, `failed_publications=1`, `ambiguous_publications=0`.
- The failed publication was the IRNA story `شنیده شدن صدای انفجار در شرق و جنوب عربستان`; it is an explicit failure, not an ambiguous delivery. Do not blindly retry it until the source is rechecked and the failure reason is known.
- The Madrid train-crash story is confirmed present in the Telegram channel by owner-provided channel evidence. It must not be republished. The visible post headline is `استقرار پلیس ضدشورش در مادرید همزمان با اعتراضات مرگبار به حادثه قطار` and the post states 68 deaths and a demand for the transport minister's resignation. A Telegram message ID/link was not included in the evidence provided, so provider-side ID reconciliation remains incomplete.
- `v13_monitor.status=publication_failure` is the intended fail-closed result, not a healthy run.

## Deep audit
- Full re-audit: `docs/review/RE-AUDIT-2026-10-29.md`.
- Large publication corpus remains only partially retrievable through the current connector; do not claim every historical post has been fact-verified.

## P0 gates before broad publication
1. Wire and test `quarantine_guard`, `v13_final_guard`, and `v13_review_log` from the production launcher.
2. Preserve the Madrid story as already published; do not retry it. Record its Telegram message ID if the channel UI exposes it.
3. Re-source and review the IRNA Saudi-explosion story before considering a retry.
4. Add a durable ambiguous-publication registry and block blind retries.
5. Keep all known quarantine IDs blocked until each is re-extracted from its original source.

## Manual steps required from the owner
1. If available, capture the Madrid message ID and permalink from Telegram; do not delete or resend the message.
2. Search for the IRNA Saudi-explosion story using `عربستان`, `انفجار`, `شرق`, `جنوب`. Do not resend or delete it.
3. If the Saudi story exists, send its message ID and timestamp for reconciliation. If absent, report absence only; do not manually resend.
4. Do not edit quarantined HTML/JSON records by guessing names, numbers, or wording.
5. After the wiring patch lands, run:
```bash
python -m compileall -q .
python -m unittest discover -s tests -v
python scripts/audit_news_corpus.py
python scripts/check_publication_health.py
```
6. Keep `v13_monitor.json` and `v13_health.json` from the same workflow run.

## Guarantee boundary
The system can validate deterministic filters and telemetry contracts. It cannot guarantee factual truth, source authenticity, or delivery after an ambiguous network timeout.
