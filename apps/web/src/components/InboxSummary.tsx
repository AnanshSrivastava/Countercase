"use client";

import { useNowSeconds } from "@/components/Countdown";
import { isOpen } from "@/lib/format";
import type { Dispute } from "@/lib/types";

export function InboxSummary({ disputes }: { disputes: Dispute[] }) {
  const now = useNowSeconds();
  const open = disputes.filter((dispute) => isOpen(dispute.status));
  const dueSoon = now === null ? null : open.filter((dispute) => Date.parse(dispute.deadline_at) - now * 1000 <= 24 * 60 * 60 * 1000).length;
  const drafts = open.filter((dispute) => dispute.status !== "needs_response").length;

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <SummaryCard label="Open cases" value={String(open.length)} hint="Need your attention" accent="blue" />
      <SummaryCard label="Due within 24 hours" value={dueSoon === null ? "—" : String(dueSoon)} hint={dueSoon ? "Prioritize these responses" : "No immediate deadlines"} accent={dueSoon ? "amber" : "zinc"} />
      <SummaryCard label="Drafts ready" value={String(drafts)} hint="Ready for your review" accent="emerald" />
    </div>
  );
}

function SummaryCard({ label, value, hint, accent }: { label: string; value: string; hint: string; accent: "blue" | "amber" | "emerald" | "zinc" }) {
  const dot: Record<typeof accent, string> = {
    blue: "bg-blue-600",
    amber: "bg-amber-500",
    emerald: "bg-emerald-500",
    zinc: "bg-zinc-400",
  };
  return (
    <div className="rounded-xl border border-zinc-200 bg-white px-4 py-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center gap-2 text-xs font-medium text-zinc-500 dark:text-zinc-400"><span className={`h-2 w-2 rounded-full ${dot[accent]}`} />{label}</div>
      <div className="mt-2 flex items-baseline justify-between gap-3">
        <span className="text-3xl font-semibold tracking-tight tabular-nums text-zinc-950 dark:text-white">{value}</span>
        <span className="text-right text-xs text-zinc-500 dark:text-zinc-400">{hint}</span>
      </div>
    </div>
  );
}
