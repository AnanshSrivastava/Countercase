"use client";

import { formatRemaining, urgency, useNowSeconds } from "@/components/Countdown";
import type { DisputeStatus } from "@/lib/types";

const STYLE = {
  overdue: "border-red-700 bg-red-700 text-white",
  critical: "border-red-300 bg-red-100 text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100",
  urgent: "border-orange-300 bg-orange-100 text-orange-900 dark:border-orange-800 dark:bg-orange-950 dark:text-orange-100",
  soon: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100",
} as const;

const WHAT: Partial<Record<DisputeStatus, string>> = {
  needs_response: "No response has been started.",
  drafted: "Your draft is saved but not approved.",
  approved: "Your response is approved but was not sent to the processor.",
};

/** Escalating reminder (IMPROVEMENTS #19): quiet until 72h before the deadline, then louder. */
export function DeadlineBanner({ deadline, status }: { deadline: string; status: DisputeStatus }) {
  const now = useNowSeconds();
  const what = WHAT[status];
  if (now === null || !what) return null;

  const left = Math.floor(Date.parse(deadline) / 1000) - now;
  const level = urgency(left * 1000);
  if (level === "ok") return null;

  return (
    <div
      role={level === "soon" ? "status" : "alert"}
      className={`rounded-lg border px-4 py-3 text-sm font-medium ${STYLE[level]}`}
    >
      {what}{" "}
      {level === "overdue"
        ? `The deadline has passed (${formatRemaining(left)}).`
        : `${formatRemaining(left)} until the deadline.`}
    </div>
  );
}
