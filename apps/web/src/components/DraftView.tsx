import Link from "next/link";
import { Fragment } from "react";

import { Checklist } from "@/components/Checklist";
import { percent } from "@/lib/format";
import type { Claim, Draft, EvidenceItem } from "@/lib/types";

/** A claim is sourced only if it points at an existing, verified (system-pulled) evidence item. */
function sourceFor(claim: Claim, evidence: EvidenceItem[]): EvidenceItem | null {
  const ev = evidence.find((e) => e.id === claim.evidence_id);
  return ev && ev.verified ? ev : null;
}

export function DraftView({
  draft,
  evidence,
  memory,
}: {
  draft: Draft | null;
  evidence: EvidenceItem[];
  memory: "on" | "off";
}) {
  return (
    <div className="flex flex-col gap-4">
      <MemoryToggle memory={memory} />
      {draft ? <DraftBody draft={draft} evidence={evidence} /> : <NoDraft />}
    </div>
  );
}

export function MemoryToggle({ memory }: { memory: "on" | "off" }) {
  const base = "px-3 py-1.5 text-sm font-medium first:rounded-l-md last:rounded-r-md";
  const on = "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900";
  const off = "bg-white text-zinc-700 hover:bg-zinc-50 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800";
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-zinc-600 dark:text-zinc-400">Memory</span>
      <div className="inline-flex rounded-md ring-1 ring-zinc-300 dark:ring-zinc-700" role="group">
        {(["on", "off"] as const).map((m) => (
          <Link
            key={m}
            href={{ query: { tab: "draft", memory: m } }}
            aria-pressed={memory === m}
            className={`${base} ${memory === m ? on : off}`}
          >
            {m.toUpperCase()}
          </Link>
        ))}
      </div>
    </div>
  );
}

function NoDraft() {
  return (
    <p className="rounded-lg border border-dashed border-zinc-300 p-6 text-sm text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
      No draft available for this dispute yet.
    </p>
  );
}

function DraftBody({ draft, evidence }: { draft: Draft; evidence: EvidenceItem[] }) {
  const claims = draft.claims.map((c, i) => ({ ...c, n: i + 1, source: sourceFor(c, evidence) }));
  const blocked = claims.filter((c) => !c.source);

  return (
    <>
      <AdviceCard draft={draft} />

      <Checklist rows={draft.checklist} />

      <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="font-semibold">Response letter</h2>
        <Letter text={draft.letter_md} claimCount={claims.length} />

        <h3 className="mt-4 text-sm font-semibold">Sources</h3>
        <ol className="mt-1 flex flex-col gap-1 text-sm">
          {claims.map((c) => (
            <li key={c.n} id={`fn-${c.n}`} className="flex gap-2">
              <span className="tabular-nums text-zinc-500">[{c.n}]</span>
              <span className="min-w-0">
                {c.text}{" "}
                {c.source ? (
                  <span className="text-zinc-500 dark:text-zinc-400">
                    — {c.source.summary} <span className="font-mono text-xs">({c.source.id})</span>
                  </span>
                ) : (
                  <span className="font-medium text-red-700 dark:text-red-400">
                    — no verified source ({c.evidence_id || "none"}): blocked
                  </span>
                )}
              </span>
            </li>
          ))}
        </ol>

        {blocked.length > 0 && (
          <p
            role="alert"
            className="mt-3 rounded-md bg-red-50 p-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-200"
          >
            {blocked.length} claim{blocked.length > 1 ? "s have" : " has"} no verified source. Approval is blocked
            until they are removed or backed by evidence.
          </p>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
            title={blocked.length ? "Unsourced claims must be resolved first" : "Approval and submission land in Phase 4"}
          >
            Approve and submit
          </button>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            Nothing is submitted without your approval. Editing and approval arrive in Phase 4.
          </span>
        </div>
      </section>

      <CostLine draft={draft} />
    </>
  );
}

export function AdviceCard({ draft }: { draft: Draft }) {
  const a = draft.advice;
  const fight = a.action === "fight";
  return (
    <section
      className={`rounded-lg border p-4 ${
        fight
          ? "border-sky-200 bg-sky-50 dark:border-sky-900 dark:bg-sky-950/40"
          : "border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/40"
      }`}
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-lg font-semibold">{fight ? "Recommend: fight" : "Recommend: accept"}</h2>
        <span className="text-sm tabular-nums">
          win chance {percent(a.win_probability)} (range {percent(a.interval[0])}–{percent(a.interval[1])}, based on{" "}
          {a.n_cases} case{a.n_cases === 1 ? "" : "s"})
        </span>
      </div>
      <p className="mt-1 text-sm">{a.amount_vs_cost}</p>
      {a.rationale.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-sm">
          {a.rationale.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      {a.n_cases < 3 && (
        <p className="mt-2 text-xs text-zinc-600 dark:text-zinc-400">Low confidence: few similar cases so far.</p>
      )}
    </section>
  );
}

/** Render the plain-text letter; `[n]` markers become links to footnote n. */
function Letter({ text, claimCount }: { text: string; claimCount: number }) {
  const body = text.split(/\n\s*Sources:/)[0]; // footnotes are rendered from claims instead
  return (
    <div className="mt-2 flex flex-col gap-3 text-sm leading-6">
      {body
        .split(/\n{2,}/)
        .filter((p) => p.trim())
        .map((para, i) => (
          <p key={i}>
            {para.split(/(\[\d+\])/).map((part, j) => {
              const m = part.match(/^\[(\d+)\]$/);
              if (m && Number(m[1]) <= claimCount) {
                return (
                  <sup key={j}>
                    <a href={`#fn-${m[1]}`} className="text-sky-700 hover:underline dark:text-sky-400">
                      [{m[1]}]
                    </a>
                  </sup>
                );
              }
              return <Fragment key={j}>{part}</Fragment>;
            })}
          </p>
        ))}
    </div>
  );
}

export function CostLine({ draft }: { draft: Draft }) {
  return (
    <p className="text-xs text-zinc-500 dark:text-zinc-400">
      Memory {draft.memory_mode}: {draft.memory.filter((m) => m.used).length} memories used · cost $
      {draft.cost.usd.toFixed(3)} ({draft.cost.input_tokens + draft.cost.output_tokens} tokens,{" "}
      {draft.cost.recall_calls} recall calls)
    </p>
  );
}
