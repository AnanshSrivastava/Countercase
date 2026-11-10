import Link from "next/link";

import { deleteMemory, dismissBelief } from "./actions";
import { getBeliefChanges, getBeliefs, getDisputeMemory } from "./data";
import type { Belief, BeliefChange, MemoryKind, MemoryRef } from "./types";

const KIND_LABEL: Record<MemoryKind, string> = {
  case: "Past case",
  belief: "Belief",
  directive: "Your rule",
  mental_model: "Playbook",
  pattern: "Pattern",
  customer_history: "Customer history",
  opinion: "Your note (unverified)",
};

const card = "rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900";
const pct = (x: number) => `${Math.round(x * 100)}%`;

/** Dispute detail → Memory tab: what the agent remembered, what it believes, and controls to correct it. */
export async function MemoryTab({ disputeId }: { disputeId: string }) {
  const [memory, beliefs, changes] = await Promise.all([
    getDisputeMemory(disputeId),
    getBeliefs(),
    getBeliefChanges(),
  ]);
  const used = memory.data.filter((m) => m.used);
  const notUsed = memory.data.filter((m) => !m.used);

  return (
    <div className="flex flex-col gap-4">
      <section className={card}>
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="font-semibold">Memory used for this dispute</h2>
          <Link href="/playbook" className="text-sm text-sky-700 hover:underline dark:text-sky-400">
            Open your Playbook →
          </Link>
        </div>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Everything the agent recalled to write the advice and letter, and why. Delete anything that is wrong.
        </p>
        {memory.unavailable && <Notice text={`Memory is unavailable: ${memory.unavailable}`} />}
        {used.length === 0 && !memory.unavailable && (
          <p className="mt-3 text-sm text-zinc-500">
            Nothing recalled yet. With Memory OFF, or for a new seller, the agent works from general rules only.
          </p>
        )}
        <ul className="mt-3 flex flex-col gap-2">
          {used.map((m) => (
            <MemoryRow key={m.id} m={m} />
          ))}
        </ul>
      </section>

      {notUsed.length > 0 && (
        <section className={card}>
          <h2 className="font-semibold">Considered but not used</h2>
          <ul className="mt-3 flex flex-col gap-2">
            {notUsed.map((m) => (
              <MemoryRow key={m.id} m={m} muted />
            ))}
          </ul>
        </section>
      )}

      <BeliefChanges changes={changes.data} />
      <Beliefs beliefs={beliefs.data} unavailable={beliefs.unavailable} />
    </div>
  );
}

function Notice({ text }: { text: string }) {
  return (
    <p className="mt-3 rounded-md bg-amber-50 p-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">{text}</p>
  );
}

function Confidence({ value }: { value: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400" title="Confidence">
      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700">
        <span className="block h-full bg-sky-600" style={{ width: pct(value) }} />
      </span>
      {pct(value)}
    </span>
  );
}

function MemoryRow({ m, muted = false }: { m: MemoryRef; muted?: boolean }) {
  const isBelief = m.kind === "belief";
  return (
    <li className={`flex items-start gap-3 rounded-md border border-zinc-100 p-3 dark:border-zinc-800 ${muted ? "opacity-60" : ""}`}>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-medium dark:bg-zinc-800">{KIND_LABEL[m.kind]}</span>
          {m.event_date && <span className="text-zinc-500 dark:text-zinc-400">{m.event_date}</span>}
          {(m.kind === "belief" || m.kind === "pattern" || m.kind === "mental_model") && <Confidence value={m.confidence} />}
          {m.n_supporting > 1 && <span className="text-zinc-500 dark:text-zinc-400">n={m.n_supporting}</span>}
        </div>
        <p className="mt-1 text-sm">{m.text}</p>
        {m.why && <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">Why: {m.why}</p>}
      </div>
      {m.editable && (
        <form action={isBelief ? dismissBelief : deleteMemory}>
          <input type="hidden" name={isBelief ? "key" : "id"} value={isBelief ? m.id.replace(/^belief:/, "") : m.id} />
          <button
            type="submit"
            className="rounded-md px-2 py-1 text-xs text-red-700 ring-1 ring-red-200 hover:bg-red-50 dark:text-red-400 dark:ring-red-900 dark:hover:bg-red-950"
            title={isBelief ? "Reject this belief" : "Delete this memory"}
          >
            {isBelief ? "Reject" : "Delete"}
          </button>
        </form>
      )}
    </li>
  );
}

export function BeliefChanges({ changes }: { changes: BeliefChange[] }) {
  if (changes.length === 0) return null;
  return (
    <section className={card}>
      <h2 className="font-semibold">What the agent just learned</h2>
      <ul className="mt-3 flex flex-col gap-2">
        {[...changes].reverse().slice(0, 5).map((c, i) => (
          <li key={`${c.key}-${i}`} className="rounded-md bg-sky-50 p-3 text-sm dark:bg-sky-950">
            <p>{c.text}</p>
            <p className="mt-1 text-xs font-medium text-sky-800 dark:text-sky-300">
              {c.status === "formed"
                ? `New belief — confidence ${c.after === null ? "" : pct(c.after)}`
                : c.status === "dropped"
                  ? "No longer supported by your cases"
                  : `Confidence ${c.before === null ? "" : pct(c.before)} → ${c.after === null ? "" : pct(c.after)}`}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Beliefs({ beliefs, unavailable }: { beliefs: Belief[]; unavailable?: string }) {
  return (
    <section className={card}>
      <h2 className="font-semibold">What the agent believes about your business</h2>
      {unavailable && <Notice text={unavailable} />}
      {beliefs.length === 0 && !unavailable && (
        <p className="mt-2 text-sm text-zinc-500">Not enough resolved disputes yet to form a belief.</p>
      )}
      <ul className="mt-3 flex flex-col gap-2">
        {beliefs.map((b) => (
          <li key={b.key} className="flex items-start gap-3 rounded-md border border-zinc-100 p-3 dark:border-zinc-800">
            <div className="min-w-0 flex-1">
              <p className="text-sm">{b.text}</p>
              <div className="mt-1 flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                <Confidence value={b.confidence} />
                <span>from {b.n} cases</span>
                <span
                  className={`rounded px-1.5 py-0.5 font-medium ${
                    b.label === "weak"
                      ? "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200"
                      : "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
                  }`}
                >
                  {b.label}
                </span>
              </div>
            </div>
            <form action={dismissBelief}>
              <input type="hidden" name="key" value={b.key} />
              <button
                type="submit"
                className="rounded-md px-2 py-1 text-xs text-red-700 ring-1 ring-red-200 hover:bg-red-50 dark:text-red-400 dark:ring-red-900 dark:hover:bg-red-950"
              >
                Reject
              </button>
            </form>
          </li>
        ))}
      </ul>
    </section>
  );
}
