// frontend/src/App.tsx - ASTERION V3 Production-Grade Architecture & Orchestrator

import React, { useState, useEffect, useCallback } from 'react';
import {
  BrainCircuit,
  Activity,
  Database,
  FolderGit2,
  Sparkles,
  Zap,
  ShieldAlert,
  Code,
  FileCode,
  Box,
  Layers,
  ChevronRight
} from 'lucide-react';
import GraphExplorer from './components/GraphExplorer';
import { RepositorySelector } from './components/RepositorySelector';
import { ImportRepositoryModal, RepositoryMetadata } from './components/ImportRepositoryModal';
import { ChatPanel } from './components/ChatPanel';
import { ImpactPanel } from './components/ImpactPanel';
import { ApprovalModal } from './components/ApprovalModal';
import { api } from './services/api';
import { ChatMessage, ImpactResult, ApprovalRequest } from './types';

type ActiveRightTab = 'chat' | 'impact';

const App: React.FC = () => {
  // System Health & Connection State
  const [health, setHealth] = useState<string>('checking...');
  const [falkorStatus, setFalkorStatus] = useState<string>('checking...');

  // Repository Management State
  const [repositories, setRepositories] = useState<RepositoryMetadata[]>([]);
  const [currentRepoId, setCurrentRepoId] = useState<string>(() => {
    return localStorage.getItem('asterion_active_repo') || 'sample_1';
  });
  const [isImportModalOpen, setIsImportModalOpen] = useState<boolean>(false);
  const [isRepoIndexing, setIsRepoIndexing] = useState<boolean>(false);

  // Graph Interaction State
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [focusedNodeName, setFocusedNodeName] = useState<string | undefined>(undefined);
  const [affectedNodeIds, setAffectedNodeIds] = useState<string[]>([]);

  // Right Panel Tab
  const [activeTab, setActiveTab] = useState<ActiveRightTab>('chat');

  // Chat State
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isInvestigating, setIsInvestigating] = useState<boolean>(false);

  // Impact Analysis State
  const [impactResult, setImpactResult] = useState<ImpactResult | null>(null);
  const [isImpactLoading, setIsImpactLoading] = useState<boolean>(false);

  // Approvals State
  const [isApprovalModalOpen, setIsApprovalModalOpen] = useState<boolean>(false);
  const [pendingApprovals, setPendingApprovals] = useState<ApprovalRequest[]>([]);
  const [isApprovalsLoading, setIsApprovalsLoading] = useState<boolean>(false);

  // Fetch repositories
  const fetchRepositories = useCallback(async () => {
    try {
      const repos = await api.getRepositories();
      setRepositories(repos);
      if (repos.length > 0) {
        const exists = repos.some((r: any) => r.id === currentRepoId);
        if (!exists) {
          const fallbackId = repos[0].id;
          setCurrentRepoId(fallbackId);
          localStorage.setItem('asterion_active_repo', fallbackId);
        }
      }
    } catch (err) {
      console.error('Failed to load repositories:', err);
    }
  }, [currentRepoId]);

  // Periodic Health & Approvals Poll
  useEffect(() => {
    const checkSystem = async () => {
      try {
        const h = await api.getHealth();
        setHealth(h.status);
        setFalkorStatus(h.falkordb || 'mock');
      } catch {
        setHealth('unavailable');
        setFalkorStatus('offline');
      }

      try {
        const reqs = await api.getApprovals('PENDING');
        setPendingApprovals(reqs);
      } catch (e) {
        console.error('Failed to poll approvals:', e);
      }
    };

    checkSystem();
    const interval = setInterval(checkSystem, 6000);
    fetchRepositories();
    return () => clearInterval(interval);
  }, [fetchRepositories]);

  const handleSelectRepo = (repoId: string) => {
    setCurrentRepoId(repoId);
    localStorage.setItem('asterion_active_repo', repoId);
    setSelectedNode(null);
    setFocusedNodeName(undefined);
    setAffectedNodeIds([]);
    setImpactResult(null);
    const targetRepo = repositories.find(r => r.id === repoId);
    if (targetRepo) {
      setMessages(prev => [
        ...prev,
        { role: 'agent', content: `Switched context to **${targetRepo.name}**. Ready for multi-agent code intelligence.` },
      ]);
    }
  };

  const handleReindexRepo = async (repoId: string) => {
    setIsRepoIndexing(true);
    try {
      const res = await fetch(`http://localhost:8000/api/repositories/${repoId}/index`, {
        method: 'POST',
      });
      const data = await res.json();
      if (res.ok) {
        await fetchRepositories();
        setSelectedNode(null);
        setAffectedNodeIds([]);
        const stats = data.stats || {};
        setMessages(prev => [
          ...prev,
          {
            role: 'agent',
            content: `Incremental index complete for **${data.repository?.name || repoId}**! Scanned ${stats.files_scanned ?? 0} files, extracted ${stats.symbols_extracted ?? 0} symbols, updated ${stats.relationships_created ?? 0} relationships.`,
          },
        ]);
      } else {
        alert(`Indexing failed: ${data.detail || 'Unknown error'}`);
      }
    } catch (e) {
      console.error(e);
      alert('Indexing failed. Ensure backend is running.');
    } finally {
      setIsRepoIndexing(false);
    }
  };

  const handleDeleteRepo = async (repoId: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/repositories/${repoId}`, {
        method: 'DELETE',
      });
      const data = await res.json();
      if (res.ok) {
        await fetchRepositories();
        if (currentRepoId === repoId) {
          const remaining = repositories.filter(r => r.id !== repoId);
          const nextId = remaining.length > 0 ? remaining[0].id : 'sample_1';
          setCurrentRepoId(nextId);
          localStorage.setItem('asterion_active_repo', nextId);
          setSelectedNode(null);
          setAffectedNodeIds([]);
        }
      } else {
        alert(`Delete failed: ${data.detail || 'Unknown error'}`);
      }
    } catch (e) {
      console.error(e);
      alert('Failed to delete repository.');
    }
  };

  const handleImportSuccess = (newRepo: RepositoryMetadata) => {
    fetchRepositories();
    setCurrentRepoId(newRepo.id);
    localStorage.setItem('asterion_active_repo', newRepo.id);
    setSelectedNode(null);
    setAffectedNodeIds([]);
    setMessages(prev => [
      ...prev,
      {
        role: 'agent',
        content: `Successfully imported **${newRepo.name}**! Found ${newRepo.stats?.symbols_extracted ?? 0} symbols across ${newRepo.stats?.files_scanned ?? 0} files.`,
      },
    ]);
  };

  // Chat Submission Handler
  const handleSendMessage = async (text: string) => {
    if (!text.trim() || isInvestigating) return;

    setMessages(prev => [...prev, { role: 'user', content: text }]);
    setIsInvestigating(true);

    // Auto-trigger impact analysis if query is impact-oriented
    const lower = text.toLowerCase();
    if (lower.includes('impact') || lower.includes('change') || lower.includes('modify')) {
      handleAnalyzeImpact(selectedNode?.name);
    }

    try {
      const res = await fetch('http://localhost:8000/api/investigate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_id: currentRepoId,
          query: text,
          context_node: selectedNode,
          history: messages.map(m => ({ role: m.role, content: m.content })),
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setMessages(prev => [
          ...prev,
          {
            role: 'agent',
            content: data.answer,
            verification: data.verification,
            investigationPlan: data.investigation_plan,
          },
        ]);
      } else {
        setMessages(prev => [
          ...prev,
          { role: 'agent', content: 'Agent Error: ' + (data.detail || 'Execution failed') },
        ]);
      }
    } catch (e) {
      setMessages(prev => [
        ...prev,
        { role: 'agent', content: 'Connection failed. Verify the Asterion backend server.' },
      ]);
    } finally {
      setIsInvestigating(false);
    }
  };

  // Impact Analysis Handler
  const handleAnalyzeImpact = async (symbol?: string, diffText?: string) => {
    setIsImpactLoading(true);
    setActiveTab('impact');
    try {
      const result = await api.getImpactAnalysis(currentRepoId, symbol, diffText);
      setImpactResult(result);
      if (result.impacted_entities && result.impacted_entities.length > 0) {
        const ids = result.impacted_entities.map(e => e.id);
        setAffectedNodeIds(ids);
      }
    } catch (err) {
      console.error('Impact analysis error:', err);
    } finally {
      setIsImpactLoading(false);
    }
  };

  // Approvals Handlers
  const handleApproveAction = async (actionId: string, reviewer: string, notes?: string) => {
    setIsApprovalsLoading(true);
    try {
      await api.approveAction(actionId, reviewer, notes);
      setPendingApprovals(prev => prev.filter(r => r.action_id !== actionId));
      setMessages(prev => [
        ...prev,
        { role: 'agent', content: `Action \`${actionId}\` authorized by **${reviewer}**. Execution proceeding safely.` }
      ]);
    } catch (err) {
      alert(`Approval error: ${err}`);
    } finally {
      setIsApprovalsLoading(false);
    }
  };

  const handleRejectAction = async (actionId: string, reviewer: string, reason?: string) => {
    setIsApprovalsLoading(true);
    try {
      await api.rejectAction(actionId, reviewer, reason);
      setPendingApprovals(prev => prev.filter(r => r.action_id !== actionId));
      setMessages(prev => [
        ...prev,
        { role: 'agent', content: `Action \`${actionId}\` rejected by **${reviewer}**. Reason: ${reason || 'Denied by policy'}.` }
      ]);
    } catch (err) {
      alert(`Rejection error: ${err}`);
    } finally {
      setIsApprovalsLoading(false);
    }
  };

  const renderNodeIcon = (type: string) => {
    switch (type?.toLowerCase()) {
      case 'file': return <FileCode className="text-emerald-400" size={16} />;
      case 'class': return <Box className="text-purple-400" size={16} />;
      case 'function': return <Code className="text-blue-400" size={16} />;
      default: return <Layers className="text-slate-400" size={16} />;
    }
  };

  return (
    <div className="fixed inset-0 w-screen h-screen overflow-hidden flex flex-row bg-[#03040a] text-[#e2e8f8] font-sans">
      {/* ── Left Slim Sidebar ───────────────────────────────────── */}
      <div className="w-14 h-full flex flex-col items-center py-4 bg-[#09090b] border-r border-[#18181b] z-20 flex-shrink-0 space-y-6">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-[#18181b] border border-[#27272a] shadow-inner">
          <BrainCircuit size={18} className="text-blue-400 animate-pulse" />
        </div>

        <div className="flex flex-col items-center space-y-3 flex-1">
          <button
            title="Import Repository"
            onClick={() => setIsImportModalOpen(true)}
            className="w-9 h-9 rounded-xl flex items-center justify-center text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-all border border-transparent hover:border-zinc-700"
          >
            <FolderGit2 size={17} />
          </button>
        </div>
      </div>

      {/* ── Main Content Area ──────────────────────────────────────── */}
      <div className="flex-1 h-full min-w-0 flex flex-col overflow-hidden z-10">
        {/* ── Top Header ───────────────────────────────────────────── */}
        <header className="h-14 flex-shrink-0 flex items-center justify-between px-5 bg-[#09090b] border-b border-[#18181b]">
          <div className="flex items-center space-x-5">
            <div className="flex items-center space-x-2.5">
              <h1 className="font-bold tracking-[0.2em] text-sm text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-indigo-300 to-purple-400">
                ASTERION
              </h1>
              <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded-md text-emerald-400 bg-emerald-950/40 border border-emerald-500/30">
                v3-prod
              </span>
            </div>

            <div className="h-4 w-px bg-zinc-800" />

            <RepositorySelector
              repositories={repositories}
              activeRepoId={currentRepoId}
              onSelectRepo={handleSelectRepo}
              onOpenImportModal={() => setIsImportModalOpen(true)}
              onReindexRepo={handleReindexRepo}
              onDeleteRepo={handleDeleteRepo}
              isIndexing={isRepoIndexing}
            />
          </div>

          {/* Right Status Controls & Approvals Gate */}
          <div className="flex items-center space-x-3">
            {/* Approval Gate Button */}
            <button
              onClick={() => setIsApprovalModalOpen(true)}
              className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-[11px] font-mono border transition-all ${
                pendingApprovals.length > 0
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse'
                  : 'bg-zinc-900 text-zinc-400 border-zinc-800 hover:text-zinc-200'
              }`}
            >
              <ShieldAlert size={12} className={pendingApprovals.length > 0 ? 'text-amber-400' : 'text-zinc-500'} />
              <span>Gate</span>
              {pendingApprovals.length > 0 && (
                <span className="px-1.5 py-0.2 rounded-full bg-amber-500 text-black font-bold text-[9px]">
                  {pendingApprovals.length}
                </span>
              )}
            </button>

            {/* FalkorDB status */}
            <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-[11px] bg-zinc-900 border border-zinc-800">
              <Database size={11} className="text-zinc-400" />
              <span className="text-zinc-400">FalkorDB</span>
              <span
                className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                  falkorStatus === 'connected' ? 'bg-emerald-400' : falkorStatus === 'mock' ? 'bg-amber-400' : 'bg-rose-400'
                }`}
              />
              <span className="font-mono text-[10px] text-zinc-300 capitalize">{falkorStatus}</span>
            </div>

            {/* API health */}
            <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-[11px] bg-zinc-900 border border-zinc-800">
              <Activity size={11} className="text-zinc-400" />
              <span
                className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                  health === 'healthy' ? 'bg-emerald-400' : 'bg-rose-400'
                }`}
              />
              <span className="font-mono text-[10px] text-zinc-300 capitalize">{health}</span>
            </div>
          </div>
        </header>

        {/* ── Main Workspace: Split Canvas & Inspector ─────────────── */}
        <div className="flex-1 flex flex-row overflow-hidden min-h-0">
          {/* Cytoscape Graph Canvas */}
          <div className="flex-1 h-full relative overflow-hidden">
            <GraphExplorer
              key={currentRepoId}
              repoId={currentRepoId}
              onNodeSelect={setSelectedNode}
              affectedNodeIds={affectedNodeIds}
              focusedNodeName={focusedNodeName}
            />

            {/* Selected Node Floating Pill */}
            {selectedNode && (
              <div className="absolute bottom-4 left-4 z-20 bg-zinc-900/90 backdrop-blur-md border border-zinc-800 rounded-xl p-3 shadow-2xl flex items-center space-x-3 max-w-md animate-in fade-in slide-up">
                <div className="p-2 rounded-lg bg-zinc-950 border border-zinc-800 flex-shrink-0">
                  {renderNodeIcon(selectedNode.label)}
                </div>
                <div className="min-w-0 flex-1">
                  <span className="text-[9px] font-mono uppercase tracking-widest text-zinc-500 block">
                    {selectedNode.label}
                  </span>
                  <h4 className="text-xs font-semibold text-zinc-200 truncate">{selectedNode.name}</h4>
                  {selectedNode.id && (
                    <span className="text-[10px] font-mono text-zinc-400 block truncate">
                      {selectedNode.id}
                    </span>
                  )}
                </div>
                <div className="flex items-center space-x-1.5 flex-shrink-0">
                  <button
                    onClick={() => handleSendMessage(`Explain ${selectedNode.label?.toLowerCase() || 'component'} '${selectedNode.name}' in detail`)}
                    className="px-2 py-1 rounded-md text-[10px] font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 transition-colors"
                  >
                    Explain
                  </button>
                  <button
                    onClick={() => handleAnalyzeImpact(selectedNode.name)}
                    className="px-2 py-1 rounded-md text-[10px] font-medium bg-blue-600/80 hover:bg-blue-600 text-white transition-colors"
                  >
                    Impact
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* ── Right Panel: Tabbed Agent & Impact Workspace ───────── */}
          <div className="w-[440px] h-full flex flex-col bg-[#09090b] border-l border-[#18181b] z-20 flex-shrink-0">
            {/* Tab switch header */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#18181b] bg-zinc-950/60">
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => setActiveTab('chat')}
                  className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    activeTab === 'chat'
                      ? 'bg-zinc-800 text-zinc-100 shadow'
                      : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
                  }`}
                >
                  <Sparkles size={13} className={activeTab === 'chat' ? 'text-blue-400' : ''} />
                  <span>Investigation Agent</span>
                </button>
                <button
                  onClick={() => setActiveTab('impact')}
                  className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    activeTab === 'impact'
                      ? 'bg-zinc-800 text-zinc-100 shadow'
                      : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
                  }`}
                >
                  <Zap size={13} className={activeTab === 'impact' ? 'text-amber-400' : ''} />
                  <span>Blast Radius</span>
                </button>
              </div>

              {activeTab === 'chat' && messages.length > 0 && (
                <button
                  onClick={() => setMessages([])}
                  className="text-[10px] font-mono text-zinc-500 hover:text-zinc-300 px-1.5 py-0.5 rounded hover:bg-zinc-800"
                >
                  Clear
                </button>
              )}
            </div>

            {/* Tab Body */}
            <div className="flex-1 overflow-hidden min-h-0">
              {activeTab === 'chat' ? (
                <ChatPanel
                  messages={messages}
                  loading={isInvestigating}
                  onSendMessage={handleSendMessage}
                  onResetChat={() => setMessages([])}
                  onSelectNodeByName={name => setFocusedNodeName(name)}
                />
              ) : (
                <ImpactPanel
                  repoId={currentRepoId}
                  selectedSymbol={selectedNode?.name}
                  onAnalyzeImpact={handleAnalyzeImpact}
                  impactResult={impactResult}
                  loading={isImpactLoading}
                  onSelectNodeByName={name => setFocusedNodeName(name)}
                />
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Modals ─────────────────────────────────────────────────── */}
      <ImportRepositoryModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        onImportSuccess={handleImportSuccess}
      />

      <ApprovalModal
        isOpen={isApprovalModalOpen}
        onClose={() => setIsApprovalModalOpen(false)}
        requests={pendingApprovals}
        onApprove={handleApproveAction}
        onReject={handleRejectAction}
        loading={isApprovalsLoading}
      />
    </div>
  );
};

export default App;
