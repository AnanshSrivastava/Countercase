import Link from "next/link";
import { Suspense } from "react";

import { Countdown } from "@/components/Countdown";
import { ErrorPanel } from "@/components/ErrorPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { getDisputes } from "@/lib/data";
import { CATEGORY_LABEL, isOpen, money } from "@/lib/format";

export default function InboxPage({ searchParams }: PageProps<"/">) {
  return (
    <section className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dispute inbox</h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Open disputes first, ordered by deadline. Badges turn amber at 72h, orange at 24h and red at 6h.
        </p>
      </div>
      <Suspense fallback={<InboxSkeleton />}>
        <InboxTable searchParams={searchParams} />
      </Suspense>
    </section>
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
    {openCount === 0 && !showClosed && (
      <p className="rounded-lg border border-dashed border-zinc-300 p-6 text-center text-sm text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
        Nothing is waiting on you.
      </p>
    )}
    <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
        {sorted.map((d) => (
          <li key={d.id}>
            <Link
              href={`/disputes/${d.id}`}
              className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 px-4 py-3 hover:bg-zinc-50 sm:grid-cols-[7rem_1fr_9rem_10rem] sm:items-center dark:hover:bg-zinc-800/50"
            >
              <span className="font-semibold tabular-nums">{money(d.amount, d.currency)}</span>
              <span className="min-w-0 sm:order-none">
                <span className="block truncate font-medium">
                  {d.category ? CATEGORY_LABEL[d.category] : "Unclassified"}
                </span>
                <span className="block truncate text-xs text-zinc-500 dark:text-zinc-400">
                  {d.category_explanation ?? d.reason_raw} · customer {d.customer_hash.slice(0, 10)}
                  {d.order_id ? ` · ${d.order_id}` : ""}
                </span>
              </span>
              <span>
                <StatusBadge status={d.status} />
              </span>
              <span className="sm:text-right">
                <Countdown deadline={d.deadline_at} open={isOpen(d.status)} />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
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

function InboxSkeleton() {
  return (
    <div className="flex flex-col gap-2" aria-busy>
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-14 animate-pulse rounded-lg bg-zinc-200/70 dark:bg-zinc-800" />
      ))}
    </div>
  );
}
