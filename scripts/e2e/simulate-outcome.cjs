// Simulated bank outcome: panel only after a response, agent learns, result persists.
const { chromium } = require("playwright");
const crypto = require("crypto");

const API = "http://localhost:8000";
const WEB = "http://localhost:3001";
const SECRET = "whsec_local_e2e";
const results = [];
const check = (name, ok, extra = "") => {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  — " + extra : ""}`);
};
const j = async (method, path, body) => {
  const res = await fetch(API + path, { method, body: body && JSON.stringify(body), headers: { "Content-Type": "application/json" } });
  return { status: res.status, body: await res.json().catch(() => null) };
};

async function webhook(order, amount) {
  const now = Math.floor(Date.now() / 1000);
  const duId = `du_out_${order}_${now}_${Math.floor(Math.random() * 1e6)}`;
  const raw = JSON.stringify({ id: `evt_${duId}`, type: "charge.dispute.created", created: now, data: { object: {
    id: duId, object: "dispute", amount, currency: "usd", charge: "ch", reason: "product_not_received",
    status: "needs_response", created: now, evidence: { customer_email_address: null },
    evidence_details: { due_by: now + 6 * 86400 }, metadata: { order_id: order } } } });
  const sig = crypto.createHmac("sha256", SECRET).update(`${now}.${raw}`).digest("hex");
  await fetch(`${API}/core/webhooks/stripe`, { method: "POST", body: raw, headers: { "Stripe-Signature": `t=${now},v1=${sig}`, "Content-Type": "application/json" } });
  return (await j("GET", "/core/disputes")).body.find((d) => d.processor_dispute_id === duId).id;
}

async function approveViaApi(id) {
  const draft = (await j("POST", `/agent/disputes/${id}/draft?memory=on`)).body;
  const req = { claims: draft.claims, seller_statement: null, attach_upload_ids: [], agent_claims: draft.claims };
  const prev = (await j("POST", `/core/disputes/${id}/letter-preview`, req)).body;
  return j("POST", `/core/disputes/${id}/approve`, { ...req, approved: true, letter_sha256: prev.letter_sha256 });
}

(async () => {
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1100, height: 900 } })).newPage();
  const problems = [];
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message));

  // ---- the panel must NOT appear before any response exists
  const fresh = await webhook("ord_101", 4999);
  await page.goto(`${WEB}/disputes/${fresh}?tab=draft`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Your response" }).waitFor({ timeout: 30000 });
  check("no 'Demo tool' panel before a response was approved", (await page.getByRole("heading", { name: /Demo tool/ }).count()) === 0);

  // ---- approve (exported: no Stripe key), then the panel appears
  const sub = await approveViaApi(fresh);
  check("setup: response approved", sub.status === 200 && sub.body.status === "exported", sub.body?.status);
  await page.goto(`${WEB}/disputes/${fresh}?tab=draft`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: /Demo tool/ }).waitFor({ timeout: 30000 });
  check("demo panel appears after a response, labelled as simulated", (await page.getByText("simulated, nothing is sent to anyone").count()) === 1);

  const changesBefore = (await j("GET", "/agent/beliefs/changes")).body.length;

  // ---- simulate a win
  await page.getByRole("button", { name: "Simulate: won" }).click();
  await page.getByRole("heading", { name: "Simulated outcome recorded: won" }).waitFor({ timeout: 30000 });
  check("result card shows the simulated outcome", true);
  await page.waitForTimeout(3000);
  check("result card is still there 3s later (no refresh wiped it)", (await page.getByRole("heading", { name: "Simulated outcome recorded: won" }).count()) === 1);
  check("agent learned from it", (await page.getByText("The agent has learned from this result.").count()) === 1);

  const dispute = (await j("GET", `/core/disputes/${fresh}`)).body.dispute;
  check("core status is now 'won'", dispute.status === "won", dispute.status);
  const changesAfter = (await j("GET", "/agent/beliefs/changes")).body;
  console.log(`   belief changes: ${changesBefore} -> ${changesAfter.length}; for this dispute: ${changesAfter.filter((c) => c.dispute_id === fresh).length}`);

  // ---- Done: the page now shows what was learned
  await page.getByRole("button", { name: "Done, show what was learned" }).click();
  await page.waitForFunction(
    () => /What the agent just learned|has not changed any belief yet/.test(document.body.innerText),
    null, { timeout: 30000 },
  );
  const text = await page.locator("main").innerText();
  const learned = /What the agent just learned/.test(text);
  check("after Done, the page explains what the agent learned (or honestly says nothing changed)", learned || /has not changed any belief yet/.test(text), learned ? "belief cards shown" : "no belief changed");
  check("status badge now says Won", (await page.getByText("Won", { exact: true }).count()) >= 1);
  check("the simulate panel is gone once a result exists", (await page.getByRole("heading", { name: /Demo tool/ }).count()) === 0);
  await page.screenshot({ path: (process.env.SHOTS_DIR || ".") + "/shot-outcome.png", fullPage: true });

  // ---- cannot simulate twice (API)
  const again = await j("POST", `/core/disputes/${fresh}/simulate-outcome`, { outcome: "lost" });
  check("a second simulation is refused", again.status === 409, `${again.status} ${again.body?.error}`);

  // ---- reload keeps the learnings
  await page.reload({ waitUntil: "networkidle" });
  const after = await page.locator("main").innerText();
  check("reload still shows the outcome section", /What the agent just learned|has not changed any belief yet/.test(after));

  // ---- a lost result on a second dispute
  const second = await webhook("ord_101", 4999);
  await approveViaApi(second);
  await page.goto(`${WEB}/disputes/${second}?tab=draft`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Simulate: lost" }).click();
  await page.getByRole("heading", { name: "Simulated outcome recorded: lost" }).waitFor({ timeout: 30000 });
  check("simulating a loss works too", (await j("GET", `/core/disputes/${second}`)).body.dispute.status === "lost");

  console.log("\npage errors:", problems.length ? problems.join(" | ") : "none");
  await browser.close();
  const failed = results.filter((r) => !r.ok);
  console.log(`${results.length - failed.length}/${results.length} checks passed`);
  process.exit(failed.length ? 1 : 0);
})().catch((e) => {
  console.error("SCRIPT ERROR:", e.message.split("\n").slice(0, 6).join("\n"));
  process.exit(2);
});
