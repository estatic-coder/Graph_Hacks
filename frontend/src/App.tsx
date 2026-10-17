import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Activity,
  Database,
  FolderGit2,
  BrainCircuit,
  Code,
  Box,
  FileCode,
  Layers,
  Send,
  User,
  Zap,
  RotateCcw,
  Sparkles,
  ChevronRight,
  ChevronDown,
  ShieldCheck,
  AlertTriangle,
  ListTree,
} from 'lucide-react';
import GraphExplorer from './components/GraphExplorer';
import { RepositorySelector } from './components/RepositorySelector';
import { ImportRepositoryModal, RepositoryMetadata } from './components/ImportRepositoryModal';

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
}

/* ─── Structured Markdown & Table renderer for agent messages ── */
const renderMd = (text: string) => {
  // 1. Code blocks
  let formatted = text.replace(/```([a-z0-9_-]*)\n([\s\S]*?)```/g, (_m, _lang, code) => {
    return `<pre class="my-2 p-2.5 bg-zinc-950/90 rounded-lg border border-zinc-800 text-[10px] font-mono text-zinc-300 overflow-x-auto whitespace-pre leading-snug"><code>${code.trim()}</code></pre>`;
  });

  // 2. Markdown tables
  formatted = formatted.replace(/(?:^|\n)((?:\|[^\n]+\|\n?)+)/g, (_m, tableBlock) => {
    const lines = tableBlock.trim().split('\n').filter((l: string) => l.trim().startsWith('|'));
    if (lines.length < 2) return tableBlock;
    const headerLine = lines[0];
    const isDivider = lines[1].replace(/[\s|:-]/g, '').length === 0;
    const bodyLines = isDivider ? lines.slice(2) : lines.slice(1);

    const headers = headerLine.split('|').slice(1, -1).map((h: string) => h.trim());
    const rows = bodyLines.map((line: string) => line.split('|').slice(1, -1).map((c: string) => c.trim()));

    const headerHtml = `<thead><tr class="border-b border-zinc-800 bg-zinc-900/60">${headers.map((h: string) => `<th class="px-2 py-1.5 text-zinc-300 font-semibold text-[10px]">${h}</th>`).join('')}</tr></thead>`;
    const rowsHtml = `<tbody>${rows.map((r: string[]) => `<tr class="border-b border-zinc-800/40 hover:bg-zinc-800/20">${r.map((c: string) => `<td class="px-2 py-1 text-zinc-400 font-mono text-[9.5px]">${c}</td>`).join('')}</tr>`).join('')}</tbody>`;

    return `<div class="overflow-x-auto my-2.5 rounded-lg border border-zinc-800"><table class="w-full text-left border-collapse">${headerHtml}${rowsHtml}</table></div>`;
  });

  // 3. Headings
  formatted = formatted
    .replace(/^### (.+)$/gm, '<h4 class="text-[11px] font-bold text-zinc-200 mt-2.5 mb-1 uppercase tracking-wider flex items-center space-x-1.5"><span class="w-1.5 h-1.5 rounded-full bg-blue-400 inline-block mr-1"></span>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="text-xs font-bold text-zinc-100 mt-3 mb-1.5">$1</h3>');

  // 4. Citation badges: file.py:10-20 or file.ts:15
  formatted = formatted.replace(/`([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+:[0-9]+(?:-[0-9]+)?)`/g, '<span class="inline-flex items-center px-1.5 py-0.5 rounded bg-blue-950/40 text-blue-300 border border-blue-500/30 font-mono text-[9px]">$1</span>');

  // 5. Normal inline code
  formatted = formatted.replace(/`([^`]+)`/g, '<code class="font-mono text-[10px] bg-zinc-800/90 text-zinc-300 px-1 py-0.5 rounded border border-zinc-700/40">$1</code>');

  // 6. Bold
  formatted = formatted.replace(/\*\*(.+?)\*\*/g, '<strong class="text-white font-semibold">$1</strong>');

  // 7. Bullet lists
  formatted = formatted.replace(/^- (.+)$/gm, '<li class="ml-3 list-disc text-zinc-300 my-0.5">$1</li>');

  // 8. Line breaks
  formatted = formatted.replace(/\n/g, '<br/>');

  return formatted;
};

/* ─── Investigation Plan Viewer Component ────────────────────── */
const InvestigationPlanViewer: React.FC<{ plan: InvestigationPlanInfo }> = ({ plan }) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const steps = plan.steps || [];

  return (
    <div className="mt-2.5 pt-2 border-t border-zinc-800/80">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between w-full px-2 py-1.5 rounded-lg text-[10px] font-mono text-zinc-400 bg-zinc-900/60 border border-zinc-800 hover:border-zinc-700 hover:text-zinc-200 transition-all"
      >
        <span className="flex items-center space-x-1.5">
          <ListTree size={11} className="text-blue-400" />
          <span>Investigation Plan ({steps.length} capabilities)</span>
        </span>
        <ChevronDown size={11} className={`transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="mt-2 space-y-1.5 pl-1 pr-1 pb-1 animate-in fade-in">
          {steps.map((step, sIdx) => {
            const isDone = step.status === 'COMPLETED';
            const isFailed = step.status === 'FAILED';
            return (
              <div
                key={step.step_id || sIdx}
                className="flex items-start space-x-2 p-1.5 rounded bg-zinc-950/70 border border-zinc-800/70 text-[9px] font-mono"
              >
                <div className="mt-1 flex-shrink-0">
                  {isDone ? (
                    <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" title="Completed" />
                  ) : isFailed ? (
                    <span className="w-2 h-2 rounded-full bg-rose-400 inline-block" title="Failed" />
                  ) : (
                    <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" title="Pending" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center space-x-1.5">
                    <span className="text-zinc-200 font-semibold">{step.capability}</span>
                    {step.target_symbol && (
                      <span className="text-blue-400 bg-blue-950/30 px-1 rounded text-[8px] border border-blue-500/20">
                        {step.target_symbol}
                      </span>
                    )}
                  </div>
                  <p className="text-zinc-400 mt-0.5 font-sans leading-tight">{step.description}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

const App: React.FC = () => {
  const [health, setHealth] = useState<string>('checking...');
  const [falkorStatus, setFalkorStatus] = useState<string>('checking...');

  // Repository Management State
  const [repositories, setRepositories] = useState<RepositoryMetadata[]>([]);
  const [currentRepoId, setCurrentRepoId] = useState<string>(() => {
    return localStorage.getItem('asterion_active_repo') || 'sample_1';
  });
  const [isImportModalOpen, setIsImportModalOpen] = useState<boolean>(false);
  const [isRepoIndexing, setIsRepoIndexing] = useState<boolean>(false);

  // Investigation & Graph State
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [query, setQuery] = useState('');
  const [isInvestigating, setIsInvestigating] = useState(false);
  const [affectedNodeIds, setAffectedNodeIds] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const fetchRepositories = useCallback(async () => {
    try {
      const res = await fetch('http://localhost:8000/api/repositories');
      const data = await res.json();
      if (data.status === 'success' && data.repositories) {
        setRepositories(data.repositories);
        if (data.repositories.length > 0) {
          const exists = data.repositories.some((r: RepositoryMetadata) => r.id === currentRepoId);
          if (!exists) {
            const fallbackId = data.repositories[0].id;
            setCurrentRepoId(fallbackId);
            localStorage.setItem('asterion_active_repo', fallbackId);
          }
        }
      }
    } catch (err) {
      console.error('Failed to load repositories:', err);
    }
  }, [currentRepoId]);

  useEffect(() => {
    const checkHealth = () => {
      fetch('http://localhost:8000/health')
        .then(res => res.json())
        .then(data => {
          setHealth(data.status);
          setFalkorStatus(data.falkordb || 'mock');
        })
        .catch(() => {
          setHealth('unavailable');
          setFalkorStatus('offline');
        });
    };
    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    fetchRepositories();
    return () => clearInterval(interval);
  }, [fetchRepositories]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSelectRepo = (repoId: string) => {
    setCurrentRepoId(repoId);
    localStorage.setItem('asterion_active_repo', repoId);
    setSelectedNode(null);
    setAffectedNodeIds([]);
    const targetRepo = repositories.find(r => r.id === repoId);
    if (targetRepo) {
      setMessages(prev => [
        ...prev,
        { role: 'agent', content: `Switched context to **${targetRepo.name}**. Ready for investigation.` },
      ]);
    }
  };

  const handleReindexRepo = async (repoId: string) => {
    setIsRepoIndexing(true);
    try {
      const response = await fetch(`http://localhost:8000/api/repositories/${repoId}/index`, {
        method: 'POST',
      });
      const data = await response.json();
      if (response.ok) {
        await fetchRepositories();
        setSelectedNode(null);
        setAffectedNodeIds([]);
        const stats = data.stats || {};
        setMessages(prev => [
          ...prev,
          {
            role: 'agent',
            content: `Index complete for **${data.repository?.name || repoId}**! Scanned ${stats.files_scanned ?? 0} files, extracted ${stats.symbols_extracted ?? 0} symbols, created ${stats.relationships_created ?? 0} edges.`,
          },
        ]);
      } else {
        alert(`Indexing failed: ${data.detail || 'Unknown error'}`);
      }
    } catch (e) {
      console.error(e);
      alert('Indexing failed. Ensure the backend is reachable.');
    } finally {
      setIsRepoIndexing(false);
    }
  };

  const handleDeleteRepo = async (repoId: string) => {
    try {
      const response = await fetch(`http://localhost:8000/api/repositories/${repoId}`, {
        method: 'DELETE',
      });
      const data = await response.json();
      if (response.ok) {
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

  const handleInvestigate = async (overrideMessage?: string | React.MouseEvent | React.KeyboardEvent) => {
    const text = typeof overrideMessage === 'string' ? overrideMessage : query;
    if (!text.trim() || isInvestigating) return;

    setQuery('');
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    setIsInvestigating(true);

    if (
      text.toLowerCase().includes('impact') ||
      text.toLowerCase().includes('change') ||
      text.toLowerCase().includes('modify')
    ) {
      fetch('http://localhost:8000/api/impact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_id: currentRepoId, max_depth: 3 }),
      })
        .then(res => res.json())
        .then(impData => {
          if (impData.affected_node_ids?.length > 0) {
            setAffectedNodeIds(impData.affected_node_ids);
          }
        })
        .catch(() => {});
    }

    try {
      const response = await fetch('http://localhost:8000/api/investigate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_id: currentRepoId,
          query: text,
          context_node: selectedNode,
          history: messages.map(m => ({ role: m.role, content: m.content })),
        }),
      });
      const data = await response.json();
      if (response.ok) {
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
          { role: 'agent', content: 'Error: ' + (data.detail || 'Unknown error') },
        ]);
      }
    } catch (e) {
      setMessages(prev => [
        ...prev,
        { role: 'agent', content: 'Connection failed. Ensure the backend is running.' },
      ]);
    } finally {
      setIsInvestigating(false);
    }
  };

  const renderNodeIcon = (type: string) => {
    switch (type?.toLowerCase()) {
      case 'file': return <FileCode className="text-emerald-400" size={18} />;
      case 'class': return <Box className="text-purple-400" size={18} />;
      case 'function': return <Code className="text-blue-400" size={18} />;
      case 'repository': return <FolderGit2 className="text-amber-400" size={18} />;
      default: return <Layers className="text-slate-400" size={18} />;
    }
  };

  const nodeTypeColor = (type: string) => {
    switch (type?.toLowerCase()) {
      case 'file': return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
      case 'class': return 'text-purple-400 bg-purple-500/10 border-purple-500/20';
      case 'function': return 'text-blue-400 bg-blue-500/10 border-blue-500/20';
      case 'repository': return 'text-amber-400 bg-amber-500/10 border-amber-500/20';
      default: return 'text-slate-400 bg-slate-800 border-slate-700';
    }
  };

  const falkorStatusConfig = {
    connected: { color: 'text-emerald-400', dot: 'bg-emerald-400', label: 'Connected', ring: true },
    mock: { color: 'text-amber-400', dot: 'bg-amber-400', label: 'In-Memory', ring: false },
  }[falkorStatus] || { color: 'text-rose-400', dot: 'bg-rose-400', label: falkorStatus, ring: false };

  const QUICK_PROMPTS = [
    'What are the main modules?',
    'Find all API endpoints',
    'Show class dependencies',
  ];

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        width: '100vw',
        height: '100vh',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'row',
        background: '#03040a',
        color: '#e2e8f8',
        fontFamily: "'Inter', system-ui, sans-serif",
      }}
    >


      {/* ── Narrow Sidebar ───────────────────────────────────────── */}
      <div
        className="space-y-6 flex-shrink-0"
        style={{
          width: '56px',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '20px 0',
          background: '#09090b',
          borderRight: '1px solid #18181b',
          zIndex: 20,
        }}
      >
        {/* Logo */}
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{
            background: '#18181b',
            border: '1px solid #27272a',
          }}
        >
          <BrainCircuit size={18} style={{ color: '#a1a1aa' }} />
        </div>

        <div className="flex flex-col items-center space-y-2 flex-1">
          {[
            { icon: FolderGit2, label: 'Repositories', active: true, action: () => setIsImportModalOpen(true) },
          ].map(({ icon: Icon, label, active, action }) => (
            <button
              key={label}
              title={label}
              onClick={action}
              className="w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200"
              style={{
                color: active ? '#e4e4e7' : '#52525b',
                background: active ? '#27272a' : 'transparent',
                border: active ? '1px solid #3f3f46' : '1px solid transparent',
              }}
              onMouseEnter={e => {
                if (!active) {
                  (e.currentTarget as HTMLElement).style.color = '#a1a1aa';
                  (e.currentTarget as HTMLElement).style.background = '#18181b';
                }
              }}
              onMouseLeave={e => {
                if (!active) {
                  (e.currentTarget as HTMLElement).style.color = '#52525b';
                  (e.currentTarget as HTMLElement).style.background = 'transparent';
                }
              }}
            >
              <Icon size={17} />
            </button>
          ))}
        </div>
      </div>

      {/* ── Main Content ──────────────────────────────────────────── */}
      <div
        style={{
          flex: 1,
          height: '100%',
          minWidth: 0,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          zIndex: 10,
        }}
      >
        {/* ── Header ───────────────────────────────────────────────── */}
        <header
          style={{
            height: '56px',
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            padding: '0 20px',
            justifyContent: 'space-between',
            background: '#09090b',
            borderBottom: '1px solid #18181b',
          }}
        >
          <div className="flex items-center space-x-5">
            <div className="flex items-center space-x-2.5">
              <h1
                className="font-bold tracking-[0.2em] text-base gradient-text"
                style={{ letterSpacing: '0.15em' }}
              >
                ASTERION
              </h1>
              <span
                className="text-[9px] font-mono px-1.5 py-0.5 rounded-md"
                style={{
                  color: '#71717a',
                  background: '#18181b',
                  border: '1px solid #27272a',
                }}
              >
                v2
              </span>
            </div>

            <div className="h-4 w-px" style={{ background: '#27272a' }} />

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

          {/* Status indicators */}
          <div className="flex items-center space-x-3">
            {/* FalkorDB status */}
            <div
              className="flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-[11px]"
              style={{ background: '#121215', border: '1px solid #27272a' }}
            >
              <Database size={11} style={{ color: '#52525b' }} />
              <span style={{ color: '#52525b' }}>FalkorDB</span>
              <span
                className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                style={{
                  background: falkorStatus === 'connected' ? '#10b981' : falkorStatus === 'mock' ? '#f59e0b' : '#f43f5e',
                }}
              />
              <span style={{ color: falkorStatus === 'connected' ? '#10b981' : falkorStatus === 'mock' ? '#f59e0b' : '#f43f5e' }}>{falkorStatusConfig.label}</span>
            </div>

            {/* API health */}
            <div
              className="flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-[11px]"
              style={{ background: '#121215', border: '1px solid #27272a' }}
            >
              <Activity size={11} style={{ color: '#52525b' }} />
              <span style={{ color: '#52525b' }}>API</span>
              <span
                className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                style={{ background: health === 'healthy' ? '#10b981' : '#f43f5e' }}
              />
              <span style={{ color: health === 'healthy' ? '#10b981' : '#f43f5e' }}>{health}</span>
            </div>
          </div>
        </header>

        {/* ── Workspace ────────────────────────────────────────────── */}
        <div
          style={{
            flex: 1,
            minHeight: 0,
            height: 'calc(100vh - 56px)',
            width: '100%',
            display: 'flex',
            flexDirection: 'row',
            overflow: 'hidden',
          }}
        >
          {/* Graph Explorer */}
          <div
            style={{
              flex: 1,
              height: '100%',
              minHeight: 0,
              minWidth: 0,
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            <GraphExplorer
              key={currentRepoId}
              repoId={currentRepoId}
              onNodeSelect={setSelectedNode}
              affectedNodeIds={affectedNodeIds}
            />
          </div>

          {/* ── Right Panel ──────────────────────────────────────────── */}
          <div
            style={{
              width: '420px',
              height: '100%',
              minHeight: 0,
              flexShrink: 0,
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              background: '#09090b',
              borderLeft: '1px solid #18181b',
            }}
          >
            {/* Panel header */}
            <div
              className="px-4 py-3.5 flex items-center justify-between flex-shrink-0"
              style={{ borderBottom: '1px solid #18181b' }}
            >
              <div className="flex items-center space-x-2.5">
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center"
                  style={{ background: '#18181b', border: '1px solid #27272a' }}
                >
                  <Sparkles size={14} style={{ color: '#a1a1aa' }} />
                </div>
                <div>
                  <span className="text-xs font-semibold" style={{ color: '#e4e4e7' }}>Investigation Agent</span>
                  <p className="text-[10px] font-mono" style={{ color: '#52525b' }}>graph-native intelligence</p>
                </div>
              </div>
              {messages.length > 0 && (
                <button
                  onClick={() => setMessages([])}
                  title="Clear conversation"
                  className="w-6 h-6 rounded-md flex items-center justify-center text-slate-600 hover:text-slate-300 hover:bg-white/5 transition-all"
                >
                  <RotateCcw size={11} />
                </button>
              )}
            </div>

            {/* Chat area */}
            <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-4 min-h-0">
              {/* Selected node card */}
              {selectedNode && (
                <div
                  className="rounded-xl p-3.5 animate-in fade-in scale-in flex-shrink-0"
                  style={{
                    background: '#121215',
                    border: '1px solid #27272a',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                  }}
                >
                  <div className="flex items-start space-x-3">
                    <div
                      className="p-2 rounded-lg flex-shrink-0"
                      style={{ background: '#18181b', border: '1px solid #3f3f46' }}
                    >
                      {renderNodeIcon(selectedNode.label)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-[9px] font-mono uppercase tracking-widest mb-0.5" style={{ color: '#71717a' }}>
                        {selectedNode.label}
                      </div>
                      <h3 className="text-sm font-semibold truncate" style={{ color: '#f4f4f5' }} title={selectedNode.name}>
                        {selectedNode.name}
                      </h3>
                      <p className="text-[10px] font-mono mt-0.5" style={{ color: '#52525b' }}>
                        ID: {selectedNode.id?.split('_').pop()}
                      </p>
                    </div>
                  </div>

                  <div
                    className="mt-3 pt-3 flex items-center justify-between"
                    style={{ borderTop: '1px solid #27272a' }}
                  >
                    <button
                      onClick={() =>
                        handleInvestigate(
                          `Explain this ${selectedNode.label?.toLowerCase() ?? 'component'} in detail`
                        )
                      }
                      disabled={isInvestigating}
                      className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-all"
                      style={{ color: '#a1a1aa', background: '#18181b', border: '1px solid #3f3f46' }}
                    >
                      <Code size={11} />
                      <span>Explain</span>
                    </button>
                    <button
                      onClick={() =>
                        handleInvestigate(
                          `What is the impact of changing this ${selectedNode.label?.toLowerCase() ?? 'component'}?`
                        )
                      }
                      disabled={isInvestigating}
                      className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-all"
                      style={{ color: '#e4e4e7', background: '#27272a', border: '1px solid #3f3f46' }}
                    >
                      <Zap size={11} className={isInvestigating ? 'animate-pulse' : ''} />
                      <span>Impact</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Empty state */}
              {messages.length === 0 && !selectedNode && (
                <div className="flex flex-col items-center justify-center py-12 space-y-6 animate-in fade-in">
                  <div
                    className="w-14 h-14 rounded-2xl flex items-center justify-center"
                    style={{ background: '#121215', border: '1px solid #27272a' }}
                  >
                    <BrainCircuit size={22} style={{ color: '#52525b' }} />
                  </div>
                  <div className="text-center space-y-1.5">
                    <p className="text-xs font-semibold" style={{ color: '#a1a1aa' }}>Select a node or ask a question</p>
                    <p className="text-[10px] max-w-[180px] leading-relaxed mx-auto" style={{ color: '#52525b' }}>
                      Graph-native AI will investigate the codebase using live knowledge graph queries.
                    </p>
                  </div>

                  {/* Quick prompts */}
                  <div className="w-full space-y-1.5">
                    {QUICK_PROMPTS.map((prompt) => (
                      <button
                        key={prompt}
                        onClick={() => handleInvestigate(prompt)}
                        className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-[11px] transition-all group"
                        style={{ color: '#71717a', background: '#121215', border: '1px solid #27272a' }}
                        onMouseEnter={e => {
                          (e.currentTarget as HTMLElement).style.borderColor = '#3f3f46';
                          (e.currentTarget as HTMLElement).style.color = '#a1a1aa';
                          (e.currentTarget as HTMLElement).style.background = '#18181b';
                        }}
                        onMouseLeave={e => {
                          (e.currentTarget as HTMLElement).style.borderColor = '#27272a';
                          (e.currentTarget as HTMLElement).style.color = '#71717a';
                          (e.currentTarget as HTMLElement).style.background = '#121215';
                        }}
                      >
                        <span>{prompt}</span>
                        <ChevronRight size={11} className="opacity-40 group-hover:opacity-80 transition-opacity" />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Messages */}
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex animate-in fade-in slide-up ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  style={{ '--animation-delay': `${idx * 30}ms` } as React.CSSProperties}
                >
                  {msg.role === 'agent' && (
                    <div
                      className="w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0 mt-0.5 mr-2"
                      style={{ background: '#18181b', border: '1px solid #27272a' }}
                    >
                      <Sparkles size={10} style={{ color: '#71717a' }} />
                    </div>
                  )}
                  <div
                    className={`max-w-[92%] rounded-xl px-3.5 py-3 text-xs leading-relaxed ${
                      msg.role === 'user' ? 'rounded-tr-sm' : 'rounded-tl-sm'
                    }`}
                    style={
                      msg.role === 'user'
                        ? { background: '#1c1c1f', border: '1px solid #3f3f46', color: '#e4e4e7' }
                        : { background: '#121215', border: '1px solid #27272a', color: '#d4d4d8' }
                    }
                  >
                    {msg.role === 'user' ? (
                      <div className="flex items-center space-x-1.5 mb-1.5" style={{ opacity: 0.5 }}>
                        <User size={9} />
                        <span className="text-[9px] uppercase tracking-widest font-semibold">You</span>
                      </div>
                    ) : (
                      <>
                        {msg.verification && (
                          <div className="mb-2 flex flex-wrap items-center gap-1.5">
                            {msg.verification.is_verified ? (
                              <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[9px] font-mono font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                                <ShieldCheck size={11} className="text-emerald-400" />
                                <span>VERIFIED EVIDENCE</span>
                                <span className="text-emerald-500/70 font-normal">
                                  ({msg.verification.citations_valid} source, {msg.verification.paths_valid} graph)
                                </span>
                              </span>
                            ) : (
                              <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[9px] font-mono font-medium bg-amber-500/10 text-amber-400 border border-amber-500/30">
                                <AlertTriangle size={11} className="text-amber-400" />
                                <span>
                                  {msg.verification.missing_required_fields && msg.verification.missing_required_fields.length > 0
                                    ? 'INCOMPLETE RESULT'
                                    : 'CAUTION / UNVERIFIED'}
                                </span>
                              </span>
                            )}
                            {msg.verification.fabricated_citations && msg.verification.fabricated_citations.length > 0 && (
                              <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[9px] font-mono bg-rose-500/10 text-rose-400 border border-rose-500/30">
                                <span>{msg.verification.fabricated_citations.length} quarantined</span>
                              </span>
                            )}
                          </div>
                        )}
                      </>
                    )}
                    <div
                      dangerouslySetInnerHTML={{ __html: renderMd(msg.content) }}
                    />
                    {msg.role === 'agent' && msg.investigationPlan && (
                      <InvestigationPlanViewer plan={msg.investigationPlan} />
                    )}
                  </div>
                  {msg.role === 'user' && (
                    <div
                      className="w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0 mt-0.5 ml-2"
                      style={{ background: '#18181b', border: '1px solid #27272a' }}
                    >
                      <User size={10} style={{ color: '#52525b' }} />
                    </div>
                  )}
                </div>
              ))}

              {/* Typing indicator */}
              {isInvestigating && (
                <div className="flex justify-start animate-in fade-in">
                  <div
                    className="w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0 mt-0.5 mr-2"
                    style={{ background: '#18181b', border: '1px solid #27272a' }}
                  >
                    <Sparkles size={10} style={{ color: '#71717a' }} />
                  </div>
                  <div
                    className="rounded-xl rounded-tl-sm px-4 py-3.5 flex items-center space-x-1"
                    style={{ background: '#121215', border: '1px solid #27272a' }}
                  >
                    <div className="w-1.5 h-1.5 rounded-full typing-dot" style={{ background: '#52525b' }} />
                    <div className="w-1.5 h-1.5 rounded-full typing-dot" style={{ background: '#52525b' }} />
                    <div className="w-1.5 h-1.5 rounded-full typing-dot" style={{ background: '#52525b' }} />
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div
              className="p-3.5 flex-shrink-0"
              style={{ borderTop: '1px solid #18181b' }}
            >
              <div className="relative">
                <input
                  type="text"
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') handleInvestigate(); }}
                  placeholder={isInvestigating ? 'Investigating…' : 'Ask about this codebase…'}
                  disabled={isInvestigating}
                  className="w-full pr-10 pl-4 py-3 rounded-xl text-xs disabled:opacity-50 transition-all"
                  style={{
                    background: '#121215',
                    border: '1px solid #27272a',
                    color: '#e4e4e7',
                    outline: 'none',
                    fontFamily: "'Inter', system-ui, sans-serif",
                  }}
                />
                <button
                  onClick={handleInvestigate}
                  disabled={!query.trim() || isInvestigating}
                  className="absolute right-2 top-1/2 -translate-y-1/2 w-7 h-7 rounded-lg flex items-center justify-center transition-all disabled:opacity-30"
                  style={{
                    background: query.trim() && !isInvestigating ? '#27272a' : 'transparent',
                    color: query.trim() && !isInvestigating ? '#e4e4e7' : '#52525b',
                    border: query.trim() && !isInvestigating ? '1px solid #3f3f46' : '1px solid transparent',
                  }}
                >
                  <Send size={13} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Import Modal */}
      <ImportRepositoryModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        onImportSuccess={handleImportSuccess}
      />
    </div>
  );
};

export default App;
