// frontend/src/services/api.ts - Typed API Client for ASTERION V3 Backend

import {
  VerificationInfo,
  InvestigationPlanInfo,
  ImpactResult,
  RetrievedContext,
  ApprovalRequest
} from '../types';

const API_BASE = '/api';

export interface QueryResponse {
  answer: string;
  verification?: VerificationInfo;
  investigation_plan?: InvestigationPlanInfo;
  session_id?: string;
}

export const api = {
  async getHealth(): Promise<{ status: string; environment: string; falkordb: string }> {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
    return res.json();
  },

  async getRepositories(): Promise<any[]> {
    const res = await fetch(`${API_BASE}/repositories`);
    if (!res.ok) throw new Error(`Failed to fetch repositories: ${res.statusText}`);
    const data = await res.json();
    return data.repositories || [];
  },

  async getRepository(repoId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/repositories/${repoId}`);
    if (!res.ok) throw new Error(`Failed to fetch repository '${repoId}'`);
    return res.json();
  },

  async getRepositoryGraph(repoId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/repositories/${repoId}/graph`);
    if (!res.ok) throw new Error(`Failed to fetch graph for '${repoId}'`);
    const data = await res.json();
    return data.graph || data;
  },

  async sendQuery(
    repoId: string,
    query: string,
    contextNode?: any,
    history?: any[],
    sessionId?: string
  ): Promise<QueryResponse> {
    const res = await fetch(`${API_BASE}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo_id: repoId,
        question: query,
        context_node: contextNode || null,
        history: history || [],
        session_id: sessionId || undefined
      })
    });
    if (!res.ok) throw new Error(`Agent query failed: ${res.statusText}`);
    return res.json();
  },

  async getImpactAnalysis(
    repoId: string,
    targetSymbol?: string,
    diffText?: string
  ): Promise<ImpactResult> {
    const res = await fetch(`${API_BASE}/impact`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo_id: repoId,
        target_symbol: targetSymbol,
        diff_text: diffText
      })
    });
    if (!res.ok) throw new Error(`Impact analysis failed: ${res.statusText}`);
    const data = await res.json();
    return data.impact || data;
  },

  async retrieveContext(
    repoId: string,
    query: string,
    limit: number = 10,
    maxTokens: number = 4000,
    alpha: number = 0.6
  ): Promise<RetrievedContext> {
    const res = await fetch(`${API_BASE}/retrieve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo_id: repoId,
        query,
        limit,
        max_tokens: maxTokens,
        alpha
      })
    });
    if (!res.ok) throw new Error(`Retrieval failed: ${res.statusText}`);
    const data = await res.json();
    return data.data;
  },

  async getMemoryFindings(
    repoId: string,
    workspaceId: string = 'default',
    query?: string
  ): Promise<any[]> {
    const q = query ? `&query=${encodeURIComponent(query)}` : '';
    const res = await fetch(`${API_BASE}/memory/findings?repo_id=${repoId}&workspace_id=${workspaceId}${q}`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.findings || [];
  },

  async getApprovals(status?: string): Promise<ApprovalRequest[]> {
    const q = status ? `?status=${encodeURIComponent(status)}` : '';
    const res = await fetch(`${API_BASE}/approvals${q}`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.requests || [];
  },

  async approveAction(actionId: string, reviewer?: string, notes?: string): Promise<ApprovalRequest> {
    const res = await fetch(`${API_BASE}/approvals/${actionId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reviewer: reviewer || 'admin', notes: notes || 'Approved via UI' })
    });
    if (!res.ok) throw new Error(`Approval failed: ${res.statusText}`);
    const data = await res.json();
    return data.request;
  },

  async rejectAction(actionId: string, reviewer?: string, notes?: string): Promise<ApprovalRequest> {
    const res = await fetch(`${API_BASE}/approvals/${actionId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reviewer: reviewer || 'admin', notes: notes || 'Rejected via UI' })
    });
    if (!res.ok) throw new Error(`Rejection failed: ${res.statusText}`);
    const data = await res.json();
    return data.request;
  }
};

