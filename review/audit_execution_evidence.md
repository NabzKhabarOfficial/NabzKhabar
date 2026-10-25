# Audit and publication safety evidence

Date: 2026-10-25

## Current revisions

- NabzKhabar audit correction: `e2d145e00e5c0bd9d26c8334ac23338b850ac233`
- NabzKhabar quarantine enforcement: `ff299b3c841dc9be2b1436c6364add12c8e907ce`
- NabzAI-YouTube schedule safety: `8e72ee518db2ff4c5a312df922ae54369de38f67`

## Corpus contract

The historical baseline was 1,408 active records, but `docs/news` is a live publication corpus and has grown. The audit now processes every checked-in `docs/news/*.html` file, reports drift from the 1,408 baseline, and validates retired/noindex pages under a separate retired-page schema.

A run is green only when:

- collected equals the current checked-out file count;
- processed equals collected;
- no active or retired structural failures exist;
- every quarantine ID exists;
- no duplicate active content hash exists.

## Execution status

The workflow exists at `.github/workflows/news-audit.yml` and uploads `nabzkhabar-news-corpus-audit` from `review/news_corpus_audit.json`. The previous run correctly exposed the stale-count and retired-page contract defects. Commit `e2d145e00e5c0bd9d26c8334ac23338b850ac233` contains the root fix and triggers a fresh run.

The new run must be checked for the final artifact. No green result is claimed until its JSON reports complete collection and processing with zero failures.
