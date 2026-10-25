# Audit and publication safety evidence

Date: 2026-10-25

## Exact final revisions

- NabzKhabar: `ff299b3c841dc9be2b1436c6364add12c8e907ce`
- NabzAI-YouTube: `8e72ee518db2ff4c5a312df922ae54369de38f67`

## Scope

- Target news population: 1,408 files under `docs/news/*.html`.
- Quarantine manifest: 15 IDs.
- Offline publication fixture: `NabzAI-YouTube/tests/fixtures/publication_outcomes.json`.
- Offline publication tests: `NabzAI-YouTube/tests/test_publication_outcomes.py`.

## Cases recorded

1. YouTube timeout after server-side acceptance: no second insert, claim becomes `ambiguous`.
2. YouTube deterministic `publishAt` rejection: only a controlled fallback is attempted.
3. YouTube fallback without confirmed `publishAt`: claim does not become a confirmed scheduled publication.
4. Buffer create timeout: no mutation retry, claim becomes `ambiguous`.
5. Buffer delete timeout: no blind replacement, delete claim becomes `ambiguous`.
6. Quarantine record: blocked by exact ID or normalized stored-page title.
7. Editorial score outside 0-10 or unknown scope: rejected.

## Execution status

The user reports that the manually started GitHub Actions runs were green. The connected session did not expose run IDs or logs, so this report labels that status **user-reported**, not independently verified here.

The complete 1,408-body audit is still pending a runner artifact from `scripts/audit_news_corpus.py`. The repository now contains the executable audit and evidence receipt; no claim of full body-level coverage is made until the artifact proves `collected=1408`, `processed=1408`, no structural failures, and no missing quarantine IDs.

## Final review status

The final static review confirms the main duplicate-publication blockers are fail-closed at the latest commits. Remaining certification requirement: attach the latest Actions run IDs and the complete audit artifact from the current heads above.
