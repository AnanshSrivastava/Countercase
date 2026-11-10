# PayPal fixtures

Webhook events shaped like PayPal's `CUSTOMER.DISPUTE.*` payloads (resource = the dispute object).
They are hand-written to the documented shape, not recordings: confirm against a real sandbox
event before relying on any field. `invoice_number` is `ord_102` so the mock shop can match it.

Replay one locally (needs `DEMO_TOOLS=1` and `PAYPAL_VERIFY_WEBHOOKS=0`):

    python scripts/paypal_simulate.py fixtures/paypal/dispute_created_not_received.json
