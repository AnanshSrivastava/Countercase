// Real-browser end-to-end check of the Phase 4 UI against the live stack.
const { chromium } = require("playwright");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const API = "http://localhost:8000";
const WEB = "http://localhost:3001";
const SECRET = "whsec_local_e2e";
const SHOTS = process.env.SHOTS_DIR || __dirname;
const results = [];
const check = (name, ok, extra = "") => {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  — " + extra : ""}`);
};

async function webhook(order, amount, reason) {
  const now = Math.floor(Date.now() / 1000);
  const duId = `du_pw_${order}_${now}`;
  const event = {
    id: `evt_pw_${order}_${now}`,
    type: "charge.dispute.created",
    created: now,
    data: {
      object: {
        id: duId, object: "dispute", amount, currency: "usd", charge: "ch_pw", reason,
        status: "needs_response", created: now, evidence: { customer_email_address: null },
        evidence_details: { due_by: now + 6 * 86400 }, metadata: { order_id: order },
      },
    },
  };
  const body = JSON.stringify(event);
  const sig = crypto.createHmac("sha256", SECRET).update(`${now}.${body}`).digest("hex");
  const res = await fetch(`${API}/core/webhooks/stripe`, {
    method: "POST", body,
    headers: { "Stripe-Signature": `t=${now},v1=${sig}`, "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`webhook ${res.status}`);
  const list = await (await fetch(`${API}/core/disputes`)).json();
  return list.find((d) => d.processor_dispute_id === duId).id;
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1100, height: 900 } });
  const page = await ctx.newPage();
  const problems = [];
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
  page.on("console", (m) => {
    if (m.type() === "error") problems.push("console: " + m.text());
  });
  page.on("requestfailed", (r) => problems.push("requestfailed: " + r.url() + " " + r.failure()?.errorText));

  // ---------------------------------------------------------------- FIGHT path
  const id = await webhook("ord_101", 4999, "product_not_received");
  console.log("fight dispute:", id);

  await page.goto(`${WEB}/disputes/${id}?tab=draft`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Your response" }).waitFor({ timeout: 30000 });
  check("editor renders for a fight dispute", true);

  const preview = page.locator("pre").first();
  await preview.waitFor({ timeout: 15000 });
  await page.waitForFunction(() => document.querySelector("pre")?.textContent?.includes("To the dispute review team"));
  check("server-rendered letter preview appears", true, (await preview.textContent()).slice(0, 60).replace(/\s+/g, " "));
  check("every statement shows its source record", (await page.getByText("The record says:").count()) >= 3);

  // edit the first statement; the preview must follow the edit
  const first = page.locator("textarea").first();
  await first.fill("The order was shipped by CourierX and arrived (edited by the seller).");
  await page.waitForFunction(() => document.querySelector("pre")?.textContent?.includes("edited by the seller"), null, { timeout: 15000 });
  check("editing a statement updates the server preview", true);

  // add the seller's own statement: must be labelled as not evidence
  await page.getByLabel("Your own statement (optional)").fill("This customer has ordered from us before.");
  await page.waitForFunction(() => document.querySelector("pre")?.textContent?.includes("not independently verified evidence"), null, { timeout: 15000 });
  check("seller statement is labelled as not verified evidence", true);

  // a statement with no wording yet must not block or break the preview
  await page.getByRole("button", { name: "Add a statement" }).click();
  await page.waitForTimeout(800);
  check("an empty new statement does not break the preview", (await page.locator("[role=alert]:not(#__next-route-announcer__)").count()) === 0);
  await page.getByRole("button", { name: "Remove" }).last().click();

  await page.screenshot({ path: path.join(SHOTS, "shot-editor-desktop.png"), fullPage: true });

  // save draft
  await page.getByRole("button", { name: "Save draft" }).click();
  await page.getByText("Draft saved.").waitFor({ timeout: 10000 });
  check("Save draft works and confirms", true);

  // approve flow
  const approveBtn = page.getByRole("button", { name: "Review and approve" });
  check("approve button enabled with a clean preview", await approveBtn.isEnabled());
  await approveBtn.click();
  const dialog = page.getByRole("dialog");
  await dialog.waitFor();
  const dialogText = await dialog.textContent();
  check("confirmation dialog says honestly nothing is sent (no key)", /Nothing will be sent automatically/.test(dialogText), dialogText.slice(0, 110).replace(/\s+/g, " "));
  await page.screenshot({ path: path.join(SHOTS, "shot-dialog.png") });

  // cancelling must not approve anything
  await dialog.getByRole("button", { name: "Go back" }).click();
  const before = await (await fetch(`${API}/core/disputes/${id}/submission`)).status;
  check("'Go back' approves nothing", before === 404, `submission endpoint -> ${before}`);

  await approveBtn.click();
  await dialog.getByRole("button", { name: /Approve and create PDF/ }).click();
  await page.getByRole("heading", { name: /PDF created, not sent/ }).waitFor({ timeout: 30000 });
  check("approve → exported result card", true);
  const pdfLink = page.getByRole("link", { name: "Download the PDF packet" }).first();
  const href = await pdfLink.getAttribute("href");
  const pdfRes = await fetch(href);
  const pdfBytes = Buffer.from(await pdfRes.arrayBuffer());
  check("PDF link downloads a real PDF", pdfRes.status === 200 && pdfBytes.slice(0, 5).toString() === "%PDF-", `${pdfBytes.length} bytes`);

  const sub = await (await fetch(`${API}/core/disputes/${id}/submission`)).json();
  const disp = (await (await fetch(`${API}/core/disputes/${id}`)).json()).dispute;
  check("dispute is 'approved' (not 'submitted') after an export", disp.status === "approved" && sub.status === "exported", `${disp.status}/${sub.status}`);
  check("approved letter contains the seller's edit", sub.letter_md.includes("edited by the seller"));

  // learning suggestions are optional; just record what appeared
  const learned = await page.getByRole("heading", { name: "Should Countercase remember this?" }).count();
  console.log("   (learned-rule suggestions shown:", learned > 0 ? "yes" : "no", ")");

  // reload: the saved submission record is shown
  await page.reload({ waitUntil: "networkidle" });
  await page.getByText("Your response was approved and exported as a PDF").waitFor({ timeout: 30000 });
  check("reload shows the approved submission record", true);

  // ---------------------------------------------------------------- ACCEPT path
  const id3 = await webhook("ord_103", 8400, "product_not_received");
  console.log("accept dispute:", id3);
  await page.goto(`${WEB}/disputes/${id3}?tab=draft`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Accept this dispute" }).waitFor({ timeout: 30000 });
  check("honest-accept dispute shows the Accept panel, not a letter editor", (await page.getByRole("heading", { name: "Your response" }).count()) === 0);
  check("'fight anyway' path is offered", (await page.getByRole("link", { name: /fight it anyway/ }).count()) === 1);
  await page.screenshot({ path: path.join(SHOTS, "shot-accept.png"), fullPage: true });

  await page.getByRole("button", { name: "Accept this dispute" }).click();
  const d2 = page.getByRole("dialog");
  await d2.waitFor();
  check("accept dialog is explicit about not closing at the processor", /recorded here only/.test(await d2.textContent()));
  await d2.getByRole("button", { name: "Go back" }).click();
  const still = (await (await fetch(`${API}/core/disputes/${id3}`)).json()).dispute.status;
  check("'Go back' accepts nothing", still === "needs_response", still);

  await page.getByRole("button", { name: "Accept this dispute" }).click();
  await d2.getByRole("button", { name: "Yes, accept it" }).click();
  await page.getByRole("heading", { name: "Dispute accepted" }).waitFor({ timeout: 30000 });
  const after = (await (await fetch(`${API}/core/disputes/${id3}`)).json()).dispute.status;
  check("accept → dispute becomes 'accepted'", after === "accepted", after);

  // fight anyway: editor available with no pre-drafted claims
  const id4 = await webhook("ord_103", 8400, "product_not_received");
  await page.goto(`${WEB}/disputes/${id4}?tab=draft&fight=1`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Your response" }).waitFor({ timeout: 30000 });
  check("'fight anyway' opens the editor with no claims", (await page.locator("ol > li").count()) === 0);
  check("approve is disabled until a sourced statement exists", await page.getByRole("button", { name: "Review and approve" }).isDisabled());

  // ---------------------------------------------------------------- EVIDENCE upload (browser)
  await page.goto(`${WEB}/disputes/${id}?tab=evidence`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Add your own evidence" }).waitFor({ timeout: 30000 });
  const png = path.join(SHOTS, "upload-test.png");
  fs.writeFileSync(png, Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64"));
  await page.getByLabel("Note").fill("Customer mentioned a neighbour on chat");
  await page.locator('input[type=file]').setInputFiles(png);
  await page.getByRole("button", { name: "Add to dispute" }).click();
  await page.getByText("Seller upload: upload-test.png").first().waitFor({ timeout: 20000 });
  check("browser upload: file and note appear after submit (router refresh works)", true);
  check("uploaded image has a preview", (await page.locator('img[src*="/core/files/"]').count()) >= 1);
  check("note and upload are shown as the seller's, not verified", (await page.getByText("Your note / upload").count()) >= 2);

  // upload rejection surfaces the API's message
  const fake = path.join(SHOTS, "fake.png");
  fs.writeFileSync(fake, "this is not an image");
  await page.locator('input[type=file]').setInputFiles(fake);
  await page.getByRole("button", { name: "Add to dispute" }).click();
  await page.getByText("only PNG, JPG and PDF files are accepted").waitFor({ timeout: 10000 });
  check("rejected upload shows the API's reason (CORS ok on errors)", true);

  // ---------------------------------------------------------------- mobile layout
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto(`${WEB}/disputes/${id4}?tab=draft&fight=1`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Your response" }).waitFor({ timeout: 30000 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check("no horizontal scroll at phone width", overflow <= 1, `overflow ${overflow}px`);
  await page.screenshot({ path: path.join(SHOTS, "shot-editor-mobile.png"), fullPage: true });

  console.log("\nbrowser problems:", problems.length ? "" : "none");
  problems.forEach((p) => console.log("  ", p.slice(0, 200)));
  await browser.close();

  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  process.exit(failed.length ? 1 : 0);
})().catch((e) => {
  console.error("SCRIPT ERROR:", e.message.split("\n").slice(0, 6).join("\n"));
  process.exit(2);
});
