# Countercase

AI-assisted dispute management for small online sellers. Countercase helps
sellers investigate PayPal disputes, assemble evidence, and draft responses.
Every response is explained, source-linked, and approved by the seller
before anything is sent.

> **Status: working prototype, synthetic data only.** The PayPal submit step
> is unit-tested against a stub and has not yet been run against a real
> sandbox dispute. See [Known limitations](#known-limitations).


## How it works
1. A dispute arrives through the PayPal webhook path. [confirm]
2. The backend pulls the related transaction and builds an evidence
   summary. [confirm]
3. An LLM drafts the response, with each claim linked to its source. [confirm]
4. The seller reviews and approves before anything is sent.
5. Resolved disputes feed an Insights view. [confirm]

Optional per-seller memory ([Hindsight](https://hindsight.vectorize.io),
off by default) lets the drafts adapt to past outcomes.

Architecture and PayPal integration: [docs/PAYPAL.md](docs/PAYPAL.md).

## Stack
- **Python / FastAPI**: backend, webhook handling, LLM claim drafting
- **Postgres**: storage, with migrations on start
- **Next.js**: seller dashboard
- **PayPal sandbox** (Disputes, Transaction Search, webhooks) and
  **Stripe test mode**
- **Anthropic API** for drafting

## Run it locally
```bash
cp .env.example .env     # set DEMO_TOOLS=1 for the local demo
make up                  # db + api + web -> http://localhost:3000
make seed-fixtures seed-core   # 3 fixture disputes + 62 resolved synthetic ones
make demo-reset          # 3 live demo disputes through the webhook path
make test                # api tests (need Postgres) + web lint
```
Optional memory: `make up-memory && make seed` (needs a Groq key; about
25 minutes on the free tier). No quota? Set `MEMORY_SEED=full` for the
in-memory version. Demo walkthrough: [docs/DEMO.md](docs/DEMO.md).

## Evaluation
`make eval` runs a simulation comparing memory OFF vs ON and writes the
results to `eval/results.md`.

## Known limitations
- No authentication or access controls yet.
- The PayPal submit step is untested against a real sandbox dispute.
- The Render blueprint is untested and omits live credentials.
- **Do not connect real seller accounts, PayPal credentials, webhooks, or
  dispute data to a publicly accessible instance.** Use synthetic data only.
