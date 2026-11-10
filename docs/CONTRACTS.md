# Contracts (shared — change only by PR approved by both)

This is the seam between Shivansh's `agent/` and Lakshya's `core/`. Everything else is free to change. JSON shapes below are the source of truth; sample instances live in `fixtures/`. All timestamps are ISO-8601 UTC. Money is integer minor units (cents/paise) plus `currency`.

Version: **v0.5** (bump and note in STATUS.md on any change).
v0.4 (D-13, D-14): approval, acceptance and review endpoints below; `Submission.note`. Shapes are additive, but TWO behaviours change the seam: (1) core renders the final letter itself, using the agent's `render_letter`, instead of taking `letter_md` from the agent; (2) core does not call `POST /agent/disputes/{id}/retain-submission` (that route does not exist); the UI calls `/agent/disputes/{id}/edit` instead.
v0.3 (D-11): seller uploads (`seller_upload`) are never `verified`, like notes and claims. No shape change.
v0.2 (additive, D-9): `Dispute.category_explanation`, new `Seller` and `Submission` entities. Every v0.1 payload is still valid.

## 1. Entities

### Dispute
```json
{
  "id": "dp_001",
  "seller_id": "sel_demo",
  "processor": "stripe",
  "processor_dispute_id": "du_123",
  "amount": 12900,
  "currency": "usd",
  "reason_raw": "product_not_received",
  "category": "not_received",
  "category_explanation": "The customer says the order never arrived.",
  "status": "needs_response",
  "created_at": "2026-10-01T10:00:00Z",
  "deadline_at": "2026-10-08T23:59:59Z",
  "customer_hash": "c_9f2a...",
  "order_id": "ord_55",
  "product_sku": "SKU-MUG-01",
  "courier": "CourierX",
  "evidence": ["ev_1", "ev_2"]
}
```
`category` ∈ `not_received | unauthorized | not_as_described | duplicate | subscription_cancelled | refund_not_processed | other`. Set by the agent classifier (`POST /agent/classify`); `core` stores it.
`category_explanation` (v0.2, optional, may be `null`): the classifier's one-line plain-language explanation (F2), shown in the inbox. Stored by `core` from the classifier result.
`status` ∈ `needs_response | drafted | approved | submitted | won | lost | accepted`.

### Seller (v0.2, produced by core)
```json
{
  "id": "sel_demo",
  "name": "Demo seller",
  "processor": "stripe",
  "processor_account_id": null,
  "currency": "usd",
  "created_at": "2026-10-01T00:00:00Z"
}
```
`processor_account_id` is the processor's account id (for example a Stripe Connect `acct_…`) and is used to route webhooks to a seller. `null` means the single demo seller.

### Submission (v0.2, produced by core)
```json
{
  "id": "sub_1",
  "dispute_id": "dp_001",
  "draft_id": "dr_1",
  "letter_md": "...the approved letter...",
  "status": "submitted",
  "approved_at": "2026-10-03T09:00:00Z",
  "submitted_at": "2026-10-03T09:00:05Z",
  "pdf_uri": "files/sub_1.pdf",
  "error": null
}
```
`status` ∈ `pending | submitted | exported | failed`. `exported` means a PDF was produced for manual upload, for processors without API submission. A Submission exists only after seller approval (`approved_at` is required). Nothing is ever submitted without it.

### EvidenceItem (produced by core, consumed by agent)
```json
{
  "id": "ev_1",
  "dispute_id": "dp_001",
  "type": "delivery_proof",
  "source": "shipping_api",
  "verified": true,
  "summary": "Delivered 2026-09-28 14:02, signed 'J. Doe', photo attached",
  "uri": "files/ev_1.jpg",
  "captured_at": "2026-09-28T14:02:00Z"
}
```
`type` ∈ `order_receipt | delivery_proof | tracking | ip_device | prior_orders | customer_message | refund_policy | seller_upload | seller_note`.
`source` ∈ `stripe | shipping_api | shop_api | seller_upload | seller_claim`.
**Rule:** `verified=true` only for system-pulled data. `seller_note`, `seller_upload` and anything with source `seller_claim` or `seller_upload` are always `verified=false` and can never back a claim (D-11; enforced by a database CHECK).

### MemoryRef (produced by agent)
```json
{
  "id": "mem_77",
  "kind": "case",
  "text": "Won 'not received' (CourierX) with delivery photo, Aug 2026",
  "confidence": 0.85,
  "n_supporting": 3,
  "event_date": "2026-08-14",
  "used": true,
  "why": "Same reason + same courier",
  "editable": true
}
```
`kind` ∈ `case | belief | directive | mental_model | pattern | customer_history | opinion`. `used=false` entries are the "considered but not used" list in the Inspector.

### Draft (produced by agent)
```json
{
  "dispute_id": "dp_001",
  "memory_mode": "on",
  "advice": {
    "action": "fight",
    "win_probability": 0.72,
    "interval": [0.45, 0.89],
    "n_cases": 5,
    "basis": "seller_history+shared_prior",
    "amount_vs_cost": "Dispute $129 vs fee $15; worth fighting",
    "rationale": ["..."]
  },
  "checklist": [{"item": "Delivery proof", "status": "available", "evidence_id": "ev_1"}],
  "claims": [{"text": "Parcel was delivered on 28 Sep.", "evidence_id": "ev_1"}],
  "letter_md": "...rendered only from validated claims...",
  "memory": [ /* MemoryRef[] */ ],
  "cost": {"input_tokens": 0, "output_tokens": 0, "recall_calls": 0, "usd": 0.0}
}
```
`action` ∈ `fight | accept`. Every item in `claims` must reference an existing, `verified=true` evidence id, or be dropped by the validator.

## 2. Endpoints

`core` = Lakshya's router, `agent` = Shivansh's router, same FastAPI app, mounted at `/core` and `/agent`.

| Method + path | Owner | Purpose |
|---|---|---|
| `POST /core/webhooks/stripe` | core | Receive `charge.dispute.*`; create/update Dispute; then call `POST /agent/classify` |
| `GET /core/disputes` · `GET /core/disputes/{id}` | core | Inbox, detail (includes evidence) |
| `POST /core/disputes/{id}/evidence` | core | Seller upload / note |
| `POST /agent/classify` | agent | body: raw reason + processor → `{category, explanation}` |
| `POST /agent/disputes/{id}/draft?memory=on\|off` | agent | Returns **Draft**. Agent fetches dispute+evidence from `core` (`GET /core/disputes/{id}`) |
| `POST /agent/disputes/{id}/edit` | agent | Seller edited draft / changed decision → retain fast signal. body: `{before, after, decision}` |
| `POST /core/disputes/{id}/letter-preview` | core | (v0.4) body **LetterRequest** `{claims:[{text,evidence_id}], seller_statement?, attach_upload_ids[], agent_claims?[]}` -> `{letter_md, letter_sha256, blocked:[{index,evidence_id,reason}], attachments[]}`. Renders exactly what approval would send; never fails on unsourced claims, it reports them |
| `PUT /core/disputes/{id}/draft?memory_mode=on\|off` · `GET /core/disputes/{id}/draft` | core | (v0.4) save / read the seller's working draft (LetterRequest). Saving moves `needs_response` to `drafted` |
| `POST /core/disputes/{id}/approve` | core | (v0.4) body **ApproveRequest** = LetterRequest + `approved: true` + `letter_sha256` from the preview the seller reviewed. Validates every claim against the DB (evidence must exist on this dispute and be `verified`), re-renders, rejects a stale hash (409 `stale_review`), builds the PDF packet, then submits to the processor if possible (else exports). Returns **Submission**. The dispute becomes `submitted` only after the processor confirms; an export leaves it `approved` |
| `POST /core/disputes/{id}/accept` | core | (v0.4) body `{confirm: true}` -> `{status:"accepted", closed_at_processor, note}`. Closes with the processor when a test key is configured, otherwise records it locally and says so |
| `GET /core/disputes/{id}/submission` · `GET /core/submissions/{id}/pdf` · `GET /core/processor-status` | core | (v0.4) latest Submission; the packet PDF (download); `{can_submit, reason}` so the UI can say whether approval will really send |
| `POST /agent/disputes/{id}/outcome` | agent | body: `{outcome: won\|lost, closed_at}` → retain + reflect; returns belief changes |
| `GET /agent/memory?dispute_id=` | agent | Inspector data (MemoryRef[]) |
| `PATCH /agent/memory/{id}` · `DELETE /agent/memory/{id}` | agent | Seller corrects/deletes a memory or belief |
| `GET /agent/playbook` | agent | Seller Playbook (markdown + structured sections) |
| `GET /agent/beliefs/changes?since=` | agent | Belief diffs for "confidence 60% → 85%" UI |
| `GET /core/insights` | core | Root-cause dashboard numbers (computed from SQL, not LLM) |
| `POST /core/alerts/run` · `GET /core/alerts` | core | (v0.5, D-15) send the 72h/24h/6h deadline warnings that are due (once per dispute and threshold; only disputes still waiting on the seller); list them. **Alert** `{id, dispute_id, threshold_hours: 72\|24\|6, channel: email\|simulated, status: sent\|failed\|superseded, subject, body, to_address?, error?, sent_at}`. `simulated` means no email was delivered and the UI must say so |

Errors: `{ "error": "code", "detail": "..." }` with proper HTTP status, for every route under `/core` and `/agent` (including 404s and 422 validation errors).

## 3. MemoryStore interface (agent-internal, but fixed so it is swappable)

```python
class MemoryStore(Protocol):
    def retain(self, seller_id: str, content: str, *, kind: str, tags: list[str],
               event_date: date, verified: bool, meta: dict) -> str: ...
    def recall(self, seller_id: str, query: str, *, tags: list[str] | None = None,
               budget: int = 8) -> list[MemoryRef]: ...
    def reflect(self, seller_id: str, question: str) -> str: ...
    def set_directive(self, seller_id: str, text: str) -> str: ...
    def delete(self, seller_id: str, memory_id: str) -> None: ...
```
Implementations: `HindsightStore` (default), `PgVectorStore` (fallback). Banks: `seller-{id}` and read-only `shared-patterns`.

## 4. Tags

`reason:<category>`, `courier:<name>`, `product:<sku>`, `customer:<hash>`, `outcome:<won|lost|pending>`, `processor:<name>`.

## 5. Fixtures (shared)

`fixtures/disputes/*.json` (Dispute + evidence), `fixtures/drafts/*.json` (Draft samples, memory on and off), `fixtures/memory/*.json` (MemoryRef lists). Created in Phase 0 by whoever finishes their part first; keep in sync with this file.
