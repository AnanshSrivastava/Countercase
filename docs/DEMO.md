# Demo script and runbook

One sentence: **Countercase is the chargeback agent that remembers every dispute you have ever had, and shows its work.**
All history is synthetic and says so on screen. Numbers below were measured on the current seed; re-measure after changing data.

## Set up (once, then `make demo-reset` between runs)

1. `make up` (db, api, web) and `make up-memory` (Hindsight). If Docker runs inside WSL, keep a WSL session open or the containers stop.
2. `.env`: `DEMO_TOOLS=1`, `ALERTS_INTERVAL_SECONDS=60` (optional; otherwise use the button on /alerts). For real memory also `MEMORY_BACKEND=hindsight` and a Groq key (`HINDSIGHT_API_LLM_*`, see D-7).
3. `make seed-core` (62 resolved synthetic disputes for Insights). With Hindsight: `make seed` once, the day before (about 25 min; the Groq free tier allows only one full load per day, see D-7). **No Hindsight / no Groq quota:** set `MEMORY_BACKEND=inmemory` and `MEMORY_SEED=full`; the API loads the same 62-case history into memory at startup (same story, nothing external).
4. `make demo-reset` creates the three live demo disputes through the real webhook path, so evidence is collected exactly as for a real dispute:

| Dispute | Story | Memory OFF | Memory ON |
|---|---|---|---|
| `ord_102`, 129.00 USD, due in 2 days | the main story: not received, CourierX, strong delivery evidence, repeat customer | fight 45%, 0 cases | **fight 62%** (range 34-90%), 3 similar cases, customer history, rules, beliefs |
| `ord_101`, 49.99 USD | smaller not-received dispute | fight 45% | fight 50% |
| `ord_103`, 84.00 USD | parcel returned to sender, no delivery proof | accept | **accept**, no rebuttal drafted, 26% win chance from 14 similar cases |

5. Open `http://localhost:3000`. **Fallback if anything is slow or down:** `NEXT_PUBLIC_USE_FIXTURES=1` serves frozen real drafts for the fixture disputes `dp_001..003` from `fixtures/drafts/` (made by `python eval/cache_demo.py`). Same screens.

## The four acts (about 6 minutes)

**Act 1: Day 1, no memory (30 s).** Open the 129.00 USD dispute, Draft tab, **Memory OFF**: fight, 45%, generic checklist and letter, no explanation. "Every tool today works like this."

**Act 2: Months later (30 s).** "Countercase has now seen 49 of this seller's disputes." Show **Insights** (money lost vs recovered, CourierX behind most recent losses, delivery proof wins "not received"). Then **Alerts**: press *Check deadlines now*. The 129.00 USD dispute is 2 days from its deadline, so a 72-hour warning appears, labelled **Simulated email** (no mail server is configured, and it says so).

**Act 3: Same dispute, Memory ON (2 min).** Same model, same prompt, same dispute; only recall changes.
- Advice: fight, **62%** from 3 similar cases (OFF: 45%, 0 cases).
- **Memory tab** (Inspector):
  - rules used: "Always cite the 7-day return policy", "Keep letters short and formal";
  - customer history: this customer disputed an order six weeks ago and later confirmed the parcel was received;
  - beliefs: "Delivery proof wins 'not received' disputes (about 62% vs 23% without)", confidence 99%, *strong*; "CourierX is behind most of your recent losses", confidence about 60%, *moderate* (honest about its size);
  - considered but not used; **Delete / Reject** on anything.
- Draft tab: every claim shows the source record's own text. Add an unsourced claim: Approve is blocked.
- Approve: the dialog says plainly whether anything is sent (Stripe test mode) or a PDF is exported.

**Act 3b: The honest accept (45 s).** Open the 84.00 USD dispute (parcel returned, no delivery proof). Advice: **accept**, no rebuttal drafted, because the customer's claim looks valid. "Other tools fight everything. Countercase tells you when not to."

**Act 4: The agent learns (1 min).** On the 129.00 USD dispute, after approving, use the **Demo tool** panel to simulate a win. The page shows "What the agent just learned" (belief confidence moves). Open **Playbook**: best evidence per type, risky couriers, repeat disputers, the seller's rules. Edit a draft shorter and approve: "Keep letters short" is *proposed*, saved only when the seller clicks.

## The proof slide (30 s)

`make eval` (simulation on synthetic data, 40 simulated sellers, held-out disputes): see `eval/results.md`.

| | Memory OFF | Memory ON |
|---|---|---|
| Win-probability error (Brier, lower is better) | 0.254 | 0.233 |
| Right "accept" advice | 58% | 67% |
| Profit per fought dispute | $31.32 | $31.66 (oracle $32.88) |

Say plainly: this is a simulation, the money gain is small because fighting is usually still worth it, and the win is **calibrated, explainable advice**. Do not pitch the delivery-proof effect as huge: in the seed it is about 62% vs 23%.

## Honest limits (say them before they ask)

- Everything is synthetic. Nothing has run against real Stripe: the submit step has only run against a fake client (needs the Stripe CLI and a test key, see `docs/STATUS.md`).
- The app has no login or access controls. The Render blueprint is untested and has no live PayPal credentials configured; never put real seller, PayPal, or processor credentials/data on a publicly accessible instance until authentication and access controls are implemented.
- `DEMO_TOOLS=1` is for local demos only. Keep it disabled in any deployed environment.
- Deadline alerts are simulated unless SMTP is configured.
- Hindsight on the Groq free tier loads about one full history per day; use a paid tier or load the day before.
- Single demo seller.

## Likely questions

- *Isn't this rigged?* Same model, prompt and dispute; only the recall step differs. The Inspector lists exactly what was injected. The eval holds out cases memory never saw, and no outcome in memory is dated after the demo disputes open.
- *What if a seller's note is wrong?* Notes and uploads are stored unverified and can never back a claim (a database rule enforces it). Beliefs are counted from outcomes, not written by a model.
- *Does it submit by itself?* Never. The seller approves a hash of exactly what is sent; Stripe test keys only.
- *Stripe Smart Disputes?* Black box, Stripe-only. Countercase: every decision cited, per-seller memory, honest accept advice.
- *Privacy?* Customers appear only as per-seller hashes; no card data; the seller can reject or delete any memory.

## Recording tips (rehearsed 14/14 + the approve and learn flow in a real browser)

- Use the production web build, not `next dev` (no dev badge, faster): `cd apps/web && pnpm build && pnpm start`.
- API for a Hindsight-free take: `MEMORY_BACKEND=inmemory MEMORY_SEED=full DEMO_TOOLS=1 uvicorn app.main:app --port 8000` from `apps/api` (memory resets on every restart).
- **Between takes:** `make demo-reset` (new live disputes) **and restart the API** (clears what the agent learned). Closed disputes are hidden in the inbox by default; "Show N closed disputes" reveals them.
- Do the approve + simulate-outcome act on the 49.99 USD dispute first if you want to keep the 129 USD one clean for a second take.
- Browser at 1280 px wide; the nav, Alerts and Insights pages all fit on a phone width too if you want a mobile shot.
