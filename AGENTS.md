# AI Team Protocol

## Mission
Complete the requested project task end-to-end, not merely suggest steps. Inspect the current repository, recent CI/workflow runs, tests, and existing architecture before editing. Do not ask the user to repeat information already present in the repository or logs.

## Roles and coordination
When subagents or parallel agent tools are actually available, use separate focused roles:
1. **Lead / planner:** define acceptance criteria and identify the smallest safe change.
2. **Implementer:** make the code change on the current feature branch.
3. **Independent reviewer:** inspect the diff for bugs, regressions, security and requirement violations.
4. **Tester:** run targeted tests, then the full available test suite and CI checks.
The lead integrates results and resolves disagreements using code, logs, tests, and documented requirements. Assign disjoint files/tasks to parallel writers; never let agents edit the same file simultaneously. If subagents are unavailable, perform these roles sequentially yourself. Never claim that multiple models/agents collaborated unless they were actually invoked.

## Required workflow
1. Read this file and `CLAUDE.md` (if present), project README, dependency files, tests, and relevant workflows.
2. Inspect current branch/status and recent failed CI runs before changing code.
3. Write down concrete acceptance criteria and a short plan.
4. Reproduce the failure or add a regression test first when practical.
5. Implement the smallest root-cause fix; avoid unrelated rewrites and speculative dependencies.
6. Run targeted tests, full tests, syntax/import checks, and workflow-specific validation where feasible.
7. Review the final diff independently; check secrets, generated files, duplicate logic, API limits, and failure handling.
8. Report exactly what changed, tests and results, unresolved blockers, and any manual steps. Never say “complete” or “all green” without evidence.

## User constraints
- **No paid services, subscriptions, or APIs.** Keep the existing free-tier architecture. Warn before proposing anything that may cost money.
- Never print, commit, or expose tokens, passwords, cookies, or secret values. Do not inspect secret values to debug; report only whether a required variable is present.
- Do not disable quality gates, tests, safety checks, duplicate protection, or publication guards just to make CI green.
- Do not publish, delete production data, rotate secrets, merge a PR, or change account settings unless the user explicitly authorized that specific action.
- Prefer offline tests and mocked external calls. Do not spend API quota for tests unless necessary and explicitly approved.
- Preserve the user's language and content requirements documented in the repository.

## Completion contract
A task is done only when its acceptance criteria are met and tests are reported accurately. If blocked by missing credentials, rate limits, provider quotas, or unavailable hardware, finish all offline work and state the exact external blocker instead of repeatedly retrying.

# NabzKhabar project-specific guardrails

Follow `AGENTS.md` and `CLAUDE.md`.

- Main runtime entry point is `run_bot.py`; respect the V13 standalone architecture and trace the actual import/call path before editing.
- Treat the GitHub Actions workflow `.github/workflows/bot.yml`, runtime logs/telemetry, and regression tests as primary evidence. Inspect the latest failed run and identify the first root-cause failure rather than guessing from the final error.
- Preserve Persian-only publication, clean natural Persian, trusted-source relevance, freshness and critical-news rescue, story/incident deduplication, quality/policy gates, and the Telegram channel URL requirement: `https://t.me/NabzKhabarOfficial`.
- Never weaken publication guards or report success based only on compilation. Test deduplication, critical-news rescue, formatter/output quality, model-router fallback and offline imports where applicable.
- Runtime state files (for example `sent_news.txt`, `ai_model_health.json`, `v13_health.json`, `v13_monitor.json`, rejected-news/history JSON and generated `docs/`) are state/output, not casual hand-edited source. Preserve them unless the task explicitly requires a safe migration.
- Check that model routing does not depend on unavailable/paid providers. Respect free-only constraints and rate limits; use mocks for offline tests.
- Do not send Telegram posts or change secrets during tests.