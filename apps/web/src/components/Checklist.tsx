import type { ChecklistRow } from "@/lib/types";

/** Evidence checklist from the agent: what the dispute type needs and what we already have. */
export function Checklist({ rows }: { rows: ChecklistRow[] }) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="font-semibold">Evidence checklist</h2>
      <ul className="mt-2 flex flex-col gap-1 text-sm">
        {rows.map((row) => (
          <li key={row.item} className="flex items-center gap-2">
            <span
              aria-hidden
              className={row.status === "available" ? "text-emerald-600 dark:text-emerald-400" : "text-zinc-400"}
            >
              {row.status === "available" ? "✓" : "○"}
            </span>
            <span className={row.status === "missing" ? "text-zinc-500 dark:text-zinc-400" : ""}>
              {row.item}
              <span className="sr-only">{row.status === "available" ? " (available)" : " (missing)"}</span>
            </span>
            {row.required === false && <span className="text-xs text-zinc-400">optional</span>}
            {row.evidence_id && (
              <a href={`?tab=evidence#${row.evidence_id}`} className="font-mono text-xs text-zinc-500 hover:underline">
                {row.evidence_id}
              </a>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
