// Result screens must survive the post-approval refresh, and the learning loop must work.
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

async function webhook(order, amount, reason) {
  const now = Math.floor(Date.now() / 1000);
  const duId = `du_pw2_${order}_${now}_${Math.floor(Math.random() * 1e6)}`;
  const event = {
    id: `evt_${duId}`, type: "charge.dispute.created", created: now,
    data: { object: {
      id: duId, object: "dispute", amount, currency: "usd", charge: "ch_pw", reason,
      status: "needs_response", created: now, evidence: { customer_email_address: null },
      evidence_details: { due_by: now + 6 * 86400 }, metadata: { order_id: order },
    } },
  };
  const body = JSON.stringify(event);
  const sig = crypto.createHmac("sha256", SECRET).update(`${now}.${body}`).digest("hex");
  const res = await fetch(`${API}/core/webhooks/stripe`, {
    method: "POST", body, headers: { "Stripe-Signature": `t=${now},v1=${sig}`, "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`webhook ${res.status}`);
  const list = await (await fetch(`${API}/core/disputes`)).json();
  return list.find((d) => d.processor_dispute_id === duId).id;
}

(async () => {
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1100, height: 900 } })).newPage();
  const directivePosts = [];
  page.on("response", (r) => {
    if (r.url().endsWith("/agent/directives") && r.request().method() === "POST") directivePosts.push(r.status());
  });
  const editCalls = [];
  page.on("response", (r) => {
    if (r.url().includes("/agent/disputes/") && r.url().endsWith("/edit")) editCalls.push(r.status());
  });

  // ------------------------------------------------------------ approve: shorten the letter a lot
  const id = await webhook("ord_101", 4999, "product_not_received");
  await page.goto(`${WEB}/disputes/${id}?tab=draft`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Your response" }).waitFor({ timeout: 30000 });
  const before = await page.locator("ol > li").count();
  for (let i = 0; i < 4; i++) await page.getByRole("button", { name: "Remove" }).first().click();
  const after = await page.locator("ol > li").count();
  check("removed 4 statements", before - after === 4, `${before} -> ${after}`);
  await page.waitForTimeout(900);

  await page.getByRole("button", { name: "Review and approve" }).click();
  await page.getByRole("dialog").getByRole("button", { name: /Approve and create PDF/ }).click();
  await page.getByRole("heading", { name: /PDF created, not sent/ }).waitFor({ timeout: 30000 });
  check("result card appears", true);

  await page.waitForTimeout(3500); // long enough for any accidental refresh to have swapped the page
  check("result card is STILL there 3.5s later (no refresh wiped it)", (await page.getByRole("heading", { name: /PDF created, not sent/ }).count()) === 1);
  check("agent /edit was called after approval", editCalls.length >= 1 && editCalls.every((s) => s === 200), editCalls.join(","));

  const panel = page.getByRole("heading", { name: "Should Countercase remember this?" });
  check("learned-rule suggestions are shown after a big edit", (await panel.count()) === 1);
  const proposal = await page.locator("section", { has: panel }).locator("li").first().textContent();
  console.log("   proposal:", (proposal || "").replace(/\s+/g, " ").slice(0, 120));
  check("proposal is 'Keep letters short and formal'", /short and formal/i.test(proposal || ""));

  const rulesBefore = await (await fetch(`${API}/agent/playbook`)).json();
  await page.getByRole("button", { name: "Save as a rule" }).first().click();
  await page.getByText(/^Saved: /).waitFor({ timeout: 10000 });
  check("'Save as a rule' reaches the agent (POST /agent/directives = 200)", directivePosts.length === 1 && directivePosts[0] === 200, directivePosts.join(","));
  const rulesAfter = JSON.stringify(await (await fetch(`${API}/agent/playbook`)).json());
  check("the rule now appears in the agent's playbook", /short and formal/i.test(rulesAfter) && !/short and formal/i.test(JSON.stringify(rulesBefore)));

  await page.getByRole("button", { name: "Done" }).click();
  await page.getByText("Your response was approved and exported as a PDF").waitFor({ timeout: 30000 });
  check("'Done' refreshes the page to the saved submission record", true);

  // ------------------------------------------------------------ accept: note must persist until Done
  const id3 = await webhook("ord_103", 8400, "product_not_received");
  await page.goto(`${WEB}/disputes/${id3}?tab=draft`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Accept this dispute" }).waitFor({ timeout: 30000 });
  await page.getByRole("button", { name: "Accept this dispute" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Yes, accept it" }).click();
  await page.getByRole("heading", { name: "Dispute accepted" }).waitFor({ timeout: 30000 });
  await page.waitForTimeout(3500);
  check("accept result and note are STILL there 3.5s later", (await page.getByText(/NOT closed with the processor/).count()) === 1);
  await page.getByRole("button", { name: "Done" }).click();
  await page.getByText(/You accepted this dispute in Countercase/).waitFor({ timeout: 30000 });
  const text = await page.locator("main").textContent();
  check("after reload the page does not claim 'nothing further is needed'", !/Nothing further is needed/.test(text));
  check("after reload it tells the seller to close it at the processor", /close it\s+in your processor dashboard/.test(text.replace(/\s+/g, " ")) || /processor dashboard/.test(text));

  // ------------------------------------------------------------ approve is gated on a fresh preview
  const id5 = await webhook("ord_101", 4999, "product_not_received");
  await page.goto(`${WEB}/disputes/${id5}?tab=draft`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Your response" }).waitFor({ timeout: 30000 });
  await page.waitForFunction(() => document.querySelector("pre")?.textContent?.includes("To the dispute review team"));
  const approve = page.getByRole("button", { name: "Review and approve" });
  check("approve enabled once the preview is current", await approve.isEnabled());
  await page.locator("textarea").first().fill("Changed wording right now");
  check("approve is disabled immediately after an edit (stale preview)", await approve.isDisabled());
  await page.waitForFunction(() => document.querySelector("pre")?.textContent?.includes("Changed wording right now"), null, { timeout: 15000 });
  await page.waitForTimeout(200);
  check("approve is enabled again once the new preview arrives", await approve.isEnabled());

  await browser.close();
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  process.exit(failed.length ? 1 : 0);
})().catch((e) => {
  console.error("SCRIPT ERROR:", e.message.split("\n").slice(0, 6).join("\n"));
  process.exit(2);
});
