// Shapes returned by the agent routes (docs/CONTRACTS.md MemoryRef + STATUS.md belief/playbook routes).

export type MemoryKind =
  | "case"
  | "belief"
  | "directive"
  | "mental_model"
  | "pattern"
  | "customer_history"
  | "opinion";

export interface MemoryRef {
  id: string;
  kind: MemoryKind;
  text: string;
  confidence: number; // 0..1
  n_supporting: number;
  event_date: string | null;
  used: boolean;
  why: string;
  editable: boolean;
}

export type BeliefLabel = "weak" | "moderate" | "strong";

export interface Belief {
  key: string;
  text: string;
  confidence: number;
  n: number;
  label: BeliefLabel;
  kind: "evidence" | "courier";
}

export interface BeliefChange {
  key: string;
  text: string;
  before: number | null;
  after: number | null;
  label: string;
  status: "formed" | "updated" | "dropped";
  at?: string;
  dispute_id?: string;
}

export interface Playbook {
  best_evidence: Belief[];
  risky_couriers: Belief[];
  repeat_disputers: { customer: string; disputes: number }[];
  preferences: string[];
  n_cases: number;
  markdown: string;
}
