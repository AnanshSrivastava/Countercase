import { MemoryTab } from "@/features/memory/MemoryTab";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { AcceptPanel } from "@/components/AcceptPanel";
import { Checklist } from "@/components/Checklist";
import { Countdown } from "@/components/Countdown";
import { LearnedFromOutcome } from "@/components/LearnedFromOutcome";
import { SimulateOutcome } from "@/components/SimulateOutcome";
import { DeadlineBanner } from "@/components/DeadlineBanner";
import { DraftEditor } from "@/components/DraftEditor";
import { AdviceCard, CostLine, DraftView, MemoryToggle } from "@/components/DraftView";
import { ErrorPanel } from "@/components/ErrorPanel";
import { EvidenceList } from "@/components/EvidenceList";
import { EvidenceUpload } from "@/components/EvidenceUpload";
import { StatusBadge } from "@/components/StatusBadge";
import { SubmissionCard } from "@/components/SubmissionCard";
import {
  getChecklist,
  getDispute,
  getDraft,
  getProcessorStatus,
  getSavedDraft,
  getSubmission,
  isOlderThanMinutes,
  isPastDeadline,
  useFixtures,
} from "@/lib/data";
import { CATEGORY_LABEL, dateTime, isOpen, money } from "@/lib/format";
import type { DisputeDetail } from "@/lib/types";

const TABS = ["evidence", "draft", "memory"] as const;
type Tab = (typeof TABS)[number];

export default function DisputePage({ params, searchParams }: PageProps<"/disputes/[id]">) {
  return (
    <div className="flex flex-col gap-6">
      <Link href="/" className="text-sm text-zinc-600 hover:underline dark:text-zinc-400">
        ← Inbox
      </Link>
      <Suspense fallback={<div className="h-40 animate-pulse rounded-lg bg-zinc-200/70 dark:bg-zinc-800" />}>
        <DisputeContent params={params} searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function DisputeContent({
  params,
  searchParams,
}: Pick<PageProps<"/disputes/[id]">, "params" | "searchParams">) {
  const { id } = await params;
  const sp = await searchParams;
  const tab: Tab = TABS.includes(sp.tab as Tab) ? (sp.tab as Tab) : "evidence";
  const memory = sp.memory === "off" ? "off" : "on";
  const fight = sp.fight === "1";

  let detail: DisputeDetail | null;
  try {
    detail = await getDispute(id);
  } catch (e) {
    return <ErrorPanel title="Could not load dispute" error={e} />;
  }
  if (!detail) notFound();
  const { dispute } = detail;

  return (
    <>
      <header className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tabular-nums">{money(dispute.amount, dispute.currency)}</h1>
          <StatusBadge status={dispute.status} />
          <Countdown deadline={dispute.deadline_at} open={isOpen(dispute.status)} />
        </div>
        <div>
          <p className="font-medium">{dispute.category ? CATEGORY_LABEL[dispute.category] : "Unclassified"}</p>
          {dispute.category_explanation && (
            <p className="text-sm text-zinc-600 dark:text-zinc-400">{dispute.category_explanation}</p>
          )}
        </div>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm sm:grid-cols-[max-content_1fr_max-content_1fr]">
          <Field label="Deadline" value={dateTime(dispute.deadline_at)} />
          <Field label="Opened" value={dateTime(dispute.created_at)} />
          <Field label="Customer" value={dispute.customer_hash} mono />
          <Field label="Order" value={dispute.order_id ?? "—"} mono />
          <Field label="Product" value={dispute.product_sku ?? "—"} mono />
          <Field label="Courier" value={dispute.courier ?? "—"} />
          <Field label="Processor" value={`${dispute.processor} · ${dispute.reason_raw}`} />
          <Field label="Processor id" value={dispute.processor_dispute_id} mono />
        </dl>
      </header>

      <DeadlineBanner deadline={dispute.deadline_at} status={dispute.status} />

      <nav className="flex gap-1 border-b border-zinc-200 dark:border-zinc-800" aria-label="Dispute sections">
        {TABS.map((t) => (
          <Link
            key={t}
            href={{ query: { tab: t, ...(t === "draft" ? { memory } : {}) } }}
            aria-current={t === tab ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium capitalize ${
              t === tab
                ? "border-zinc-900 text-zinc-900 dark:border-zinc-100 dark:text-zinc-100"
                : "border-transparent text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200"
            }`}
          >
            {t}
          </Link>
        ))}
      </nav>

      {tab === "evidence" && <EvidenceTab detail={detail} />}
      {tab === "draft" && (
        <Suspense fallback={<p className="text-sm text-zinc-500">Drafting…</p>}>
          <DraftTab id={dispute.id} memory={memory} fight={fight} detail={detail} />
        </Suspense>
      )}
      {tab === "memory" && (
        <Suspense fallback={<p className="text-sm text-zinc-500">Loading memory…</p>}>
          <MemoryTab disputeId={dispute.id} />
        </Suspense>
      )}
    </>
  );
}

const PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function EvidenceTab({ detail }: { detail: DisputeDetail }) {
  const { dispute, evidence } = detail;
  // Rules-only route: no model, no memory, safe on every page view.
  let checklist = null;
  try {
    checklist = await getChecklist(dispute.id);
  } catch {
    // The evidence list is still useful without the checklist.
  }
  return (
    <div className="flex flex-col gap-5">
      {checklist && <Checklist rows={checklist} />}
      <EvidenceList evidence={evidence} apiUrl={PUBLIC_API_URL} />
      {useFixtures ? (
        <p className="rounded-lg border border-dashed border-zinc-300 p-4 text-sm text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
          Adding notes and files needs the live API. Fixture mode is read-only.
        </p>
      ) : (
        <EvidenceUpload disputeId={dispute.id} apiUrl={PUBLIC_API_URL} />
      )}
    </div>
  );
}

async function DraftTab({
  id,
  memory,
  fight,
  detail,
}: {
  id: string;
  memory: "on" | "off";
  fight: boolean;
  detail: DisputeDetail;
}) {
  const { dispute, evidence } = detail;
  let draft, saved, submission, processor;
  try {
    [draft, saved, submission, processor] = await Promise.all([
      getDraft(id, memory),
      getSavedDraft(id),
      getSubmission(id),
      getProcessorStatus(),
    ]);
  } catch (e) {
    return <ErrorPanel title="Could not build draft" error={e} />;
  }

  // Fixture mode has no API behind it: show the read-only draft.
  if (useFixtures) return <DraftView draft={draft} evidence={evidence} memory={memory} />;

  if (dispute.status === "accepted") {
    return (
      <p className="rounded-lg border border-zinc-200 bg-white p-4 text-sm dark:border-zinc-800 dark:bg-zinc-900">
        You accepted this dispute in Recoup. If it has not been closed with your processor yet, close it
        in your processor dashboard.
      </p>
    );
  }
  const closed = ["won", "lost"].includes(dispute.status);
  // A pending submission older than the API's 10-minute grace was interrupted: allow another try.
  const stalePending =
    submission?.status === "pending" && (await isOlderThanMinutes(submission.approved_at, 10));
  const retryable =
    !closed &&
    dispute.status !== "submitted" &&
    (!submission || submission.status === "exported" || submission.status === "failed" || stalePending);

  if (closed) {
    // A result is in: show the response (if any) and what the agent learned from it.
    return (
      <div className="flex flex-col gap-4">
        {submission && <SubmissionCard submission={submission} apiUrl={PUBLIC_API_URL} />}
        <LearnedFromOutcome disputeId={dispute.id} />
      </div>
    );
  }
  if (submission && !retryable) {
    return (
      <div className="flex flex-col gap-4">
        <SubmissionCard submission={submission} apiUrl={PUBLIC_API_URL} />
        {processor.demo_tools && <SimulateOutcome disputeId={dispute.id} apiUrl={PUBLIC_API_URL} />}
      </div>
    );
  }
  if (!draft) {
    return (
      <p className="rounded-lg border border-dashed border-zinc-300 p-6 text-sm text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
        No draft available for this dispute yet.
      </p>
    );
  }

  const acceptAdvised = draft.advice.action === "accept" && draft.letter_md === "" && !fight;
  const overdue = await isPastDeadline(dispute.deadline_at);

  return (
    <div className="flex flex-col gap-4">
      {submission && <SubmissionCard submission={submission} apiUrl={PUBLIC_API_URL} />}
      {submission && processor.demo_tools && dispute.status === "approved" && (
        <SimulateOutcome disputeId={dispute.id} apiUrl={PUBLIC_API_URL} />
      )}
      <MemoryToggle memory={memory} />
      <AdviceCard draft={draft} />
      {acceptAdvised ? (
        <AcceptPanel
          disputeId={dispute.id}
          apiUrl={PUBLIC_API_URL}
          rationale={draft.advice.rationale}
          processor={processor}
        />
      ) : (
        <>
          <Checklist rows={draft.checklist} />
          <DraftEditor
            key={`${memory}-${fight}-${submission?.id ?? "new"}`}
            disputeId={dispute.id}
            apiUrl={PUBLIC_API_URL}
            memoryMode={memory}
            agentClaims={draft.claims}
            agentLetter={draft.letter_md}
            initialClaims={saved?.claims ?? draft.claims}
            initialStatement={saved?.seller_statement ?? ""}
            initialAttachIds={saved?.attach_upload_ids ?? []}
            evidence={evidence}
            processor={processor}
            overdue={overdue}
          />
        </>
      )}
      <CostLine draft={draft} />
    </div>
  );
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <>
      <dt className="text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className={`min-w-0 truncate ${mono ? "font-mono text-xs leading-5" : ""}`}>{value}</dd>
    </>
  );
}
