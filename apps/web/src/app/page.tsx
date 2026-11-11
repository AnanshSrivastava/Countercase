import Link from "next/link";
import { Suspense } from "react";
import { DisputesGrid } from "@/components/DisputesGrid";
import { ErrorPanel } from "@/components/ErrorPanel";
import { InboxSummary } from "@/components/InboxSummary";
import { getDisputes } from "@/lib/data";
import { isOpen } from "@/lib/format";

export default function InboxPage({ searchParams }: PageProps<"/">) {
  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-blue-700 dark:text-blue-300">Seller workspace</p>
          <h1 className="text-3xl font-semibold tracking-tight text-zinc-950 dark:text-white">Dispute inbox</h1>
          <p className="mt-1.5 max-w-xl text-sm text-zinc-600 dark:text-zinc-400">Your cases, deadlines, and next steps—organized so you can act with confidence.</p>
        </div>
        <div className="hidden items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-800 sm:flex dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-200">
          <span className="h-2 w-2 rounded-full bg-emerald-500" /> All systems operational
        </div>
      </div>
      <Suspense fallback={<InboxSkeleton />}>
        <InboxTable searchParams={searchParams} />
      </Suspense>
    </section>
  );
}

function InboxSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading disputes">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((item) => <div key={item} className="h-24 animate-pulse rounded-xl bg-zinc-200/70 dark:bg-zinc-800" />)}
      </div>
      <div className="h-[540px] animate-pulse rounded-xl bg-zinc-200/70 dark:bg-zinc-800" />
    </div>
  );
}

async function InboxTable({ searchParams }: Pick<PageProps<"/">, "searchParams">) {
  const showClosed = (await searchParams).show === "closed";
  let disputes;
  try {
    disputes = await getDisputes();
  } catch (e) {
    return <ErrorPanel title="Could not load disputes" error={e} />;
  }

  if (disputes.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
        No disputes yet. They appear here as soon as Stripe sends a <code>charge.dispute.created</code> webhook.
      </div>
    );
  }

  // Open disputes (deadline matters) first, then closed ones; each group by deadline.
  const openCount = disputes.filter((d) => isOpen(d.status)).length;
  const closedCount = disputes.length - openCount;
  const visible = showClosed ? disputes : disputes.filter((d) => isOpen(d.status));
  const sorted = [...visible].sort(
    (a, b) => Number(isOpen(b.status)) - Number(isOpen(a.status)) || Date.parse(a.deadline_at) - Date.parse(b.deadline_at),
  );

  return (
    <div className="flex flex-col gap-3">
    <InboxSummary disputes={disputes} />
    {openCount === 0 && !showClosed ? (
      <p className="rounded-xl border border-dashed border-zinc-300 bg-white p-8 text-center text-sm text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400">Nothing is waiting on you.</p>
    ) : <DisputesGrid disputes={sorted} />}
    {closedCount > 0 && (
      <Link
        href={showClosed ? "/" : { query: { show: "closed" } }}
        className="self-start text-sm text-sky-700 hover:underline dark:text-sky-400"
      >
        {showClosed ? "Hide closed disputes" : `Show ${closedCount} closed disputes`}
      </Link>
    )}
    </div>
  );
}
