// TypeScript mirror of the Pydantic models in apps/api/app/core/insights.py (GET /core/insights).
// Money is integer minor units of `currency`. Every rate comes with its own n.

export interface Counts {
  n_closed: number;
  n_fought: number;
  won: number;
  lost: number;
  accepted: number;
}

export interface Headline {
  total_disputes: number;
  open_disputes: number;
  closed_disputes: number;
  won: number;
  lost: number;
  accepted: number;
  fought: number;
  win_rate: number | null;
  money_at_stake_open: number;
  money_lost: number;
  money_conceded: number;
  money_recovered: number;
  total_disputed_amount: number;
  net_recovery_rate: number | null;
  closed_disputed_amount: number;
  net_recovery_rate_closed: number | null;
}

export interface ReasonStat {
  category: string;
  count: number;
  amount: number;
}

export interface CategoryWinRate extends Counts {
  category: string;
  win_rate: number | null;
  low_confidence: boolean;
}

export interface GroupStat extends Counts {
  key: string;
  loss_rate: number | null;
  money_lost: number;
  small_sample: boolean;
}

export interface TipFact {
  label: string;
  value: string;
}

export interface Tip {
  id: string;
  title: string;
  evidence: TipFact[];
  action: string;
  small_sample: boolean;
  sample_note: string | null;
}

export interface EvidenceReadiness {
  type: string;
  won_with: number;
  won_total: number;
  lost_with: number;
  lost_total: number;
}

export interface OtherCurrency {
  currency: string;
  disputes: number;
}

export interface Insights {
  seller_id: string;
  currency: string;
  other_currencies: OtherCurrency[];
  headline: Headline;
  top_reasons: ReasonStat[];
  win_rate_by_category: CategoryWinRate[];
  worst_couriers: GroupStat[];
  worst_products: GroupStat[];
  tips: Tip[];
  evidence_readiness: EvidenceReadiness[];
}
