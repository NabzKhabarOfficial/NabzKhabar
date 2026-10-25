# Hardening status

Branch: `brain/hardening-p0-p1`

## Completed in this pass
- Added `atomic_state.py` with same-directory tempfile, flush, fsync, atomic replace, and corrupt-file quarantine.
- Added offline regression tests for round trips, Unicode, cleanup, and corruption recovery.

## Remaining verified risks
- Existing production writers still need migration to `atomic_state.save_json`.
- Telegram ambiguous outcomes still need reconciliation before any fallback send.
- Runtime CI must run on this branch before merge.

This file is intentionally explicit: helper availability is not claimed as production migration.
