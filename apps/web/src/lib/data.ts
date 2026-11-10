// Server-side data access. Reads the API, or fixtures/ when NEXT_PUBLIC_USE_FIXTURES=1.
// Only import from server components: it uses node:fs.

import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { connection } from "next/server";

import type { ChecklistRow, DisputeDetail, Draft, ProcessorStatus, SavedDraft, Submission } from "./types";

export const useFixtures = process.env.NEXT_PUBLIC_USE_FIXTURES === "1";

// Inside docker the API is reachable as http://api:8000, not localhost.
const API_URL = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const FIXTURES_DIR = process.env.FIXTURES_DIR ?? path.join(process.cwd(), "..", "..", "fixtures");

// Fixture deadlines are fixed dates in the past. In fixture mode, shift every dispute by the same
// offset so the earliest deadline is ~20h away; relative gaps (and the colour mix) are preserved.
const FIXTURE_FIRST_DEADLINE_MS = 20 * 3600 * 1000;

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    detail: string,
  ) {
    super(detail);
  }
}

async function api<T>(pathname: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${pathname}`, { cache: "no-store", ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: "http_error", detail: res.statusText }));
    throw new ApiError(res.status, body.error ?? "http_error", body.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

async function readFixtureDisputes(): Promise<DisputeDetail[]> {
  const dir = path.join(FIXTURES_DIR, "disputes");
  const files = (await readdir(dir)).filter((f) => f.endsWith(".json")).sort();
  const details = await Promise.all(
    files.map(async (f) => JSON.parse(await readFile(path.join(dir, f), "utf-8")) as DisputeDetail),
  );
  const earliest = Math.min(...details.map((d) => Date.parse(d.dispute.deadline_at)));
  const offset = Date.now() + FIXTURE_FIRST_DEADLINE_MS - earliest;
  const shift = (iso: string) => new Date(Date.parse(iso) + offset).toISOString();
  return details.map(({ dispute, evidence }) => ({
    dispute: { ...dispute, created_at: shift(dispute.created_at), deadline_at: shift(dispute.deadline_at) },
    evidence,
  }));
}

export async function getDisputes(): Promise<DisputeDetail["dispute"][]> {
  await connection(); // per-request data: never prerender
  if (useFixtures) {
    const all = await readFixtureDisputes();
    return all
      .map((d) => d.dispute)
      .sort((a, b) => Date.parse(a.deadline_at) - Date.parse(b.deadline_at));
  }
  return api("/core/disputes");
}

export async function getDispute(id: string): Promise<DisputeDetail | null> {
  await connection();
  if (useFixtures) {
    return (await readFixtureDisputes()).find((d) => d.dispute.id === id) ?? null;
  }
  try {
    return await api<DisputeDetail>(`/core/disputes/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function getDraft(id: string, memory: "on" | "off"): Promise<Draft | null> {
  await connection();
  if (useFixtures) {
    const file = path.join(FIXTURES_DIR, "drafts", `${id}_memory_${memory}.json`);
    try {
      return JSON.parse(await readFile(file, "utf-8")) as Draft;
    } catch {
      return null; // only some disputes have fixture drafts
    }
  }
  try {
    return await api<Draft>(`/agent/disputes/${encodeURIComponent(id)}/draft?memory=${memory}`, {
      method: "POST",
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

/** Rules-only checklist (no model, no memory): cheap enough for every page view. */
export async function getChecklist(id: string): Promise<ChecklistRow[] | null> {
  await connection();
  if (useFixtures) return (await getDraft(id, "off"))?.checklist ?? null;
  try {
    const body = await api<{ checklist: ChecklistRow[] }>(`/agent/disputes/${encodeURIComponent(id)}/checklist`);
    return body.checklist;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function getSavedDraft(id: string): Promise<SavedDraft | null> {
  await connection();
  if (useFixtures) return null;
  try {
    return await api<SavedDraft>(`/core/disputes/${encodeURIComponent(id)}/draft`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function getSubmission(id: string): Promise<Submission | null> {
  await connection();
  if (useFixtures) return null;
  try {
    return await api<Submission>(`/core/disputes/${encodeURIComponent(id)}/submission`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function getProcessorStatus(): Promise<ProcessorStatus> {
  await connection();
  if (useFixtures) return { can_submit: false, reason: "fixture mode is read-only" };
  return api<ProcessorStatus>("/core/processor-status");
}

/** Whether a deadline has already passed, read per request (not at build time). */
export async function isPastDeadline(deadlineIso: string): Promise<boolean> {
  await connection();
  return Date.parse(deadlineIso) <= Date.now();
}

/** Matches the API's rule: a `pending` submission younger than 10 minutes may still be running. */
export async function isOlderThanMinutes(iso: string, minutes: number): Promise<boolean> {
  await connection();
  return Date.now() - Date.parse(iso) > minutes * 60_000;
}
