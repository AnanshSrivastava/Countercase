import { CATEGORY_LABEL, EVIDENCE_LABEL, money } from "@/lib/format";
import type { Category, EvidenceType } from "@/lib/types";
import type { EvidenceReadiness, GroupStat, Insights, Tip } from "@/lib/insights-types";

import { BarList, Card, LowConfidence, SERIES, Track, type BarRow } from "./Bars";

const catLabel = (c: string) => CATEGORY_LABEL[c as Category] ?? c;
const evLabel = (t: string) => EVIDENCE_LABEL[t as EvidenceType] ?? t;
const pct = (p: number | null) => (p === null ? "n/a" : `${Math.round(p * 100)}%`);

export function InsightsView({ data }: { data: Insights }) {
  const h = data.headline;
  const cur = data.currency;
  if (h.closed_disputes === 0) {
    return (
      <div className="flex flex-col gap-4">
        <div className="rounded-lg border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
          Insights appear once disputes are closed.
          {h.total_disputes > 0 && (
            <p className="mt-2">
              {h.total_disputes} open {h.total_disputes === 1 ? "dispute" : "disputes"} with{" "}
              {money(h.money_at_stake_open, cur)} at stake so far.
            </p>
          )}
        </div>
        <CurrencyNote data={data} />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-6">
      <StatTiles data={data} />
      <CurrencyNote data={data} />
      <div className="grid gap-6 md:grid-cols-2">
        <MoneyChart data={data} />
        <TopReasons data={data} />
      </div>
      <WinRateByCategory data={data} />
      <div className="grid gap-6 md:grid-cols-2">
        <Worst title="Worst couriers" noun="courier" rows={data.worst_couriers} cur={cur} />
        <Worst title="Worst products" noun="product" rows={data.worst_products} cur={cur} />
      </div>
      <Tips tips={data.tips} />
      <Readiness rows={data.evidence_readiness} />
    </div>
  );
}

function CurrencyNote({ data }: { data: Insights }) {
  const others = data.other_currencies;
  return (
    <p className="text-xs text-zinc-500 dark:text-zinc-400">
      All money is in {data.currency.toUpperCase()}.
      {others.length > 0 &&
        ` Not included: ${others.map((o) => `${o.disputes} in ${o.currency.toUpperCase()}`).join(", ")}.`}
    </p>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{sub}</p>
    </div>
  );
}

function StatTiles({ data }: { data: Insights }) {
  const h = data.headline;
  const cur = data.currency;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Tile
        label="Disputes"
        value={String(h.total_disputes)}
        sub={`${h.open_disputes} open, ${h.closed_disputes} closed`}
      />
      <Tile
        label="Win rate on fought disputes"
        value={pct(h.win_rate)}
        sub={`${h.won} won of ${h.fought} fought (${h.accepted} accepted, not fought)`}
      />
      <Tile
        label="Net recovery rate"
        value={pct(h.net_recovery_rate)}
        sub={`${money(h.money_recovered, cur)} recovered of ${money(h.total_disputed_amount, cur)} disputed`}
      />
      <Tile
        label="At stake in open disputes"
        value={money(h.money_at_stake_open, cur)}
        sub={`${h.open_disputes} open ${h.open_disputes === 1 ? "dispute" : "disputes"}`}
      />
    </div>
  );
}

function MoneyChart({ data }: { data: Insights }) {
  const h = data.headline;
  const cur = data.currency;
  const max = Math.max(h.money_recovered, h.money_lost, h.money_conceded, 1);
  const rows: BarRow[] = [
    { key: "rec", label: "Recovered (won)", amount: h.money_recovered, n: h.won, color: "blue" as const },
    { key: "lost", label: "Lost (fought and lost)", amount: h.money_lost, n: h.lost, color: "orange" as const },
    { key: "conc", label: "Conceded (accepted)", amount: h.money_conceded, n: h.accepted, color: "neutral" as const },
  ].map((r) => ({
    key: r.key,
    label: r.label,
    fraction: r.amount / max,
    valueText: money(r.amount, cur),
    note: `${r.n} ${r.n === 1 ? "dispute" : "disputes"}`,
    color: r.color,
    tableCells: [r.label, money(r.amount, cur), String(r.n)],
  }));
  return (
    <Card title="Money lost vs recovered" subtitle="Closed disputes only. Same scale for all three bars.">
      <BarList caption="Money recovered, lost and conceded" columns={["Outcome", "Amount", "Disputes"]} rows={rows} />
    </Card>
  );
}

function TopReasons({ data }: { data: Insights }) {
  const cur = data.currency;
  const top = data.top_reasons.slice(0, 5);
  const max = Math.max(...top.map((r) => r.count), 1);
  const rows: BarRow[] = top.map((r) => ({
    key: r.category,
    label: catLabel(r.category),
    fraction: r.count / max,
    valueText: `${r.count} ${r.count === 1 ? "dispute" : "disputes"}`,
    note: `${money(r.amount, cur)} disputed`,
    tableCells: [catLabel(r.category), String(r.count), money(r.amount, cur)],
  }));
  return (
    <Card title="Top reasons" subtitle="Why customers dispute, all disputes (open and closed).">
      <BarList caption="Top dispute reasons" columns={["Reason", "Disputes", "Amount"]} rows={rows} />
    </Card>
  );
}

function WinRateByCategory({ data }: { data: Insights }) {
  const rows: BarRow[] = data.win_rate_by_category.map((c) => ({
    key: c.category,
    label: catLabel(c.category),
    fraction: c.win_rate ?? 0,
    valueText: c.win_rate === null ? "n/a" : pct(c.win_rate),
    note: `${c.won} won of ${c.n_fought} fought; ${c.n_closed} closed${c.accepted ? ` (${c.accepted} accepted)` : ""}`,
    lowConfidence: c.low_confidence,
    tableCells: [
      catLabel(c.category),
      pct(c.win_rate),
      `${c.won} of ${c.n_fought}`,
      String(c.n_closed),
      c.low_confidence ? "low confidence" : "ok",
    ],
  }));
  return (
    <Card
      title="Win rate by dispute type"
      subtitle="Won / (won + lost). Fewer than 3 fought cases is marked low confidence."
    >
      <BarList
        caption="Win rate by dispute type"
        columns={["Type", "Win rate", "Won of fought", "Closed", "Confidence"]}
        rows={rows}
      />
    </Card>
  );
}

function Worst({
  title,
  noun,
  rows,
  cur,
}: {
  title: string;
  noun: string;
  rows: GroupStat[];
  cur: string;
}) {
  const max = Math.max(...rows.map((r) => r.money_lost), 1);
  const bars: BarRow[] = rows.map((r) => ({
    key: r.key,
    label: r.key,
    fraction: r.money_lost / max,
    valueText: money(r.money_lost, cur),
    note: `Lost ${r.lost} of ${r.n_fought} fought (${pct(r.loss_rate)}); ${r.n_closed} closed`,
    color: "orange",
    lowConfidence: r.small_sample,
    tableCells: [r.key, money(r.money_lost, cur), `${r.lost} of ${r.n_fought}`, pct(r.loss_rate), String(r.n_closed)],
  }));
  return (
    <Card title={title} subtitle={`Ranked by money lost. Only ${noun}s with 2 or more closed cases; under 5 fought is a small sample.`}>
      {bars.length === 0 ? (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">No {noun} has 2 or more closed cases with a loss yet.</p>
      ) : (
        <BarList
          caption={title}
          columns={[noun[0].toUpperCase() + noun.slice(1), "Money lost", "Lost of fought", "Loss rate", "Closed"]}
          rows={bars}
        />
      )}
    </Card>
  );
}

function Tips({ tips }: { tips: Tip[] }) {
  return (
    <section aria-labelledby="tips-h">
      <h2 id="tips-h" className="mb-3 text-base font-semibold tracking-tight">
        Tips
      </h2>
      {tips.length === 0 ? (
        <p className="rounded-lg border border-dashed border-zinc-300 p-4 text-sm text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
          No tips yet. The data does not clearly point at anything to change.
        </p>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {tips.map((t) => (
            <li key={t.id} className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
              <h3 className="font-medium">
                {t.title}
                {t.small_sample && <LowConfidence text="small sample" />}
              </h3>
              <dl className="mt-2 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-sm">
                {t.evidence.map((f) => (
                  <div key={f.label} className="contents">
                    <dt className="text-zinc-600 dark:text-zinc-400">{f.label}</dt>
                    <dd className="text-right tabular-nums">{f.value}</dd>
                  </div>
                ))}
              </dl>
              {t.sample_note && <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">{t.sample_note}</p>}
              <p className="mt-3 text-sm">
                <span className="font-medium">Suggested action: </span>
                {t.action}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Readiness({ rows }: { rows: EvidenceReadiness[] }) {
  const usable = rows.filter((r) => r.won_total + r.lost_total > 0);
  return (
    <Card
      title="Evidence readiness"
      subtitle="Verified, system-pulled evidence on your won vs lost disputes. Seller notes and uploads never count."
    >
      {usable.length === 0 ? (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">No fought disputes yet.</p>
      ) : (
        <figure className="m-0">
          <div className="mb-3 flex gap-4 text-xs text-zinc-600 dark:text-zinc-400" aria-hidden="true">
            <span className="flex items-center gap-1.5">
              <span className={`inline-block h-2.5 w-2.5 rounded-sm ${SERIES.blue}`} /> Won
            </span>
            <span className="flex items-center gap-1.5">
              <span className={`inline-block h-2.5 w-2.5 rounded-sm ${SERIES.orange}`} /> Lost
            </span>
          </div>
          <ul className="grid gap-x-8 gap-y-4 md:grid-cols-2" aria-hidden="true">
            {rows.map((r) => (
              <li key={r.type}>
                <p className="mb-1 text-sm font-medium">{evLabel(r.type)}</p>
                <ReadyBar label="Won" with_={r.won_with} total={r.won_total} color="blue" />
                <div className="h-0.5" />
                <ReadyBar label="Lost" with_={r.lost_with} total={r.lost_total} color="orange" />
              </li>
            ))}
          </ul>
          <div className="sr-only"><table>
            <caption>Disputes with each verified evidence type, won vs lost</caption>
            <thead>
              <tr>
                <th scope="col">Evidence</th>
                <th scope="col">Won disputes with it</th>
                <th scope="col">Lost disputes with it</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.type}>
                  <td>{evLabel(r.type)}</td>
                  <td>
                    {r.won_with} of {r.won_total}
                  </td>
                  <td>
                    {r.lost_with} of {r.lost_total}
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </figure>
      )}
    </Card>
  );
}

function ReadyBar({
  label,
  with_,
  total,
  color,
}: {
  label: string;
  with_: number;
  total: number;
  color: "blue" | "orange";
}) {
  return (
    <div className="grid grid-cols-[2.5rem_1fr_5.5rem] items-center gap-2 text-xs">
      <span className="text-zinc-600 dark:text-zinc-400">{label}</span>
      <Track fraction={total ? with_ / total : 0} color={color} />
      <span className="text-right tabular-nums text-zinc-700 dark:text-zinc-300">
        {with_} of {total}
      </span>
    </div>
  );
}
