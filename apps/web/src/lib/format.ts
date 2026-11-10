import type { Category, DisputeStatus, EvidenceType } from "./types";

const ZERO_DECIMAL = new Set(["jpy", "krw", "vnd", "clp", "isk", "ugx", "xof", "xaf"]);

export function money(amountMinor: number, currency: string): string {
  const divisor = ZERO_DECIMAL.has(currency.toLowerCase()) ? 1 : 100;
  return new Intl.NumberFormat("en", { style: "currency", currency: currency.toUpperCase() }).format(
    amountMinor / divisor,
  );
}

export function dateTime(iso: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(iso)) + " UTC";
}

export const CATEGORY_LABEL: Record<Category, string> = {
  not_received: "Not received",
  unauthorized: "Unauthorized / fraud",
  not_as_described: "Not as described",
  duplicate: "Duplicate",
  subscription_cancelled: "Subscription cancelled",
  refund_not_processed: "Refund not processed",
  other: "Other",
};

export const STATUS_LABEL: Record<DisputeStatus, string> = {
  needs_response: "Needs response",
  drafted: "Drafted",
  approved: "Approved",
  submitted: "Submitted",
  won: "Won",
  lost: "Lost",
  accepted: "Accepted",
};

export const EVIDENCE_LABEL: Record<EvidenceType, string> = {
  order_receipt: "Order receipt",
  delivery_proof: "Delivery proof",
  tracking: "Tracking",
  ip_device: "IP / device",
  prior_orders: "Prior orders",
  customer_message: "Customer message",
  refund_policy: "Refund policy",
  seller_upload: "Seller upload",
  seller_note: "Seller note",
};

export function percent(p: number): string {
  return `${Math.round(p * 100)}%`;
}

/** Statuses where the deadline still matters. */
export function isOpen(status: DisputeStatus): boolean {
  return status === "needs_response" || status === "drafted" || status === "approved";
}
