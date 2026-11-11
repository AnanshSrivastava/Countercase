# Countercase — Product Requirements (source of truth, v1 as pasted 2026-11-07)

> Changes we propose are in [IMPROVEMENTS.md](IMPROVEMENTS.md); accepted ones are logged in [DECISIONS.md](DECISIONS.md). Edit this file only when a decision is accepted.

## 1. Problem

When a customer files a dispute ("item not received", "unauthorized purchase"), the seller's money is pulled back immediately and they get only a few days to submit evidence. Small sellers handle this ad hoc: they send whatever proof they have, rarely know what wins, and repeat the same mistakes.

- ~281 million card chargebacks forecast for 2026 (Datos Insights / Mastercard, via Justt; other forecasts ~286M).
- Merchants win ~44.6% of the disputes they fight, but net recovery across all chargebacks is only ~10.7% (Chargebacks911 2026 Field Report, self-reported; directional).
- The gap is mostly operational: disputes go unfought, deadlines are missed, or the wrong evidence is sent.
- US merchants lose ~$5.13 per $1 of fraud once fees and operations are counted (LexisNexis True Cost of Fraud 2026).

*Root cause:* sellers never learn from past cases. Nothing captures what worked, what failed, and why.

## 2. Target users

| Segment | Description |
|---|---|
| Primary | Small and mid-size online sellers (D2C brands, Shopify/WooCommerce stores) with no disputes team |
| Secondary | Freelancers and digital-goods businesses (SaaS, courses, templates) |
| Geography | Cross-border and card-accepting sellers first (Stripe, PayPal); Indian gateway disputes (Razorpay, Cashfree) and UPI disputes as extension |

## 3. Positioning

| | Enterprise tools (Justt, Chargeflow, Chargebacks911) | Stripe Smart Disputes | *Countercase* |
|---|---|---|---|
| Built for | Large merchants | Stripe users only | Small sellers, any processor |
| Reasoning | Black box | Black box | *Every decision explained with sources* |
| Learns the seller's own history | Generic models | Network-level | *Per-seller memory bank* |
| Prevention insights | Some | Limited | *Root-cause playbook* |
| Covers only "eligible" disputes | — | Yes | All disputes, with honest fight/accept advice |

*Wedge:* explainable, memory-driven dispute handling that adapts to each seller.

## 4. Product principles

1. *Memory is the product.* Without memory the agent is generic; with memory it knows this seller.
2. *Show the why.* Every recommendation cites the past cases, rules and beliefs it used.
3. *Never fabricate.* Only facts pulled from real data sources go into evidence.
4. *Honest advice.* Recommend accepting disputes that look valid; don't push sellers to fight genuine complaints.
5. *The seller stays in control.* Nothing is submitted without approval; memories can be edited or deleted.

---

## 5. Features

### 5.1 Core (MVP)

**F1. Unified dispute inbox**
- Connects Stripe, PayPal, Razorpay, Shopify Payments via webhooks/APIs.
- Shows amount, customer, reason and a deadline countdown.
- Alerts (email/WhatsApp) at 72h, 24h and 6h before the deadline.

**F2. Reason-code classifier**
- Maps raw processor codes to plain categories: Not received, Unauthorized/fraud, Not as described, Duplicate, Subscription cancelled, Refund not processed.
- One-line plain-language explanation for the seller.

**F3. Evidence checklist per dispute type**
- Baseline from public card-network rules (e.g. Visa Compelling Evidence 3.0 for fraud claims).
- Marks what's available and what's missing.

**F4. Auto evidence gathering**
- Pulls order details, tracking, delivery proof, IP/device data, prior orders, customer messages and the refund policy shown at checkout.
- Seller can upload extra files.

**F5. Response packet drafting**
- Rebuttal letter + organized evidence PDF.
- *Every claim links to its source document.* Claims without a source are blocked.
- Seller reviews, edits and approves before submission.

**F6. Fight-or-accept advice**
- Win probability based on reason code, evidence strength and this seller's history.
- Compares dispute amount vs fee and effort, and recommends accepting when the claim looks valid or the odds are poor.

### 5.2 Memory features (Hindsight — the differentiator)

**M1. Case memory**
- Every dispute is retained with tags: reason code, product, courier, customer (hashed), amount, evidence submitted, outcome.
- New disputes recall similar past cases: "3 similar cases; you won 2 when you included the delivery photo."

**M2. Outcome-driven beliefs with confidence**
- After each outcome, reflect updates beliefs and shows the change: "Delivery photos win 'not received' disputes — confidence 60% → 85%."
- Minimum case threshold before a belief is formed; low-evidence beliefs are clearly labelled weak.

**M3. Preference learning**
- Learns from seller edits and decisions: "Never fight disputes under ₹500", "Always cite my 7-day return policy", "Keep letters short and formal."
- Explicit preferences become Hindsight *directives* (hard rules applied on every draft).

**M4. Long-term pattern and customer recall**
- "This customer disputed an order 6 weeks ago and later admitted the parcel was with a neighbour."
- "Since September, 70% of your lost disputes involve Courier X."
- Uses event dates so recall across weeks and months is real.

**M5. Seller Playbook (mental model)**
- A living page the agent writes and maintains: best evidence per dispute type, risky couriers/products, repeat disputers, seller preferences.

**M6. Memory Inspector**
- Next to every response: which memories, observations, mental models and directives were used, and why.
- Seller can correct or delete any memory or belief.

**M7. Fast feedback signals**
- Outcomes can take weeks to months. The agent also learns immediately from faster signals: seller edits, fight/accept choices, evidence added, and corrections.

### 5.3 Prevention

- **P1. Root-cause dashboard:** top reasons, money lost vs recovered, win rate by type, worst products/couriers.
- **P2. Actionable tips:** "Require signature on orders above ₹5,000", "Clarify your billing descriptor."
- **P3. Pre-dispute deflection:** detects complaint emails/chats and suggests a reply or refund before it becomes a chargeback.
- **P4. Evidence readiness:** recommends what to start capturing (delivery photos, policy checkbox, IP logging).

### 5.4 Nice to have

- WhatsApp bot for alerts, photo uploads and approvals.
- Multilingual explanations (Hindi and regional languages).
- Small-team access with roles.

---

## 6. Memory architecture (Hindsight)

### Banks
| Bank | Contents | Access |
|---|---|---|
| seller-{id} | That seller's disputes, outcomes, preferences, beliefs, playbook | That seller only |
| shared-patterns | *Aggregate, anonymized* patterns per reason code / category (e.g. win rates by evidence type) | Read-only for all sellers; no customer-level facts ever |

### Operations
| Operation | When | Purpose |
|---|---|---|
| *Retain* | Dispute created, evidence added, seller edits, decision made, outcome received | Build structured, time-aware case memory |
| *Recall* | New dispute arrives; evidence selection | Find similar cases, customer history, patterns (semantic + keyword + graph + temporal) |
| *Reflect* | Drafting explanation, fight/accept advice, belief updates, playbook refresh | Reason over memory and update beliefs |
| *Directives* | Seller states a rule | Enforce preferences on every draft |
| *Mental models* | Periodic / after outcomes | Maintain the Seller Playbook |

### Tags
`reason:<code>`, `courier:<name>`, `product:<sku>`, `customer:<hash>`, `outcome:<won|lost|pending>`, `processor:<name>`

### Separating facts from claims
- *Verified facts:* from processor/shipping/order data.
- *Seller claims:* stored as opinions, labelled as such, never treated as proof.
- Prevents memory poisoning from a wrong seller note.

### Cold start
1. Day 0: card-network rules + shared-patterns bank.
2. As history grows, recall weights shift toward the seller's own bank.
3. Confidence shown on every belief so sparse data is visible.

---

## 7. System architecture

```
Processors (Stripe / PayPal / Razorpay / Shopify)
        │ webhooks
        ▼
 Ingestion service ──► Evidence collectors (orders, shipping, IP, chats)
        │
        ▼
 Agent orchestrator
   ├─ Classifier (small model)
   ├─ Hindsight: retain / recall / reflect
   ├─ Packet builder (source-linked claims only)
   └─ Fight/accept scorer
        │
        ▼
 Seller dashboard
   ├─ Inbox + deadlines
   ├─ Draft review + Memory Inspector
   ├─ Seller Playbook
   └─ Insights dashboard
        │ approve
        ▼
 Submit via API (where supported) or export PDF for manual upload
```

*Suggested stack:* Next.js (dashboard), FastAPI (backend), Postgres, Hindsight (self-hosted via Docker), Stripe test mode, an LLM for drafting/reflect and a smaller model for classification.

---

## 8. Guardrails, privacy and compliance

| Area | Approach |
|---|---|
| Evidence integrity | Only source-linked facts; no generated or altered evidence; seller approval required |
| Honest advice | Agent recommends accepting disputes that appear valid |
| Customer PII | Store hashed customer IDs; raw personal data stays in the source system; retention limits |
| Cross-seller data | Only aggregate patterns shared; no customer-level facts leave a seller's bank |
| Payment data | No card numbers stored; rely on processor tokens (PCI scope minimized) |
| Regulation | Designed with India's DPDP Act in mind: consent, purpose limitation, deletion on request |
| Seller control | Edit/delete any memory or belief; export and wipe their bank |

---

## 9. Risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| 1 | Small sellers have too few disputes to learn from | Shared anonymized bank for cold start; confidence on every belief |
| 2 | Outcomes take weeks/months, slowing learning | Learn from fast signals (edits, decisions, added evidence); demo uses seeded history, stated openly |
| 3 | Overfitting / wrong beliefs from few cases | Minimum case threshold; confidence levels; seller can correct beliefs |
| 4 | Memory poisoning from bad seller notes | Separate verified facts from seller claims; editable memory |
| 5 | Before/after demo looks rigged | Same model, prompt and dispute; only recall toggled; Memory Inspector shows exact memories used |
| 6 | Storing customer personal data | Hashed IDs, per-seller banks, retention limits |
| 7 | Cross-seller leakage | Aggregate-only shared bank |
| 8 | Stripe Smart Disputes already exists | Multi-processor, explainable, per-seller memory, prevention |
| 9 | Card chargebacks less relevant to UPI-heavy Indian sellers | Target card-accepting/cross-border sellers first; gateway and UPI disputes as roadmap |
| 10 | Helping sellers fight genuine complaints | Honest accept recommendations; no fabricated evidence |
| 11 | LLM hallucinates evidence | Source-linked claims only; unsourced claims blocked; seller approval |
| 12 | Processor APIs don't all allow submission | API submit where supported; PDF export otherwise |
| 13 | Cost/latency per dispute | Small model for classification; budgeted recall; show cost per dispute |
| 14 | No real proof it works | Offline evaluation on synthetic/public data comparing memory on vs off, presented as simulation |

---

## 10. Success metrics

| Metric | Why it matters |
|---|---|
| Disputes responded to before deadline (%) | Fixes the main operational leak |
| Win rate on fought disputes | Quality of evidence |
| Net recovery rate | The headline business outcome |
| Seller time per dispute | Ease of use |
| Draft edits needed over time (should fall) | *Shows memory is learning preferences* |
| Recommendation accuracy with memory vs without | *Direct proof of memory value* |
| Repeat dispute rate by root cause | Prevention working |

---

## 11. Hackathon demo plan

*Before/after toggle:* same dispute, Memory OFF vs Memory ON.

| | Memory OFF | Memory ON |
|---|---|---|
| Evidence advice | Generic checklist | "Include the delivery photo; it won your last 2 similar cases" |
| Customer | Unknown | "Disputed 6 weeks ago, later admitted receipt" |
| Fight/accept | Generic estimate | Uses this seller's win rate for this reason + courier |
| Letter | Default template | Seller's tone, return policy included |
| Explanation | None | Cites specific memories and beliefs |

**4-act script**
1. *Day 1, empty memory:* generic help; seller loses a case and corrects the draft ("mention my return policy").
2. *Weeks later (seeded history):* the bank fills with disputes, outcomes and preferences.
3. *New dispute:* toggle Memory OFF vs ON; the difference is obvious; Memory Inspector shows why.
4. *Playbook + belief changes:* "Here's what the agent learned about this business."

**Demo build slice**
1. Stripe test-mode webhook → inbox with deadline timer (F1, F2)
2. Checklist + auto-gathering from mock order/shipping data (F3, F4)
3. Source-linked packet with explanations (F5)
4. Hindsight case memory, beliefs, preferences, inspector (M1–M6)
5. Seeded history dataset with real event dates
6. Insights dashboard (P1)

---

## 12. Roadmap

| Phase | Scope |
|---|---|
| Hackathon | Stripe test mode, memory features, before/after demo, playbook |
| v1 | Stripe + PayPal live, WhatsApp alerts, PDF export, privacy controls |
| v2 | Razorpay/Cashfree gateway disputes, Shopify app, pre-dispute deflection |
| v3 | UPI dispute support, multilingual, small-team access, offline evaluation benchmark |

## 13. Business model (draft)

- Free tier: inbox, deadlines, checklist.
- Pro: memory features, drafting, playbook — flat monthly fee for small sellers.
- Optional success fee on recovered amounts, capped low for small disputes.

## 14. Open questions

- Which processors to support first beyond Stripe?
- How large must the shared bank be before cross-seller patterns are reliable?
- Exact retention period for dispute memory under DPDP?
- Pricing: flat fee vs success fee for very small sellers?

---

### Sources
- Redo — Chargeback statistics 2026: https://redo.com/resources/articles/chargebacks/chargeback-statistics
- Justt 2026 Chargeback Benchmark Report: https://www.prnewswire.com/il/news-releases/shoppers-are-turning-chargebacks-into-a-customer-service-hotline-justt-chargeback-benchmark-report-finds-302919550.html
- Chargeflow — LexisNexis $5.13 figure: https://www.chargeflow.io/category/chargebacks-tricks-statistics
- Stripe Smart Disputes docs: https://docs.stripe.com/disputes/smart-disputes
- Hindsight (Vectorize): https://vectorize.io/blog/introducing-hindsight-agent-memory-that-works-like-human-memory
- Hindsight FAQ: https://hindsight.vectorize.io/faq
