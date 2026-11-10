// TypeScript mirror of docs/CONTRACTS.md (v0.2; category_explanation is optional so v0.1 data works).

export type Category =
  | "not_received"
  | "unauthorized"
  | "not_as_described"
  | "duplicate"
  | "subscription_cancelled"
  | "refund_not_processed"
  | "other";

export type DisputeStatus =
  | "needs_response"
  | "drafted"
  | "approved"
  | "submitted"
  | "won"
  | "lost"
  | "accepted";

export interface Dispute {
  id: string;
  seller_id: string;
  processor: string;
  processor_dispute_id: string;
  amount: number; // minor units
  currency: string;
  reason_raw: string;
  category: Category | null;
  category_explanation?: string | null;
  status: DisputeStatus;
  created_at: string;
  deadline_at: string;
  customer_hash: string;
  order_id: string | null;
  product_sku: string | null;
  courier: string | null;
  evidence: string[];
}

export type EvidenceType =
  | "order_receipt"
  | "delivery_proof"
  | "tracking"
  | "ip_device"
  | "prior_orders"
  | "customer_message"
  | "refund_policy"
  | "seller_upload"
  | "seller_note";

export interface EvidenceItem {
  id: string;
  dispute_id: string;
  type: EvidenceType;
  source: "stripe" | "shipping_api" | "shop_api" | "seller_upload" | "seller_claim";
  verified: boolean;
  summary: string;
  uri: string | null;
  captured_at: string;
}

export interface DisputeDetail {
  dispute: Dispute;
  evidence: EvidenceItem[];
}

export interface MemoryRef {
  id: string;
  kind: string;
  text: string;
  confidence: number;
  n_supporting: number;
  event_date: string | null;
  used: boolean;
  why: string;
  editable: boolean;
}

export interface Claim {
  text: string;
  evidence_id: string;
}

export interface ChecklistRow {
  item: string;
  status: "available" | "missing";
  evidence_id: string | null;
  required?: boolean;
}

export interface Advice {
  action: "fight" | "accept";
  win_probability: number;
  interval: [number, number];
  n_cases: number;
  basis: string;
  amount_vs_cost: string;
  rationale: string[];
}

export interface Draft {
  dispute_id: string;
  memory_mode: "on" | "off";
  advice: Advice;
  checklist: ChecklistRow[];
  claims: Claim[];
  letter_md: string;
  memory: MemoryRef[];
  cost: { input_tokens: number; output_tokens: number; recall_calls: number; usd: number };
}

export interface ApiErrorBody {
  error: string;
  detail: string;
}

// ---- Phase 4 (CONTRACTS v0.4) ----

export interface Submission {
  id: string;
  dispute_id: string;
  draft_id: string | null;
  letter_md: string;
  status: "pending" | "submitted" | "exported" | "failed";
  approved_at: string;
  submitted_at: string | null;
  pdf_uri: string | null;
  error: string | null;
  note: string | null;
}

export interface BlockedClaim {
  index: number;
  evidence_id: string;
  reason: string;
}

export interface LetterRequest {
  claims: Claim[];
  seller_statement: string | null;
  attach_upload_ids: string[];
  agent_claims?: Claim[];
}

export interface LetterPreview {
  letter_md: string;
  letter_sha256: string;
  blocked: BlockedClaim[];
  attachments: string[];
}

export interface AcceptResult {
  status: DisputeStatus;
  closed_at_processor: boolean;
  note: string;
}

export interface ProcessorStatus {
  can_submit: boolean;
  reason: string | null;
  demo_tools?: boolean;
}

export interface SavedDraft {
  claims: Claim[];
  seller_statement: string | null;
  attach_upload_ids: string[];
  memory_mode: "on" | "off";
}

export interface DirectiveProposal {
  text: string;
  reason: string;
}
