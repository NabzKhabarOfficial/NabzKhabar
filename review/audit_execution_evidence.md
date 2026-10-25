# Audit and publication safety evidence

Date: 2026-10-25

## Exact revisions

- NabzKhabar: `ae92fd4768ddda209ae5e0f2b16d49fef7a6c9bc`
- NabzAI-YouTube safety baseline: `8fda7a6db1a749bbb85bd745f414d5ee5acec7d0`

## Scope

- Target news population: 1,408 files under `docs/news/*.html`.
- Quarantine manifest: 15 IDs.
- Offline publication fixture: `NabzAI-YouTube/tests/fixtures/publication_outcomes.json`.
- Offline publication tests: `NabzAI-YouTube/tests/test_publication_outcomes.py`.

## Cases recorded

1. YouTube timeout after server-side acceptance: no second insert, claim becomes `ambiguous`.
2. YouTube deterministic `publishAt` rejection: one controlled fallback is allowed.
3. Buffer create timeout: no mutation retry, claim becomes `ambiguous`.
4. Buffer delete timeout: no blind replacement, delete claim becomes `ambiguous`.
5. Quarantine record: blocked before publication.
6. Editorial score outside 0-10 or unknown scope: rejected.

## Execution status

The source and fixtures are committed. Hosted GitHub Actions execution is **not certified in this evidence file**: the connected GitHub session returned 404 for the private Actions pages, and the current token could not create/update workflow files because it lacks the `workflow` scope.

The complete 1,408-body audit is therefore still pending actual runner execution. This file intentionally records the gap instead of claiming green tests.
