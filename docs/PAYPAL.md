# Countercase x PayPal: architecture

Countercase defends small sellers against PayPal disputes. PayPal tells us a buyer opened a dispute,
an agent assembles only verified evidence, drafts a source-linked response, the seller approves
it, and Countercase sends it back through PayPal's Disputes API.

## Layers

```
 PayPal sandbox                              Seller (browser)
  | webhooks CUSTOMER.DISPUTE.*                   |
  v                                               v
+--------------------------- FastAPI -------------------------------+        +-- Next.js --+
| core/paypal/ingest.py   verify -> dedupe -> upsert -> classify    |        | inbox       |
| core/paypal/collector   PayPal txn record + shop facts (verified) |  <-->  | dispute page|
| core/paypal/submitter   provide-evidence / accept-claim           |        | insights    |
| core/paypal/client      OAuth, REST, webhook verification         |        | (AG Grid)   |
|------------------------------------------------------------------ |        +-------------+
| core/*  (processor-agnostic): disputes, evidence, deadlines,      |
|         letter + hashed approval, PDF packet, insights, alerts    |
| agent/* (processor-agnostic): classifier, checklist, claim        |
|         generator (LLM), validator, fight-or-accept scorer        |
+----------------------------+--------------------------------------+
                             |
                        PostgreSQL
```

Rule that holds everywhere: **no claim without a verified source**. The LLM only proposes claims;
`agent/validator.py` blocks any claim whose evidence is missing or unverified, and approval is
bound to a SHA-256 of the exact letter the seller reviewed.

## What is PayPal-specific

| Concern | File | Notes |
|---|---|---|
| REST + auth | `core/paypal/client.py` | OAuth client credentials, sandbox-only guard, multipart provide-evidence |
| Webhooks | `core/paypal/ingest.py`, route `POST /core/webhooks/paypal` | verified with PayPal's verify-webhook-signature using the raw body |
| Vocabulary | `core/paypal/mapping.py`, `agent/rules.py` (`PAYPAL_REASONS`) | reason -> category, status/outcome -> status, decimal strings -> minor units |
| Evidence out | `core/paypal/mapping.build_evidences` | PROOF_OF_FULFILLMENT (carrier + tracking) and OTHER (notes + PDF) |
| Evidence in | `core/paypal/collector.py` | PayPal transaction record as `order_receipt`, merged with shop evidence |
| Storage | migration `0005_paypal.py` | `paypal_events` ledger, `disputes.tracking_number`, `disputes.processor_meta`, evidence source `paypal` |

Stripe still works: `MultiSubmitter` picks the submitter by `dispute.processor`.

## PayPal flow

1. Buyer opens a dispute -> PayPal posts `CUSTOMER.DISPUTE.CREATED`.
2. `verify_and_parse` checks the signature with PayPal; duplicate event ids are dropped.
3. A `DisputeRow` is created (`processor="paypal"`), the reason is classified, the buyer is
   hashed (never stored), and the deadline comes from `seller_response_due_date`.
4. `PayPalCollector` stores PayPal's own transaction record plus shop order/shipping/policy facts,
   all `verified=true`.
5. The agent drafts claims; the seller edits and approves; `approve` builds the PDF packet.
6. `PayPalSubmitter.submit` calls `provide-evidence` with the submission id as `PayPal-Request-Id`.
   Without credentials, or past the deadline, the PDF is exported instead and the UI says so.
7. `CUSTOMER.DISPUTE.RESOLVED` updates the outcome; the agent records it.

## Verify against the live sandbox first (not testable offline)

### Local Sandbox checkout

Countercase includes a local-only checkout at `/sandbox-checkout` to create a test sale before
opening a dispute. The API creates a fixed `$10.00 USD` Orders v2 purchase and captures it only
after the Sandbox buyer approves. The amount is not accepted from browser input, and the PayPal
Client Secret remains on the API server. The UI requires the business account associated with the
Sandbox REST app and a Personal Sandbox buyer account.

PayPal may reject domestic INR transactions for some account regions. The checkout uses USD, but
currency alone does not change whether PayPal classifies a payment as domestic or international;
use a supported cross-border pair of Sandbox accounts for a goods/services payment. See PayPal's
[Sandbox account guide](https://developer.paypal.com/sandbox-testing/accounts) and
[checkout integration guide](https://developer.paypal.com/studio/checkout/standard/integrate).

This test page does not create Countercase shop orders or attach evidence to a dispute. It only
creates the Sandbox payment needed to exercise PayPal's dispute flow. It must not be exposed with
real customer or PayPal data while the app has no authentication.

The PayPal Sandbox JS SDK is loaded in the browser using the public Client ID. The API uses the
existing `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, and sandbox base URL from `.env` for the
server-side create and capture calls. Restart both services after changing credentials:
`docker compose restart api web`.

### Unverified assumptions

The test suite stubs PayPal, so these are the assumptions to confirm with a real sandbox dispute:

- `provide-evidence` multipart: document parts keyed by file name and listed in `documents[].name`.
- `carrier_name_other` for carriers outside PayPal's enum, and the carrier enum values in `KNOWN_CARRIERS`.
- `accept-claim` with `accept_claim_reason: REASON_NOT_SET`.
- Webhook `resource` shape (fixtures in `fixtures/paypal/` follow the docs, they are not recordings).
- Transaction Search returns the sale for `seller_transaction_id` (reporting can lag a few hours).
- `dispute_outcome.outcome_code` values; `DENIED` is intentionally left unmapped.

## Not built (do not claim)

Refund-type evidence (`PROOF_OF_REFUND`) needs refund ids we do not collect, so those disputes go
out as `OTHER`. Buyer messages are not ingested. Win-rate numbers in the UI come from synthetic
seed data, not from PayPal.
