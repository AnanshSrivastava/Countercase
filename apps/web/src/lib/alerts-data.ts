// Server-side access to deadline alerts (docs/CONTRACTS.md Alert, v0.5). Server components only.
import { connection } from "next/server";

const API_URL = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const useFixtures = process.env.NEXT_PUBLIC_USE_FIXTURES === "1";

export interface Alert {
  id: string;
  dispute_id: string;
  threshold_hours: 72 | 24 | 6;
  channel: "email" | "simulated";
  status: "sent" | "failed" | "superseded";
  subject: string;
  body: string;
  to_address: string | null;
  error: string | null;
  sent_at: string | null;
}

export async function getAlerts(): Promise<{ alerts: Alert[]; unavailable?: string }> {
  await connection();
  if (useFixtures) return { alerts: [], unavailable: "Alerts need the live API (fixture mode is on)." };
  try {
    const res = await fetch(`${API_URL}/core/alerts`, { cache: "no-store" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return { alerts: (await res.json()) as Alert[] };
  } catch (e) {
    return { alerts: [], unavailable: e instanceof Error ? e.message : "API unreachable" };
  }
}

export async function runAlertCheck(): Promise<void> {
  const res = await fetch(`${API_URL}/core/alerts/run`, { method: "POST", cache: "no-store" });
  if (!res.ok) throw new Error(`alert check failed: ${res.status}`);
}
