"""PayPal adapter: the processor-specific half of Countercase.

Everything above this package (agent, letter, packet, approval, insights) is processor-agnostic.
This package only knows how to (1) talk to the PayPal REST API, (2) turn PayPal disputes and
webhooks into DisputeRow / EvidenceRow, and (3) send an approved response back.
"""
