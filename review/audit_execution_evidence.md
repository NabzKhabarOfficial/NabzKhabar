# Audit and publication safety evidence

Date: 2026-10-25

## Current revisions

- NabzKhabar audit correction: `e2d145e00e5c0bd9d26c8334ac23338b850ac233`
- NabzKhabar quarantine enforcement: `ff299b3c841dc9be2b1436c6364add12c8e907ce`
- NabzAI-YouTube schedule safety baseline: `8e72ee518db2ff4c5a312df922ae54369de38f67`
- Latest YouTube behavior-test commits: `b57301aa1cb81ec90772b11edff9e89283f1ddb7`, `ee8ebd296c74504a7b5f64cc51d409e96348d16a`

## Corpus contract

The historical baseline was 1,408 active records, but `docs/news` is a live publication corpus and has grown. The audit processes every checked-in `docs/news/*.html` file, reports drift from the 1,408 baseline, and validates retired/noindex pages under a separate retired-page schema.

## Verified NabzKhabar execution

- Offline tests: [run #55](https://github.com/NabzKhabarOfficial/NabzKhabar/actions/runs/40204580319), head `eac6c1e`, success.
- Hardening tests: [run #62](https://github.com/NabzKhabarOfficial/NabzKhabar/actions/runs/40204580321), head `eac6c1e`, success.
- Full news audit: [run #5](https://github.com/NabzKhabarOfficial/NabzKhabar/actions/runs/40204580192), head `eac6c1e`, success.
- Audit artifact: [`nabzkhabar-news-corpus-audit`](https://api.github.com/repos/NabzKhabarOfficial/NabzKhabar/actions/artifacts/12603820193), available and unexpired.

The downloaded artifact reported the current corpus count of 1,438 and processed the full corpus. The historical 1,408 number is retained only as baseline drift, not as a failure threshold.

## Execution gate

A final release certification still requires the latest NabzAI-YouTube `main` workflow run after commits `b57301aa` and `ee8ebd29`, because the new behavior-level fallback test was added after the earlier green run.

No live provider smoke is claimed here. YouTube/Buffer external outcomes remain protected by fail-closed claims and require reconciliation on ambiguous results.
