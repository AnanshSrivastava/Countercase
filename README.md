# Countercase

Countercase helps small online sellers manage **PayPal disputes**. Every response is explained,
source-linked, and approved by the seller before anything is sent.

Architecture and the PayPal integration: [docs/PAYPAL.md](docs/PAYPAL.md).

## Deployment status

The Render blueprint is untested and is not configured with live processor credentials. Countercase does not yet have
authentication or access controls; **do not connect real seller accounts, PayPal credentials,
webhooks, or dispute data to a publicly accessible instance** until those protections are in place.
The hosted blueprint disables demo tools and omits PayPal credentials. Use synthetic data only.

## Run it

```
cp .env.example .env            # local demo only: set DEMO_TOOLS=1 locally; add a Groq key for Hindsight (see D-7)
make up                         # db + api (migrations run on start) + web   -> http://localhost:3000
make seed-fixtures seed-core    # 3 fixture disputes + 62 resolved synthetic disputes (Insights)
make demo-reset                 # 3 live demo disputes through the real webhook path (needs DEMO_TOOLS=1)
make up-memory && make seed     # optional: real Hindsight memory (about 25 min on the Groq free tier)
make eval                       # memory OFF vs ON simulation  -> eval/results.md
make test                       # api (needs Postgres) + web lint
```

No Hindsight or Groq quota? Set `MEMORY_SEED=full` (in-memory, same story). Demo script: [docs/DEMO.md](docs/DEMO.md).
All data is synthetic. Stripe and PayPal are sandbox/test only. The PayPal submit step is unit-tested against a stub and still needs a first run against a real sandbox dispute (see docs/PAYPAL.md).

## Stack

Next.js (dashboard) · FastAPI (backend) · Postgres · PayPal sandbox (Disputes, Transaction Search, webhooks) · Stripe test mode · LLM claim drafting (Anthropic API) · optional Hindsight memory (off by default).
