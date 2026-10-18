// frontend/src/types/index.ts - Core TypeScript Definitions for ASTERION V3

export interface VerificationInfo {
  is_verified: boolean;
  citations_checked: number;
  citations_valid: number;
  fabricated_citations?: string[];
  paths_checked: number;
  paths_valid: number;
  fabricated_paths?: string[];
  insufficient_evidence_flags?: string[];
  missing_required_fields?: string[];
  summary?: string;
}

export interface PlanStepInfo {
  step_id: string;
  capability: string;
  description: string;
  status: string;
  target_symbol?: string;
}

export interface InvestigationPlanInfo {
  query_id: string;
  query_text?: string;
  steps: PlanStepInfo[];
  execution_order: string[];
}

export interface ChatMessage {
  role: 'user' | 'agent';
  content: string;
  verification?: VerificationInfo;
  investigationPlan?: InvestigationPlanInfo;
  timestamp?: number;
}

export interface ImpactedEntity {
  id: string;
  type: string;
  name: string;
  source_path?: string;
  distance?: number;
  risk_level?: string;
}

export interface DownstreamOperation {
  symbol_id: string;
  symbol_name: string;
  operation_type: string;
  target: string;
}

export interface ImpactResult {
  target_symbol?: string;
  files_changed?: string[];
  impacted_entities?: ImpactedEntity[];
  downstream_operations?: DownstreamOperation[];
  connected_tests?: string[];
  risk_level?: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  risk_score?: number;
  diff_summary?: string;
  score_breakdown?: string[];
  explanations?: string[];
}

export interface RetrievedItem {
  id: string;
  type: string;
  name: string;
  source_path: string;
  start_line: number;
  end_line: number;
  docstring?: string;
  snippet?: string;
  bm25_score: number;
  graph_score: number;
  hybrid_score: number;
  rrf_score?: number;
  neighbors?: Array<{ relation: string; name: string; type: string }>;
  token_count?: number;
}

export interface RetrievedContext {
  query: string;
  total_candidates: number;
  returned_items: number;
  estimated_tokens: number;
  token_budget: number;
  budget_used_pct: number;
  context_text: string;
  items: RetrievedItem[];
  elapsed_ms: number;
}

export interface ApprovalRequest {
  action_id: string;
  action_type: string;
  description: string;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  payload: Record<string, any>;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'AUTO_APPROVED';
  requested_at: number;
  resolved_at?: number;
  resolved_by?: string;
  resolution_notes?: string;
}
