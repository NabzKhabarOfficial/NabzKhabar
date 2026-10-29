# NabzKhabar Project Handoff

## Scope
- This repository is for the Telegram news channel only.
- Instagram and YouTube work belongs in the private `NabzAI-YouTube` repository.

## Audit snapshot: 2026-10-28
- Audited current `main` after the publication-gap alert.
- Open issue: [#18 publication stopped or telemetry is stale](https://github.com/NabzKhabarOfficial/NabzKhabar/issues/18).
- Open hardening PR: [#14](https://github.com/NabzKhabarOfficial/NabzKhabar/pull/14). Do not merge wholesale without recreating its remaining fixes on current `main`.

## Changes applied in this audit
- `v13_monitor.py` now reports `publication_gap` when stories were selected but confirmed publications are zero.
- It distinguishes an all-editorially-blocked run from a transport/publication failure instead of calling both healthy.
- The permanent handoff now records the known quarantine, state-safety, reconciliation and editorial limitations.

## Known production risks
- `content/quarantine_manifest.json` still requires verified wiring into candidate collection and processing. Do not claim quarantined records are blocked until an exact current-main test proves it.
- Some auxiliary writers and senders remain outside the canonical atomic/outcome path.
- Telegram timeouts can be accepted by Telegram even when the client sees no response. Provider-side reconciliation is still required.
- Numeric-presence checks do not prove entity/number correctness or source truth.
- Published data contains known Persian grammar, neutrality, attribution and unsupported-claim defects. Re-source and manually review before republishing.
- Offline tests cannot prove RSS freshness, AI output correctness, Telegram delivery, or factual truth.

## Safe verification sequence
```bash
python -m compileall -q .
python -m unittest discover -s tests -v
python scripts/audit_news_corpus.py
python scripts/check_publication_health.py
```

## Manual-only continuation
1. Run the checks on the exact current `main` commit.
2. Inspect `v13_monitor.json` and `v13_health.json` from the same run.
3. Reconcile every ambiguous Telegram attempt with the channel/provider before retrying.
4. Re-source quarantined and high-risk posts; never “correct” names or numbers by guesswork.
5. Dispatch one controlled workflow run and inspect feed diagnostics before broad scheduling.

## Guarantee boundary
The system can validate deterministic filters and telemetry contracts. It cannot guarantee factual truth, source authenticity, or delivery after an ambiguous network timeout.
