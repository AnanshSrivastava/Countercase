"use client";

import { useEffect, useState } from "react";

import type { DirectiveProposal } from "@/lib/types";

/**
 * After approving or accepting, ask the agent what it could learn from the seller's edits or decision
 * (M3). The agent only PROPOSES rules; nothing is saved until the seller confirms one here.
 */
export function LearnedSuggestions({
  apiUrl,
  disputeId,
  before,
  after,
  decision,
}: {
  apiUrl: string;
  disputeId: string;
  before: string;
  after: string;
  decision: "fight" | "accept";
}) {
  const [proposals, setProposals] = useState<DirectiveProposal[] | null>(null);
  const [saved, setSaved] = useState<string[]>([]);
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${apiUrl}/agent/disputes/${encodeURIComponent(disputeId)}/edit`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ before, after, decision }),
        });
        if (!res.ok) throw new Error();
        const body = await res.json();
        if (!cancelled) setProposals(body.proposals ?? []);
      } catch {
        if (!cancelled) setProposals([]); // learning is optional; never block the seller
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiUrl, disputeId, before, after, decision]);

  async function save(p: DirectiveProposal) {
    setError(null);
    try {
      const res = await fetch(`${apiUrl}/agent/directives`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: p.text }),
      });
      if (!res.ok) throw new Error();
      setSaved((prev) => [...prev, p.text]);
    } catch {
      setError("Could not save that rule.");
    }
  }

  const open = (proposals ?? []).filter((p) => !saved.includes(p.text) && !dismissed.includes(p.text));
  if (proposals === null || (open.length === 0 && saved.length === 0)) return null;

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="font-semibold">Should Recoup remember this?</h2>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        Based on what you just did. A rule is only saved if you say yes, and you can delete it later.
      </p>
      <ul className="mt-2 flex flex-col gap-2">
        {open.map((p) => (
          <li key={p.text} className="flex flex-wrap items-center gap-3 text-sm">
            <span className="min-w-0 flex-1">
              <span className="font-medium">{p.text}</span>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">{p.reason}</span>
            </span>
            <button
              type="button"
              onClick={() => save(p)}
              className="rounded-md bg-zinc-900 px-3 py-1 text-xs font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
            >
              Save as a rule
            </button>
            <button
              type="button"
              onClick={() => setDismissed((prev) => [...prev, p.text])}
              className="rounded-md border border-zinc-300 px-3 py-1 text-xs dark:border-zinc-700"
            >
              No thanks
            </button>
          </li>
        ))}
        {saved.map((t) => (
          <li key={t} className="text-sm text-emerald-700 dark:text-emerald-400">
            Saved: {t}
          </li>
        ))}
      </ul>
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700 dark:text-red-400">
          {error}
        </p>
      )}
    </section>
  );
}
