import { STATUS_LABEL } from "@/lib/format";
import type { DisputeStatus } from "@/lib/types";

const STYLE: Record<DisputeStatus, string> = {
  needs_response: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200",
  drafted: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200",
  approved: "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-200",
  submitted: "bg-zinc-200 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200",
  won: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  lost: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
  accepted: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
};

export function StatusBadge({ status }: { status: DisputeStatus }) {
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STYLE[status]}`}>
      {STATUS_LABEL[status]}
    </span>
  );
}
