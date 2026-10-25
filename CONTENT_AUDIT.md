# Telegram content audit

Branch: `brain/production-hardening`

## Verified coverage
- `docs/guard_log.json`: 100 blocked events, 77 unique titles, all 100 inspected.
- `docs/items.json`: 15 records with confirmed content defects inspected from the available branch snapshot.

## Confirmed published-record defects requiring quarantine/re-source
- `20261024-211632-d4ea37`: malformed phrase `صف می ستند`.
- `20261024-154459-933f4d`: incomplete/meaningless title.
- `20261024-143618-5e4409`: malformed title/lead.
- `20261024-125641-faffb3`: malformed speaker prefix.
- `20261024-113313-140f0f`: unintelligible detail sentence.
- `20261024-110450-abc6a0`: malformed sentence/meaning boundary.
- `20261024-090814-2b6637`: spelling defect in group name.
- `20261024-081954-c64e41`: ambiguous proper name.
- `20261024-080221-c4a396`: unintelligible place/name token.
- `20261024-190130-aab041`: incomplete grammar/statistic wording.
- `20261024-193915-099c8b`: ambiguous statistic with missing exact count.
- `20261024-200811-7adfbc`: security/military claim without source URL in record.
- `20261024-174422-7241c2`: ambiguous actor/action wording.
- `20261024-163250-ff140d`: Starshield/Starlink claim needs source match.
- `20261024-091930-9c3ea0`: heavy numeric claims without source URL.

## Safe handling decision
These records are documented as defects, not silently rewritten. A definitive correction requires the original source/article text. Guessing replacement wording would create a new factual defect. The publication pipeline must quarantine these IDs until re-extraction and source verification are available.

## Coverage boundary
Large files (`docs/review/telegram_log.json`, `docs/review/rejected_log.json`, `v13_rejected_news.json`, `sent_news.txt`, and the full `docs/news/` tree) were not fully enumerable in the connector response. This document makes no false exhaustive claim for those populations.

## Next action
Add the quarantine manifest to the production selection gate, then re-source each ID before allowing republish. Run the complete offline suite afterward.
