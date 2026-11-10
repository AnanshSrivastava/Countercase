// Server-side data access for the memory screens (owner: Shivansh). Server components only.
// Fixture mode (NEXT_PUBLIC_USE_FIXTURES=1) serves fixtures/memory/*.json for the Inspector; beliefs and
// the Playbook need the live agent and show an explanatory empty state in fixture mode.

import { readFile } from "node:fs/promises";
import path from "node:path";
import { connection } from "next/server";

import type { Belief, BeliefChange, MemoryRef, Playbook } from "./types";

const useFixtures = process.env.NEXT_PUBLIC_USE_FIXTURES === "1";
const API_URL = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const FIXTURES_DIR = process.env.FIXTURES_DIR ?? path.join(process.cwd(), "..", "..", "fixtures");

export const SELLER_ID = "sel_demo"; // single demo seller until auth exists

async function agent<T>(pathname: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}/agent${pathname}`, { cache: "no-store", ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export interface MemoryData<T> {
  data: T;
  unavailable?: string; // set when the data could not be loaded (shown instead of crashing the page)
}

async function safe<T>(fallback: T, load: () => Promise<T>): Promise<MemoryData<T>> {
  try {
    return { data: await load() };
  } catch (e) {
    return { data: fallback, unavailable: e instanceof Error ? e.message : "agent unreachable" };
  }
}

/** Memories recalled for this dispute (used and considered-but-not-used). */
export async function getDisputeMemory(disputeId: string): Promise<MemoryData<MemoryRef[]>> {
  await connection();
  if (useFixtures) {
    return safe([], async () =>
      JSON.parse(await readFile(path.join(FIXTURES_DIR, "memory", `${disputeId}_memory.json`), "utf-8")),
    );
  }
  return safe([], () => agent<MemoryRef[]>(`/memory?dispute_id=${encodeURIComponent(disputeId)}`));
}

export async function getBeliefs(): Promise<MemoryData<Belief[]>> {
  await connection();
  if (useFixtures) return { data: [], unavailable: "Beliefs need the live agent (fixture mode is on)." };
  return safe([], () => agent<Belief[]>(`/beliefs?seller_id=${SELLER_ID}`));
}

export async function getBeliefChanges(): Promise<MemoryData<BeliefChange[]>> {
  await connection();
  if (useFixtures) return { data: [] };
  return safe([], () => agent<BeliefChange[]>("/beliefs/changes"));
}

export async function getPlaybook(): Promise<MemoryData<Playbook | null>> {
  await connection();
  if (useFixtures) return { data: null, unavailable: "The Playbook needs the live agent (fixture mode is on)." };
  return safe<Playbook | null>(null, () => agent<Playbook>(`/playbook?seller_id=${SELLER_ID}`));
}

export async function agentMutation(pathname: string, method: "DELETE" | "POST", body?: unknown): Promise<void> {
  await agent(pathname, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
}
