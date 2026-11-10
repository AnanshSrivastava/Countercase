"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import { LearnedSuggestions } from "@/components/LearnedSuggestions";
import { EVIDENCE_LABEL } from "@/lib/format";
import type { Claim, EvidenceItem, LetterPreview, ProcessorStatus, Submission } from "@/lib/types";

interface Props {
  disputeId: string;
  apiUrl: string;
  memoryMode: "on" | "off";
  agentClaims: Claim[];
  agentLetter: string;
  initialClaims: Claim[];
  initialStatement: string;
  initialAttachIds: string[];
  evidence: EvidenceItem[];
  processor: ProcessorStatus;
  overdue: boolean;
}

type Outcome = { kind: "saved" } | { kind: "error"; message: string } | null;

export function DraftEditor(props: Props) {
  const { disputeId, apiUrl, memoryMode, agentClaims, agentLetter, evidence, processor, overdue } = props;
  const router = useRouter();
  const [, startTransition] = useTransition();
  const dialog = useRef<HTMLDialogElement>(null);

  const [claims, setClaims] = useState<Claim[]>(props.initialClaims);
  const [statement, setStatement] = useState(props.initialStatement);
  const [attachIds, setAttachIds] = useState<string[]>(props.initialAttachIds);

  const [preview, setPreview] = useState<(LetterPreview & { forKey: string }) | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome>(null);
  const [busy, setBusy] = useState<"save" | "approve" | null>(null);
  const [result, setResult] = useState<Submission | null>(null);

  const verified = useMemo(() => evidence.filter((e) => e.verified), [evidence]);
  const uploads = useMemo(() => evidence.filter((e) => e.type === "seller_upload"), [evidence]);
  const evidenceById = useMemo(() => new Map(evidence.map((e) => [e.id, e])), [evidence]);

  // Claims with no wording yet are still being written: leave them out of what the server sees.
  const sendable = useMemo(
    () => claims.map((c, i) => ({ c, i })).filter(({ c }) => c.text.trim() !== ""),
    [claims],
  );
  const request = useMemo(
    () => ({
      claims: sendable.map(({ c }) => ({ text: c.text.trim(), evidence_id: c.evidence_id })),
      seller_statement: statement.trim() || null,
      attach_upload_ids: attachIds,
      agent_claims: agentClaims,
    }),
    [sendable, statement, attachIds, agentClaims],
  );

  const requestKey = useMemo(() => JSON.stringify(request), [request]);

  // The server renders and validates; the browser only displays what it says. Debounced.
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`${apiUrl}/core/disputes/${encodeURIComponent(disputeId)}/letter-preview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request),
          signal: controller.signal,
        });
        const body = await res.json();
        if (!res.ok) {
          setPreview(null);
          setPreviewError(body.detail ?? "The letter could not be previewed.");
          return;
        }
        setPreviewError(null);
        setPreview({ ...(body as LetterPreview), forKey: requestKey });
      } catch (e) {
        if ((e as Error).name !== "AbortError") setPreviewError("Could not reach the API.");
      }
    }, 350);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [apiUrl, disputeId, request, requestKey]);

  // Map the server's blocked-claim indices (over sendable claims) back to editor rows.
  const blockedByRow = useMemo(() => {
    const map = new Map<number, string>();
    for (const b of preview?.blocked ?? []) {
      const row = sendable[b.index]?.i;
      if (row !== undefined) map.set(row, b.reason);
    }
    return map;
  }, [preview, sendable]);

  // Only a preview computed for exactly what is on screen can be approved.
  const fresh = preview !== null && !previewError && preview.forKey === requestKey;
  const canApprove =
    fresh && preview.blocked.length === 0 && sendable.length > 0 && busy === null && result === null;

  function update(i: number, patch: Partial<Claim>) {
    setClaims((prev) => prev.map((c, j) => (j === i ? { ...c, ...patch } : c)));
    setOutcome(null);
  }

  async function saveDraft() {
    setBusy("save");
    setOutcome(null);
    try {
      const res = await fetch(
        `${apiUrl}/core/disputes/${encodeURIComponent(disputeId)}/draft?memory_mode=${memoryMode}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...request, claims: claims.filter((c) => c.text.trim()) }),
        },
      );
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new Error(body?.detail ?? `Could not save (${res.status}).`);
      setOutcome({ kind: "saved" });
      startTransition(() => router.refresh());
    } catch (e) {
      setOutcome({ kind: "error", message: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function approve() {
    if (!preview) return;
    setBusy("approve");
    setOutcome(null);
    try {
      const res = await fetch(`${apiUrl}/core/disputes/${encodeURIComponent(disputeId)}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...request, approved: true, letter_sha256: preview.letter_sha256 }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        const stale = body?.error === "stale_review";
        throw new Error(stale ? "Something changed since you last looked. Review the letter again." : body?.detail ?? "Approval failed.");
      }
      dialog.current?.close();
      setResult(body as Submission); // the page is refreshed from the result card's button
    } catch (e) {
      dialog.current?.close();
      setOutcome({ kind: "error", message: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  if (result) {
    return (
      <ResultCard
        result={result}
        apiUrl={apiUrl}
        disputeId={disputeId}
        agentLetter={agentLetter}
        decision="fight"
        onDone={() => startTransition(() => router.refresh())}
      />
    );
  }

  const willSend = processor.can_submit && !overdue;

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="font-semibold">Your response</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Edit the wording freely. Every statement must point to a record from your shop, courier or
          Stripe; statements without one cannot be sent.
        </p>

        <ol className="mt-3 flex flex-col gap-3">
          {claims.map((claim, i) => {
            const blocked = blockedByRow.get(i);
            const source = evidenceById.get(claim.evidence_id);
            return (
              <li
                key={i}
                className={`rounded-md border p-3 ${
                  blocked
                    ? "border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40"
                    : "border-zinc-200 dark:border-zinc-700"
                }`}
              >
                <label className="flex flex-col gap-1 text-sm">
                  <span className="font-medium">Statement {i + 1}</span>
                  <textarea
                    value={claim.text}
                    onChange={(e) => update(i, { text: e.target.value })}
                    rows={2}
                    maxLength={1000}
                    className="rounded-md border border-zinc-300 bg-white p-2 dark:border-zinc-700 dark:bg-zinc-950"
                  />
                </label>
                <div className="mt-2 flex flex-wrap items-end gap-3">
                  <label className="flex min-w-0 flex-1 flex-col gap-1 text-sm">
                    <span className="text-zinc-600 dark:text-zinc-400">Backed by this record</span>
                    <select
                      value={claim.evidence_id}
                      onChange={(e) => update(i, { evidence_id: e.target.value })}
                      className="rounded-md border border-zinc-300 bg-white p-2 dark:border-zinc-700 dark:bg-zinc-950"
                    >
                      {!verified.some((e) => e.id === claim.evidence_id) && (
                        <option value={claim.evidence_id}>{claim.evidence_id} (not available)</option>
                      )}
                      {verified.map((e) => (
                        <option key={e.id} value={e.id}>
                          {EVIDENCE_LABEL[e.type]} · {e.id}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    onClick={() => setClaims((prev) => prev.filter((_, j) => j !== i))}
                    className="rounded-md border border-zinc-300 px-3 py-2 text-sm hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
                  >
                    Remove
                  </button>
                </div>
                {source && (
                  <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                    The record says: {source.summary}
                  </p>
                )}
                {blocked && (
                  <p role="alert" className="mt-2 text-sm font-medium text-red-700 dark:text-red-400">
                    Blocked: {blocked}.
                  </p>
                )}
              </li>
            );
          })}
        </ol>

        <button
          type="button"
          disabled={verified.length === 0}
          onClick={() =>
            setClaims((prev) => [...prev, { text: "", evidence_id: verified[0]?.id ?? "" }])
          }
          className="mt-3 rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 disabled:opacity-40 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          Add a statement
        </button>
        {verified.length === 0 && (
          <p className="mt-2 text-sm text-zinc-500">
            There is no verified record to cite yet, so there is nothing to send. Evidence is collected
            automatically when the order can be matched.
          </p>
        )}
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-semibold">Your own statement (optional)</span>
          <span className="text-zinc-600 dark:text-zinc-400">
            In your own words. It appears in the letter under a heading that says it is the
            seller&apos;s statement and not verified evidence.
          </span>
          <textarea
            value={statement}
            onChange={(e) => {
              setStatement(e.target.value);
              setOutcome(null);
            }}
            rows={3}
            maxLength={2000}
            className="mt-1 rounded-md border border-zinc-300 bg-white p-2 dark:border-zinc-700 dark:bg-zinc-950"
          />
        </label>

        <fieldset className="mt-4">
          <legend className="text-sm font-semibold">Attach your files</legend>
          {uploads.length === 0 ? (
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              No uploads. Add files on the Evidence tab; they are only attached if you tick them here.
              Your notes are private and are never sent.
            </p>
          ) : (
            <ul className="mt-1 flex flex-col gap-1 text-sm">
              {uploads.map((u) => (
                <li key={u.id}>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={attachIds.includes(u.id)}
                      onChange={(e) =>
                        setAttachIds((prev) =>
                          e.target.checked ? [...prev, u.id] : prev.filter((x) => x !== u.id),
                        )
                      }
                    />
                    {u.summary.replace("Seller upload: ", "")}
                    <span className="text-xs text-zinc-500">attached as seller-provided, not verified</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </fieldset>
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="font-semibold">Letter preview</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          This is exactly what will be sent, rendered by the server.
        </p>
        {previewError ? (
          <p role="alert" className="mt-2 text-sm text-red-700 dark:text-red-400">
            {previewError}
          </p>
        ) : preview?.letter_md ? (
          <pre className="mt-2 whitespace-pre-wrap rounded-md bg-zinc-50 p-3 font-sans text-sm leading-6 dark:bg-zinc-950">
            {preview.letter_md}
          </pre>
        ) : (
          <p className="mt-2 text-sm text-zinc-500">
            {sendable.length === 0 ? "Add at least one statement to see the letter." : "Rendering…"}
          </p>
        )}
        {preview && preview.attachments.length > 0 && (
          <p className="mt-2 text-sm">Attached files: {preview.attachments.join(", ")}.</p>
        )}
        {preview && preview.blocked.length > 0 && (
          <p role="alert" className="mt-2 rounded-md bg-red-50 p-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
            {preview.blocked.length} statement{preview.blocked.length > 1 ? "s have" : " has"} no verified
            source. Approval is blocked until they are fixed or removed.
          </p>
        )}
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={saveDraft}
          disabled={busy !== null}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          {busy === "save" ? "Saving…" : "Save draft"}
        </button>
        <button
          type="button"
          disabled={!canApprove}
          onClick={() => dialog.current?.showModal()}
          className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
        >
          Review and approve
        </button>
        {outcome?.kind === "saved" && (
          <span role="status" className="text-sm text-emerald-700 dark:text-emerald-400">
            Draft saved.
          </span>
        )}
        {outcome?.kind === "error" && (
          <span role="alert" className="text-sm text-red-700 dark:text-red-400">
            {outcome.message}
          </span>
        )}
      </div>

      <dialog
        ref={dialog}
        aria-labelledby="approve-title"
        className="m-auto max-w-lg rounded-lg border border-zinc-300 bg-white p-5 text-zinc-900 backdrop:bg-black/50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
      >
        <h2 id="approve-title" className="text-lg font-semibold">
          Approve this response?
        </h2>
        <p className="mt-2 text-sm">
          {willSend
            ? "It will be sent to Stripe (test mode) as your response to this dispute. After that it cannot be changed."
            : overdue
              ? "The deadline has passed, so nothing will be sent. A PDF will be created for you to upload yourself if the processor still accepts it."
              : `Nothing will be sent automatically (${processor.reason ?? "no processor available"}). A PDF will be created for you to upload yourself.`}
        </p>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          {sendable.length} statement{sendable.length === 1 ? "" : "s"}, each backed by a verified record
          {attachIds.length > 0 ? `, and ${attachIds.length} of your file${attachIds.length > 1 ? "s" : ""}` : ""}.
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
            onClick={approve}
            disabled={busy !== null}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {busy === "approve" ? "Working…" : willSend ? "Approve and send" : "Approve and create PDF"}
          </button>
        </div>
      </dialog>
    </div>
  );
}

function ResultCard({
  result,
  apiUrl,
  disputeId,
  agentLetter,
  decision,
  onDone,
}: {
  result: Submission;
  apiUrl: string;
  disputeId: string;
  agentLetter: string;
  decision: "fight";
  onDone: () => void;
}) {
  const heading = {
    submitted: "Sent to the processor",
    exported: "Approved: PDF created, not sent",
    failed: "Approved, but sending failed",
    pending: "Sending…",
  }[result.status];
  return (
    <div className="flex flex-col gap-4">
      <section
        className={`rounded-lg border p-4 ${
          result.status === "failed"
            ? "border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40"
            : "border-emerald-300 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950/40"
        }`}
        role="status"
      >
        <h2 className="font-semibold">{heading}</h2>
        {result.note && <p className="mt-1 text-sm">{result.note}</p>}
        {result.error && <p className="mt-1 font-mono text-xs">{result.error}</p>}
        {result.pdf_uri && (
          <a
            href={`${apiUrl}/core/submissions/${result.id}/pdf`}
            className="mt-2 inline-block text-sm font-medium text-sky-700 hover:underline dark:text-sky-400"
          >
            Download the PDF packet
          </a>
        )}
        {result.status === "failed" && (
          <p className="mt-2 text-sm">Your approval is saved. Reload this page to try again.</p>
        )}
      </section>
      <LearnedSuggestions
        apiUrl={apiUrl}
        disputeId={disputeId}
        before={agentLetter}
        after={result.letter_md}
        decision={decision}
      />
      <div>
        <button
          type="button"
          onClick={onDone}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          Done
        </button>
      </div>
    </div>
  );
}
