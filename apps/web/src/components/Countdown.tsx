"use client";

import { useSyncExternalStore } from "react";

// One shared 1-second clock for every countdown on the page.
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | undefined;

function subscribe(listener: () => void) {
  listeners.add(listener);
  timer ??= setInterval(() => listeners.forEach((l) => l()), 1000);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

const nowSeconds = () => Math.floor(Date.now() / 1000);
const serverSnapshot = () => null;

/** One shared 1-second clock; null until the client has mounted (avoids hydration mismatches). */
export function useNowSeconds(): number | null {
  return useSyncExternalStore(subscribe, nowSeconds, serverSnapshot);
}

export type Urgency = "overdue" | "critical" | "urgent" | "soon" | "ok";

/** PRD F1 alert thresholds: 72h, 24h, 6h before the deadline. */
export function urgency(msLeft: number): Urgency {
  const h = msLeft / 3_600_000;
  if (h <= 0) return "overdue";
  if (h <= 6) return "critical";
  if (h <= 24) return "urgent";
  if (h <= 72) return "soon";
  return "ok";
}

const STYLE: Record<Urgency, string> = {
  overdue: "bg-red-700 text-white dark:bg-red-600",
  critical: "bg-red-100 text-red-800 ring-1 ring-red-300 dark:bg-red-950 dark:text-red-200 dark:ring-red-800",
  urgent: "bg-orange-100 text-orange-800 ring-1 ring-orange-300 dark:bg-orange-950 dark:text-orange-200 dark:ring-orange-800",
  soon: "bg-amber-50 text-amber-800 ring-1 ring-amber-200 dark:bg-amber-950 dark:text-amber-200 dark:ring-amber-900",
  ok: "bg-zinc-100 text-zinc-700 ring-1 ring-zinc-200 dark:bg-zinc-800 dark:text-zinc-200 dark:ring-zinc-700",
};

export function formatRemaining(totalSeconds: number): string {
  const s = Math.abs(totalSeconds);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const text = d > 0 ? `${d}d ${h}h ${m}m` : h > 0 ? `${h}h ${m}m ${sec}s` : `${m}m ${sec}s`;
  return totalSeconds < 0 ? `overdue by ${text}` : `${text} left`;
}

export function Countdown({ deadline, open = true }: { deadline: string; open?: boolean }) {
  const now = useNowSeconds();
  const deadlineSec = Math.floor(Date.parse(deadline) / 1000);

  if (!open) {
    return <span className="text-sm text-zinc-500 dark:text-zinc-400">Closed</span>;
  }
  if (now === null) {
    // Server render / first paint: no clock yet, avoid a hydration mismatch.
    return <span className="inline-block h-6 w-28 rounded-full bg-zinc-100 dark:bg-zinc-800" aria-hidden />;
  }
  const left = deadlineSec - now;
  const level = urgency(left * 1000);
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium tabular-nums ${STYLE[level]}`}
      title={`Deadline ${new Date(deadline).toUTCString()}`}
    >
      {formatRemaining(left)}
    </span>
  );
}
