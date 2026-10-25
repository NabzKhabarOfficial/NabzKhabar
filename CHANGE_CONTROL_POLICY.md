# NabzKhabar Change-Control and Editorial Safety Policy

## Immutable backup
- Backup branch: `backup/immutable-2026-10-25`
- Backup source commit: `c1759b511631334a8c4df399294c203c2398ef90`
- Treat the backup branch as read-only. Never force-push, rebase, delete, or amend it.
- Before any production-risk change, create a new dated backup branch and record its exact source SHA.
- GitHub branch protection must require pull requests, prevent force-pushes, and restrict deletion for backup branches. A branch name alone is not technically immutable.

## High-risk changes requiring review
- Telegram sender, retry/fallback, publication state, candidate selection, editorial gate, source ranking, scheduler, workflow, secrets, or state schema.
- Any change that can alter publication volume, bypass a veto, or turn an ambiguous transport outcome into success.

## Required checks before production
1. Offline compile/import/unit tests.
2. Hardening tests for atomic state and publication outcomes.
3. Static diff review against the immutable backup.
4. One manual workflow run with captured SHA.
5. Confirm `failed_publications=0`, `ambiguous_publications=0`, and no missed selected story.

## Editorial false-block policy
- Keep fail-closed behavior when AI is unavailable for speculative, local, unverified, or non-event material.
- Reduce false blocks only through deterministic, auditable rescue rules for concrete events: deaths/injuries, attacks, disasters, official strategic decisions, ceasefires, sanctions, major economic shocks, and decisive national/global sports results.
- Never rescue a story solely because it contains a high-impact keyword.
- A rescue candidate must still pass the AI happened/scope decision when an AI provider is available.
- Version the editorial cache whenever the rubric or rescue rules change.
- Review `no-ai-fallback-fail-closed` counts separately from genuine editorial rejections. They are not the same failure.

## Current editorial review
- The gate already uses a wider backfill pool, deterministic vetoes, war-zone rescue, strategic-official handling, versioned cache, and non-failure telemetry.
- Recent telemetry shows most blocks are speculative or `no-ai-fallback-fail-closed`, which is evidence to improve provider availability and observability before lowering editorial thresholds.
- Do not lower `MIN_AI_SCORE` globally. That would trade false blocks for false publications.
