# Suggested improvements to the PRD

Status of each: **Proposed** until accepted in [DECISIONS.md](DECISIONS.md). Ordered by impact.

## A. Scope and demo risk (most important)

1. **Cut the MVP to what the demo shows.** The PRD lists ~25 features; the demo uses ~8. Build only: F1, F2, F3, F4 (mock data), F5, F6, M1, M2, M3, M5, M6, P1. Defer: PayPal/Razorpay, WhatsApp, P3 deflection, alerts beyond one email, small-team access, multilingual.
2. **Verify Hindsight in the first session.** It is the core dependency and the least known to us. Spike: Docker up, retain with tags and event dates, recall, reflect, directives, mental model. If anything is missing, fall back to a thin `MemoryStore` interface (see CONTRACTS.md) backed by Postgres + pgvector so the product never depends on one library's quirks. Build everything against the interface.
3. **Make the before/after toggle un-riggable.** Same model, same prompt, same dispute, `temperature=0` and a fixed seed where supported; only the recall step is switched. Show a diff view and the exact memories injected. Pre-run both outputs and cache them as a demo fallback so a slow API cannot kill the demo.
4. **Add one number to the pitch.** Run the offline eval (risk #14) early: N synthetic held-out disputes, recommendation accuracy memory-off vs memory-on, and "draft edits needed" across simulated rounds. A single chart beats five feature claims. State plainly that data is synthetic.

## B. Product correctness

5. **Win probability must not be an LLM guess.** Compute it from counts: seller's own wins/losses for the same reason (+ courier/product when n is enough), shrunk toward the shared-bank rate (Beta prior), shown with an interval and n ("2 of 3 wins, low confidence"). The LLM only explains the number. This also makes M2 confidence real instead of decorative.
6. **Enforce "no unsourced claim" structurally, not by prompt.** Drafting model must return JSON `claims[] = {text, evidence_id}`. A validator rejects any claim whose `evidence_id` does not exist or is `verified=false`; the renderer builds the letter only from validated claims. Seller claims can appear only labelled as the seller's statement.
7. **Customer hash design.** Use per-seller salted HMAC of normalized email (and a second one for device/IP) so repeat disputers are detectable inside a seller bank but hashes cannot be joined across sellers. Never put raw email in memory text — LLM-written memory content can leak it otherwise.
8. **Memory text sanitation.** Retained memory contents are written by us from structured fields (templates), not free LLM prose, for anything customer-related. Free-text seller notes go in as `opinion` type only.
9. **Fast signals (M7) get low weight.** An edit or a fight/accept choice is a preference signal, not proof of what wins. Only confirmed outcomes move belief confidence; edits can propose directives that the seller confirms ("Always include return policy? yes/no"). This avoids a wrong belief from one bad edit.
10. **Add an "accept" win in the demo.** One of the three demo disputes should end in "accept — this looks valid", with memory showing why. It is the strongest proof of principle 4 (honest advice) and differentiates from tools that always fight.

## C. Integration realities

11. **Stripe specifics.** Use test-mode disputes (test card `4000000000000259` creates a fraudulent dispute) and submit through the Disputes update endpoint with structured evidence fields (`shipping_tracking_number`, `customer_communication`, `receipt`, etc.) plus uploaded files, which have size and character limits; the packet builder must map to these fields. Verify exact field names and limits against current Stripe docs before building F5 submission. Webhook events to handle: `charge.dispute.created`, `.updated`, `.closed`.
12. **Mock shop.** F4 needs orders/tracking/IP data that no real shop gives us during a hackathon. Build one small mock-shop service with seeded orders so evidence collection is real code against a real (fake) API, and Shopify can later swap in behind the same `EvidenceCollector` interface.
13. **Visa CE 3.0 as seed knowledge.** Encode the rule that prior undisputed transactions matching device/IP/email strengthen fraud disputes as a checklist rule and seed matching history for the demo customer. Confirm current rule details from Visa/Stripe docs before quoting them to judges.

## D. Positioning and numbers

14. **Soften the statistics.** The 44.6% / 10.7% figures are vendor-reported (Chargebacks911, self-reported). Use "~45% win rate when merchants fight, ~11% net recovery" with the source on the slide and the word "reported".
15. **One-sentence pitch:** "Recoup is the chargeback agent that remembers every dispute you have ever had, and shows its work." Lead with memory, not with the market size.
16. **Name the Indian angle carefully.** Judges may notice chargebacks are less central to UPI. Keep the story "card-accepting and cross-border sellers first", use ₹ amounts in the demo data only if the demo seller is an Indian exporter.

## E. Small additions worth having

17. **Undo/forget for memory** is in the PRD; also add **"why not"** in the inspector (memories considered but not used, with reason) — cheap to build from recall scores and very convincing.
18. **Cost per dispute** displayed in the draft view (tokens + recall calls) to back risk #13 with a number.
19. **Deadline safety:** compute deadlines in UTC from processor `due_by`, show seller-local time, and add a "drafted but not approved" state with an escalating banner — this is the PRD's biggest operational leak and cheap to demo.
