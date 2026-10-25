# Editorial Gate Review Snapshot

Date: 2026-10-25

## Current behavior
- Deterministic veto blocks non-events and local-level material unless a concrete hard event occurred.
- AI editor requires happened=true, non-local scope, and score >= 7.
- War-zone events use a dedicated rescue path with a lower score threshold.
- Strategic official positions on war, sanctions, nuclear talks, ceasefire, and negotiations are treated as events.
- The gate judges a backfill pool rather than only the first four ranked candidates.
- Cache versioning allows corrected verdicts after rubric changes.

## False-block findings
- The latest healthy run published one story with zero failed or ambiguous publications.
- Many blocks were correct editorial blocks for speculation, analysis, unverified claims, or no-AI fallback.
- `no-ai-fallback-fail-closed` indicates provider availability/structured-output failure, not proof that the story is low-value.
- Do not lower the global score threshold. Improve provider health, preserve reasons, and add narrow event-specific rescue tests instead.

## Review checklist for future gate changes
- Add a fixture for each new rescue rule.
- Test deterministic veto, AI unavailable fallback, cached verdict version, war-zone classification, and official strategic position.
- Compare publication rate and block reasons before and after the change.
- Reject any patch that turns speculative or unverified material into publishable news.
