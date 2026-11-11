"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, useTransition } from "react";

import { LearnedSuggestions } from "@/components/LearnedSuggestions";
import type { AcceptResult, ProcessorStatus } from "@/lib/types";

/** Shown when the agent advises accepting and has drafted no rebuttal (the customer is probably right). */
export function AcceptPanel({
  disputeId,
  apiUrl,
  rationale,
  processor,
}: {
  disputeId: string;
  apiUrl: string;
  rationale: string[];
  processor: ProcessorStatus;
}) {
  const router = useRouter();
  const [, startTransition] = useTransition();
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AcceptResult | null>(null);

  async function accept() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${apiUrl}/core/disputes/${encodeURIComponent(disputeId)}/accept`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new Error(body?.detail ?? `Could not accept (${res.status}).`);
      setResult(body as AcceptResult); // refreshed from the Done button, so the note stays visible
    } catch (e) {
      setError((e as Error).message);
    } finally {
      dialog.current?.close();
      setBusy(false);
    }
  }

  if (result) {
    return (
      <div className="flex flex-col gap-4">
        <section
          role="status"
          className="rounded-lg border border-emerald-300 bg-emerald-50 p-4 dark:border-emerald-900 dark:bg-emerald-950/40"
        >
          <h2 className="font-semibold">Dispute accepted</h2>
          <p className="mt-1 text-sm">{result.note}</p>
        </section>
        <LearnedSuggestions
          apiUrl={apiUrl}
          disputeId={disputeId}
          before=""
          after=""
          decision="accept"
        />
        <div>
          <button
            type="button"
            onClick={() => startTransition(() => router.refresh())}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            Done
          </button>
        </div>
      </div>
    );
  }

  return (
    <section className="rounded-lg border border-amber-300 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/40">
      <h2 className="text-lg font-semibold">Accept this dispute</h2>
      <p className="mt-1 text-sm">
        Countercase did not draft a rebuttal because the evidence suggests the customer is probably right.
        Fighting a claim that looks valid usually loses the amount and the fee anyway.
      </p>
      {rationale.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-sm">
          {rationale.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => dialog.current?.showModal()}
          disabled={busy}
          className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          Accept this dispute
        </button>
        <Link
          href={{ query: { tab: "draft", fight: "1" } }}
          className="text-sm text-zinc-700 underline dark:text-zinc-300"
        >
          I want to fight it anyway
        </Link>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700 dark:text-red-400">
          {error}
        </p>
      )}

      <dialog
        ref={dialog}
        aria-labelledby="accept-title"
        className="m-auto max-w-lg rounded-lg border border-zinc-300 bg-white p-5 text-zinc-900 backdrop:bg-black/50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
      >
        <h2 id="accept-title" className="text-lg font-semibold">
          Accept and give up this dispute?
        </h2>
        <p className="mt-2 text-sm">
          {processor.can_submit
            ? "This closes the dispute with Stripe (test mode). You lose the disputed amount and cannot reopen it."
            : `This is recorded here only (${processor.reason ?? "no processor available"}). You would still need to close it in your processor dashboard.`}
        </p>
        <div className="mt-4 flex justify-end gap-3">
          <button
            type="button"
            onClick={() => dialog.current?.close()}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700"
          >
            Go back
          </button>
          <button
            type="button"
            onClick={accept}
            disabled={busy}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {busy ? "Working…" : "Yes, accept it"}
          </button>
        </div>
      </dialog>
    </section>
  );
}
