// Hand-written horizontal bars (no chart library). Colours follow the dataviz skill: categorical
// slot 1 (blue) and slot 2 (orange), validated for light and dark; text always wears text colours.
// Each chart has a visually hidden table as its text alternative, and the visual part is aria-hidden.

import type { ReactNode } from "react";

export const SERIES = {
  blue: "bg-[#2a78d6] dark:bg-[#3987e5]",
  orange: "bg-[#eb6834] dark:bg-[#d95926]",
  neutral: "bg-zinc-400 dark:bg-zinc-500",
} as const;
export type Series = keyof typeof SERIES;

export interface BarRow {
  key: string;
  label: string;
  /** Bar length as a fraction 0..1 of the track. */
  fraction: number;
  /** Text shown at the end of the label line. */
  valueText: string;
  /** Small muted line under the bar (always carries the sample size). */
  note?: string;
  color?: Series;
  /** Draws the bar lighter and adds a "low confidence" marker. */
  lowConfidence?: boolean;
  /** Plain-text row for the hidden table. */
  tableCells: string[];
}

export function LowConfidence({ text = "low confidence" }: { text?: string }) {
  return (
    <span className="ml-2 rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-700 ring-1 ring-zinc-300 dark:bg-zinc-800 dark:text-zinc-300 dark:ring-zinc-600">
      {text}
    </span>
  );
}

export function Track({
  fraction,
  color = "blue",
  faded = false,
}: {
  fraction: number;
  color?: Series;
  faded?: boolean;
}) {
  const width = `${Math.max(0, Math.min(1, fraction)) * 100}%`;
  return (
    <div className="h-3 w-full rounded-r bg-zinc-100 dark:bg-zinc-800">
      <div
        className={`h-3 rounded-r ${SERIES[color]} ${faded ? "opacity-50" : ""}`}
        style={{ width, minWidth: fraction > 0 ? 4 : 0 }}
      />
    </div>
  );
}

export function BarList({
  caption,
  columns,
  rows,
}: {
  caption: string;
  columns: string[];
  rows: BarRow[];
}) {
  return (
    <figure className="m-0">
      <ul className="flex flex-col gap-3" aria-hidden="true">
        {rows.map((r) => (
          <li key={r.key}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
              <span className="min-w-0 truncate font-medium">
                {r.label}
                {r.lowConfidence && <LowConfidence />}
              </span>
              <span className="shrink-0 tabular-nums text-zinc-700 dark:text-zinc-300">{r.valueText}</span>
            </div>
            <Track fraction={r.fraction} color={r.color} faded={r.lowConfidence} />
            {r.note && <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{r.note}</p>}
          </li>
        ))}
      </ul>
      <div className="sr-only"><table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c} scope="col">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              {r.tableCells.map((c, i) => (
                <td key={i}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table></div>
    </figure>
  );
}

export function Card({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-base font-semibold tracking-tight">{title}</h2>
      {subtitle && <p className="mb-4 mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{subtitle}</p>}
      {!subtitle && <div className="mb-4" />}
      {children}
    </section>
  );
}
