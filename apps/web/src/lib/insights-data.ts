// Server-side data access for the Insights page. Only import from server components (node:fs).
//
// Live mode: GET /core/insights, which is the AUTHORITATIVE implementation (plain SQL over the
// disputes table, apps/api/app/core/insights.py).
// Fixture mode (NEXT_PUBLIC_USE_FIXTURES=1) has no database, so the same payload is computed here
// from data/seed/history.json (SYNTHETIC, read-only). `computeFromHistory` mirrors the Python
// definitions and tip rules on purpose; if the two ever disagree, the live path is right.

import { readFile } from "node:fs/promises";
import path from "node:path";
import { connection } from "next/server";

import { ApiError, useFixtures } from "./data";
import type {
  CategoryWinRate,
  Counts,
  EvidenceReadiness,
  GroupStat,
  Headline,
  Insights,
  Tip,
} from "./insights-types";

const API_URL = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const HISTORY_PATH =
  process.env.SEED_HISTORY_PATH ?? path.join(process.cwd(), "..", "..", "data", "seed", "history.json");

export async function getInsights(): Promise<Insights> {
  await connection(); // per-request data: never prerender
  if (useFixtures) {
    const history = JSON.parse(await readFile(/*turbopackIgnore: true*/ HISTORY_PATH, "utf-8")) as History;
    return computeFromHistory(history);
  }
  const res = await fetch(`${API_URL}/core/insights`, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: "http_error", detail: res.statusText }));
    throw new ApiError(res.status, body.error ?? "http_error", body.detail ?? res.statusText);
  }
  return (await res.json()) as Insights;
}

// ---- fixture-mode computation (mirrors apps/api/app/core/insights.py) -----------------------

interface HistoryCase {
  id: string;
  category: string;
  courier: string | null;
  sku: string | null;
  amount: number;
  currency: string;
  evidence: string[];
  outcome: "won" | "lost" | "accepted";
}
interface History {
  seller_id: string;
  cases: HistoryCase[];
}

const READINESS_TYPES = [
  "order_receipt",
  "delivery_proof",
  "tracking",
  "ip_device",
  "prior_orders",
  "customer_message",
  "refund_policy",
] as const;
// Same mapping as the seed loader: photo and signature both count as delivery proof.
const EVIDENCE_TYPE: Record<string, string> = {
  order_receipt: "order_receipt",
  tracking: "tracking",
  delivery_photo: "delivery_proof",
  signature: "delivery_proof",
  prior_orders: "prior_orders",
  ip_device: "ip_device",
  refund_policy: "refund_policy",
  customer_message: "customer_message",
};

const MIN_FOUGHT_FOR_CATEGORY = 3;
const MIN_CLOSED_FOR_GROUP = 2;
const SMALL_GROUP = 5;
const MAX_RANKED = 5;
const MAX_TIPS = 5;
const COURIER_MIN_FOUGHT = 3;
const COURIER_MARGIN = 0.15;
const CATEGORY_MAX_WIN_RATE = 0.4;
const EVIDENCE_GAP = 0.3;
const EVIDENCE_GAP_MIN_N = 3;
const PRODUCT_MIN_DISPUTES = 4;
const PRODUCT_MIN_SHARE = 0.3;
const PRODUCT_MIN_TOTAL = 8;
const LARGE_PERCENTILE = 0.75;
const LARGE_MIN_CLOSED = 8;

interface Tally {
  won: number;
  lost: number;
  accepted: number;
  money_lost: number;
}

const rate = (num: number, den: number): number | null => (den ? Math.round((num / den) * 1e4) / 1e4 : null);
const pct = (num: number, den: number) => (den ? `${Math.round((100 * num) / den)}%` : "n/a");
const fmtMoney = (minor: number, cur: string) =>
  `${(minor / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${cur.toUpperCase()}`;
const label = (t: string) => t.replaceAll("_", " ");
const sumBy = <T,>(xs: T[], f: (x: T) => number) => xs.reduce((a, x) => a + f(x), 0);

function counts(d: Tally): Counts {
  return {
    n_closed: d.won + d.lost + d.accepted,
    n_fought: d.won + d.lost,
    won: d.won,
    lost: d.lost,
    accepted: d.accepted,
  };
}

function tally(cases: HistoryCase[], key: (c: HistoryCase) => string | null): Map<string, Tally> {
  const out = new Map<string, Tally>();
  for (const c of cases) {
    const k = key(c);
    if (k === null) continue;
    const t = out.get(k) ?? { won: 0, lost: 0, accepted: 0, money_lost: 0 };
    t[c.outcome] += 1;
    if (c.outcome === "lost") t.money_lost += c.amount;
    out.set(k, t);
  }
  return out;
}

function smallNote(n: number): string | null {
  return n < SMALL_GROUP ? `Small sample: only ${n} fought cases, treat as a hint, not a finding.` : null;
}

function groupStats(groups: Map<string, Tally>): GroupStat[] {
  const out: GroupStat[] = [];
  for (const [key, d] of groups) {
    const c = counts(d);
    if (c.n_closed < MIN_CLOSED_FOR_GROUP || c.lost === 0) continue;
    out.push({
      key,
      ...c,
      loss_rate: rate(c.lost, c.n_fought),
      money_lost: d.money_lost,
      small_sample: c.n_fought < SMALL_GROUP,
    });
  }
  out.sort((a, b) => b.money_lost - a.money_lost || (b.loss_rate ?? 0) - (a.loss_rate ?? 0) || (a.key < b.key ? -1 : 1));
  return out.slice(0, MAX_RANKED);
}

type TypeCounts = Map<string, number>; // `${type}|${won|lost}` -> distinct disputes with that type

function typeCounts(cases: HistoryCase[]): TypeCounts {
  const out: TypeCounts = new Map();
  for (const c of cases) {
    if (c.outcome === "accepted") continue;
    const types = new Set(c.evidence.map((e) => EVIDENCE_TYPE[e]).filter(Boolean));
    for (const t of types) out.set(`${t}|${c.outcome}`, (out.get(`${t}|${c.outcome}`) ?? 0) + 1);
  }
  return out;
}

function bestGap(tc: TypeCounts, wonTotal: number, lostTotal: number, minN: number): [string, number, number] | null {
  if (wonTotal < minN || lostTotal < minN) return null;
  let best: [number, string, number, number] | null = null;
  for (const t of READINESS_TYPES) {
    const w = tc.get(`${t}|won`) ?? 0;
    const lo = tc.get(`${t}|lost`) ?? 0;
    const gap = w / wonTotal - lo / lostTotal;
    if (gap >= EVIDENCE_GAP && (best === null || gap > best[0])) best = [gap, t, w, lo];
  }
  return best ? [best[1], best[2], best[3]] : null;
}

export function computeFromHistory(history: History): Insights {
  const currencyCount = new Map<string, number>();
  for (const c of history.cases) currencyCount.set(c.currency.toLowerCase(), (currencyCount.get(c.currency.toLowerCase()) ?? 0) + 1);
  const ranked = [...currencyCount].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1));
  const currency = currencyCount.has("usd") ? "usd" : (ranked[0]?.[0] ?? "usd");
  const other_currencies = ranked.filter(([c]) => c !== currency).map(([c, n]) => ({ currency: c, disputes: n }));
  const cases = history.cases.filter((c) => c.currency.toLowerCase() === currency);

  // Every history case is closed, so open disputes are always 0 here.
  const of = (o: HistoryCase["outcome"]) => cases.filter((c) => c.outcome === o);
  const amt = (o: HistoryCase["outcome"]) => sumBy(of(o), (c) => c.amount);
  const total = cases.length;
  const totalAmount = sumBy(cases, (c) => c.amount);
  const fought = of("won").length + of("lost").length;
  const head: Headline = {
    total_disputes: total,
    open_disputes: 0,
    closed_disputes: total,
    won: of("won").length,
    lost: of("lost").length,
    accepted: of("accepted").length,
    fought,
    win_rate: rate(of("won").length, fought),
    money_at_stake_open: 0,
    money_lost: amt("lost"),
    money_conceded: amt("accepted"),
    money_recovered: amt("won"),
    total_disputed_amount: totalAmount,
    net_recovery_rate: rate(amt("won"), totalAmount),
    closed_disputed_amount: totalAmount,
    net_recovery_rate_closed: rate(amt("won"), totalAmount),
  };

  const reasonMap = new Map<string, { count: number; amount: number }>();
  for (const c of cases) {
    const r = reasonMap.get(c.category) ?? { count: 0, amount: 0 };
    r.count += 1;
    r.amount += c.amount;
    reasonMap.set(c.category, r);
  }
  const top_reasons = [...reasonMap]
    .map(([category, r]) => ({ category, ...r }))
    .sort((a, b) => b.count - a.count || b.amount - a.amount || (a.category < b.category ? -1 : 1));

  const categories = tally(cases, (c) => c.category);
  const win_rate_by_category: CategoryWinRate[] = [...categories]
    .map(([category, d]) => {
      const c = counts(d);
      return {
        category,
        ...c,
        win_rate: rate(c.won, c.n_fought),
        low_confidence: c.n_fought < MIN_FOUGHT_FOR_CATEGORY,
      };
    })
    .sort((a, b) => b.n_closed - a.n_closed || (a.category < b.category ? -1 : 1));

  const couriers = tally(cases, (c) => c.courier);
  const products = tally(cases, (c) => c.sku);
  const tc = typeCounts(cases);
  const evidence_readiness: EvidenceReadiness[] = READINESS_TYPES.map((t) => ({
    type: t,
    won_with: tc.get(`${t}|won`) ?? 0,
    won_total: head.won,
    lost_with: tc.get(`${t}|lost`) ?? 0,
    lost_total: head.lost,
  }));

  return {
    seller_id: history.seller_id,
    currency,
    other_currencies,
    headline: head,
    top_reasons,
    win_rate_by_category,
    worst_couriers: groupStats(couriers),
    worst_products: groupStats(products),
    tips: buildTips(cases, currency, head, couriers, products, categories, tc),
    evidence_readiness,
  };
}

function buildTips(
  cases: HistoryCase[],
  currency: string,
  head: Headline,
  couriers: Map<string, Tally>,
  products: Map<string, Tally>,
  categories: Map<string, Tally>,
  tc: TypeCounts,
): Tip[] {
  const tips: Tip[] = [];
  const overallLoss = rate(head.lost, head.fought);

  // 1. courier loss rate clearly above the overall rate
  if (overallLoss !== null) {
    const cands: [number, number, string, Counts][] = [];
    for (const [name, d] of couriers) {
      const c = counts(d);
      const r = rate(c.lost, c.n_fought);
      if (c.n_fought >= COURIER_MIN_FOUGHT && c.lost >= 2 && r !== null && r >= overallLoss + COURIER_MARGIN)
        cands.push([d.money_lost, r, name, c]);
    }
    cands.sort((a, b) => b[0] - a[0] || b[1] - a[1]);
    if (cands[0]) {
      const [money, , name, c] = cands[0];
      tips.push({
        id: "courier_loss_rate",
        title: `${name} disputes are lost more often than your average`,
        evidence: [
          { label: `${name} loss rate`, value: pct(c.lost, c.n_fought) },
          { label: `${name} fought cases`, value: `${c.lost} lost of ${c.n_fought}` },
          { label: "Your overall loss rate", value: `${pct(head.lost, head.fought)} (${head.lost} of ${head.fought})` },
          { label: `Money lost on ${name}`, value: fmtMoney(money, currency) },
        ],
        action: `Ask for signature or photo proof of delivery on ${name} shipments, or compare it with another carrier.`,
        small_sample: c.n_fought < SMALL_GROUP,
        sample_note: smallNote(c.n_fought),
      });
    }
  }

  // 2. a dispute type with a low win rate, plus the evidence that separates wins from losses
  if (head.fought > 0) {
    const cands: [number, string, Counts][] = [];
    for (const [cat, d] of categories) {
      const c = counts(d);
      const r = rate(c.won, c.n_fought);
      if (
        c.n_fought >= MIN_FOUGHT_FOR_CATEGORY &&
        r !== null &&
        r <= CATEGORY_MAX_WIN_RATE &&
        (head.win_rate === null || r < head.win_rate)
      )
        cands.push([d.money_lost, cat, c]);
    }
    cands.sort((a, b) => b[0] - a[0] || (a[1] < b[1] ? 1 : -1));
    if (cands[0]) {
      const [, cat, c] = cands[0];
      const facts = [
        { label: `${label(cat)} win rate`, value: pct(c.won, c.n_fought) },
        { label: `${label(cat)} fought cases`, value: `${c.won} won of ${c.n_fought}` },
        { label: "Your overall win rate", value: `${pct(head.won, head.fought)} (${head.won} of ${head.fought})` },
      ];
      let action = `Review these cases before fighting similar ${label(cat)} disputes; consider accepting low-value ones.`;
      const gap = bestGap(typeCounts(cases.filter((x) => x.category === cat)), c.won, c.lost, 1);
      if (gap) {
        const [t, w, lo] = gap;
        facts.push({ label: `${label(t)} on record`, value: `${w} of ${c.won} won vs ${lo} of ${c.lost} lost` });
        action = `Collect ${label(t)} for ${label(cat)} disputes before responding; it was present far more often on the cases you won.`;
      }
      tips.push({
        id: "category_low_win_rate",
        title: `You win few ${label(cat)} disputes`,
        evidence: facts,
        action,
        small_sample: c.n_fought < SMALL_GROUP,
        sample_note: smallNote(c.n_fought),
      });
    }
  }

  // 3. many disputes on one product
  if (head.total_disputes >= PRODUCT_MIN_TOTAL) {
    const skuCount = new Map<string, number>();
    for (const c of cases) if (c.sku) skuCount.set(c.sku, (skuCount.get(c.sku) ?? 0) + 1);
    const top = [...skuCount].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))[0];
    if (top && top[1] >= PRODUCT_MIN_DISPUTES && top[1] / head.total_disputes >= PRODUCT_MIN_SHARE) {
      const [sku, n] = top;
      const amount = sumBy(cases.filter((c) => c.sku === sku), (c) => c.amount);
      const c = counts(products.get(sku) ?? { won: 0, lost: 0, accepted: 0, money_lost: 0 });
      const small = head.total_disputes < 20;
      tips.push({
        id: "product_concentration",
        title: `${sku} accounts for a large share of your disputes`,
        evidence: [
          { label: `${sku} disputes`, value: `${n} of ${head.total_disputes} (${pct(n, head.total_disputes)})` },
          { label: `Amount disputed on ${sku}`, value: fmtMoney(amount, currency) },
          { label: `${sku} closed outcomes`, value: `${c.won} won, ${c.lost} lost, ${c.accepted} accepted` },
        ],
        action: `Check the listing, packaging and description of ${sku}; a product problem is cheaper to fix than to dispute.`,
        small_sample: small,
        sample_note: small ? `Based on ${head.total_disputes} disputes in total.` : null,
      });
    }
  }

  // 4. large not-received disputes closed without verified delivery proof
  if (cases.length >= LARGE_MIN_CLOSED) {
    const ordered = cases.map((c) => c.amount).sort((a, b) => a - b);
    const threshold = ordered[Math.min(ordered.length - 1, Math.floor(LARGE_PERCENTILE * ordered.length))];
    const big = cases.filter((c) => c.category === "not_received" && c.amount >= threshold);
    const missing = big.filter((c) => !c.evidence.some((e) => EVIDENCE_TYPE[e] === "delivery_proof"));
    const lostMissing = missing.filter((c) => c.outcome === "lost").length;
    if (missing.length >= 2 && lostMissing >= 1) {
      tips.push({
        id: "large_without_delivery_proof",
        title: "Large not-received disputes were closed without delivery proof",
        evidence: [
          { label: "Large amount threshold (top quarter of closed)", value: fmtMoney(threshold, currency) },
          { label: "Large not-received closed cases", value: String(big.length) },
          { label: "...without verified delivery proof", value: String(missing.length) },
          { label: "...of which lost", value: String(lostMissing) },
        ],
        action:
          "For high-value orders, ship with signature or photo confirmation so delivery proof exists if the customer disputes.",
        small_sample: big.length < SMALL_GROUP,
        sample_note: smallNote(big.length),
      });
    }
  }

  // 5. one evidence type is far more common on won than on lost disputes
  const gap = bestGap(tc, head.won, head.lost, EVIDENCE_GAP_MIN_N);
  if (gap) {
    const [t, w, lo] = gap;
    const n = Math.min(head.won, head.lost);
    tips.push({
      id: "evidence_gap",
      title: `Winning disputes usually have ${label(t)}`,
      evidence: [
        { label: `${label(t)} on won disputes`, value: `${w} of ${head.won}` },
        { label: `${label(t)} on lost disputes`, value: `${lo} of ${head.lost}` },
      ],
      action: `Make collecting ${label(t)} a standard step for every dispute.`,
      small_sample: n < SMALL_GROUP,
      sample_note: smallNote(n),
    });
  }
  return tips.slice(0, MAX_TIPS);
}
