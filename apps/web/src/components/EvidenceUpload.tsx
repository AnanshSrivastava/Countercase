"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, useTransition } from "react";

const MAX_BYTES = 5 * 1024 * 1024; // mirrors the API limit; the API enforces it too

export function EvidenceUpload({ disputeId, apiUrl }: { disputeId: string; apiUrl: string }) {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [, startTransition] = useTransition();

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const form = new FormData(e.currentTarget);

    const file = form.get("file");
    const hasFile = file instanceof File && file.size > 0;
    if (!hasFile) form.delete("file");
    const note = String(form.get("note") ?? "").trim();
    if (!note) form.delete("note");

    if (!hasFile && !note) {
      setError("Add a note, a file, or both.");
      return;
    }
    if (hasFile && file.size > MAX_BYTES) {
      setError("That file is larger than 5 MB.");
      return;
    }

    setBusy(true);
    try {
      // Straight from the browser to the API: avoids the Next server-action body size limit.
      const res = await fetch(`${apiUrl}/core/disputes/${encodeURIComponent(disputeId)}/evidence`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setError(body?.detail ?? `Upload failed (${res.status}).`);
        return;
      }
      formRef.current?.reset();
      startTransition(() => router.refresh());
    } catch {
      setError("Could not reach the API. Is it running?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      ref={formRef}
      onSubmit={onSubmit}
      className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
    >
      <div>
        <h2 className="font-semibold">Add your own evidence</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Notes are private and are never sent. Files can be attached to your response when you approve it,
          but neither is ever used as proof for a claim. Only data pulled from your shop or courier is.
        </p>
      </div>
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium">Note</span>
        <textarea
          name="note"
          rows={3}
          maxLength={2000}
          placeholder="For example: the customer told us on chat that a neighbour took the parcel."
          className="rounded-md border border-zinc-300 bg-white p-2 dark:border-zinc-700 dark:bg-zinc-950"
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium">File (PNG, JPG or PDF, up to 5 MB)</span>
        <input
          type="file"
          name="file"
          accept=".png,.jpg,.jpeg,.pdf,image/png,image/jpeg,application/pdf"
          className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-sm file:font-medium dark:file:bg-zinc-800"
        />
      </label>
      {error && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          {error}
        </p>
      )}
      <div>
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {busy ? "Adding…" : "Add to dispute"}
        </button>
      </div>
    </form>
  );
}
