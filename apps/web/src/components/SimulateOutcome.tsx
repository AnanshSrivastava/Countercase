"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

type Outcome = "won" | "lost";

/**
 * DEMO ONLY. Stands in for the bank's decision so the demo can show the agent learning from a result
 * without waiting weeks. Only rendered when the API reports demo tools are on.
 */
export function SimulateOutcome({ disputeId, apiUrl }: { disputeId: string; apiUrl: string }) {
  const router = useRouter();
  const [, startTransition] = useTransition();
  const [busy, setBusy] = useState<Outcome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recorded, setRecorded] = useState<{ outcome: Outcome; agentOk: boolean } | null>(null);

  async function recordWithAgent(outcome: Outcome): Promise<boolean> {
    try {
      const res = await fetch(`${apiUrl}/agent/disputes/${encodeURIComponent(disputeId)}/outcome`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ outcome }),
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  async function run(outcome: Outcome) {
    setBusy(outcome);
    setError(null);
    try {
      // The core status is the source of truth, so it goes first.
      const res = await fetch(`${apiUrl}/core/disputes/${encodeURIComponent(disputeId)}/simulate-outcome`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ outcome }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new Error(body?.detail ?? `Could not simulate (${res.status}).`);
      setRecorded({ outcome, agentOk: await recordWithAgent(outcome) });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (recorded) {
    return (
      <section
        role="status"
        className="rounded-lg border border-violet-300 bg-violet-50 p-4 dark:border-violet-900 dark:bg-violet-950/40"
      >
        <h2 className="font-semibold">Simulated outcome recorded: {recorded.outcome}</h2>
        {recorded.agentOk ? (
          <p className="mt-1 text-sm">The agent has learned from this result.</p>
        ) : (
          <div className="mt-1 text-sm">
            <p>The status was updated, but the agent could not record it.</p>
            <button
              type="button"
              onClick={async () => setRecorded({ outcome: recorded.outcome, agentOk: await recordWithAgent(recorded.outcome) })}
              className="mt-2 rounded-md border border-zinc-300 px-3 py-1 text-xs dark:border-zinc-700"
            >
              Try again
            </button>
          </div>
        )}
        <button
          type="button"
          onClick={() => startTransition(() => router.refresh())}
          className="mt-3 rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
        >
          Done, show what was learned
        </button>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-dashed border-violet-400 p-4 dark:border-violet-700">
      <h2 className="font-semibold">
        Demo tool <span className="text-xs font-normal text-violet-700 dark:text-violet-300">simulated, nothing is sent to anyone</span>
      </h2>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
        Real bank decisions take weeks. Pick a result to see the agent learn from it now.
      </p>
      <div className="mt-3 flex flex-wrap gap-3">
        {(["won", "lost"] as const).map((o) => (
          <button
            key={o}
            type="button"
            disabled={busy !== null}
            onClick={() => run(o)}
            className="rounded-md border border-violet-400 px-3 py-1.5 text-sm font-medium hover:bg-violet-50 disabled:opacity-50 dark:border-violet-700 dark:hover:bg-violet-950"
          >
            {busy === o ? "Working…" : `Simulate: ${o}`}
          </button>
        ))}
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700 dark:text-red-400">
          {error}
        </p>
      )}
    </section>
  );
}
