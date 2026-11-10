# Browser end-to-end checks (manual)

Real headless Chromium against the **running** stack (`make up`, web on :3001 and api on :8000 as in
`.env`). They create their own disputes through signed webhooks, so they need `STRIPE_WEBHOOK_SECRET`
to be `whsec_local_e2e` (set it in `.env`) and `NEXT_PUBLIC_USE_FIXTURES=0`.

    npm i playwright && npx playwright install chromium     # once, in any scratch folder
    node scripts/e2e/phase4-flow.cjs        # fight, accept, upload, PDF, mobile width   (27 checks)
    node scripts/e2e/phase4-learning.cjs    # result survives refresh, learned-rule loop (15 checks)
    DEMO_TOOLS=1 node scripts/e2e/simulate-outcome.cjs   # needs DEMO_TOOLS=1 on the api (13 checks)

Notes
- Run them from a folder where `playwright` is installed (or set NODE_PATH to its node_modules).
- They leave test disputes in your local DB. Reset with `make demo-reset` once that exists.
- After editing web code, `docker compose restart web`: the Docker dev server can serve stale code.
- `simulate-outcome` shows a belief change only if the agent has seeded memory (`make seed`).
- Not CI: they need the live stack. They are the fastest way to see that the demo path still works.
