# fixtures/ (shared — change only via PR approved by both)

Sample data matching docs/CONTRACTS.md v0.1. Both halves build against these until the live endpoints exist.
`apps/api/tests/test_fixtures.py` validates every dispute file against the contract models.

- `disputes/*.json` — `{ "dispute": Dispute, "evidence": EvidenceItem[] }` (shape of `GET /core/disputes/{id}`). dp_001 not received (fight), dp_002 unauthorized with prior orders (fight), dp_003 not as described (likely accept).
- `drafts/dp_001_memory_{off,on}.json` — Draft samples for the before/after toggle (Shivansh). Evidence ids refer to dp_001_not_received.json.
- `memory/dp_001_memory.json` — MemoryRef list for the Inspector (Shivansh).

All data is synthetic. Demo seller: cross-border, USD (open question in STATUS.md; change here if we pick ₹).
