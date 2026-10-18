// frontend/src/components/ImpactPanel.tsx - Visual Blast Radius & Change Impact Analysis (ASTERION V3)

import React, { useState } from 'react';
import {
  Zap,
  AlertTriangle,
  ShieldCheck,
  Flame,
  CheckCircle2,
  FileCode,
  Box,
  Code,
  ChevronDown,
  ChevronRight,
  TestTube,
  Play
} from 'lucide-react';
import { ImpactResult, ImpactedEntity, DownstreamOperation } from '../types';

interface ImpactPanelProps {
  repoId: string;
  selectedSymbol?: string;
  onAnalyzeImpact: (symbol?: string, diffText?: string) => Promise<void>;
  impactResult: ImpactResult | null;
  loading: boolean;
  onSelectNodeByName?: (name: string) => void;
}

export const ImpactPanel: React.FC<ImpactPanelProps> = ({
  repoId,
  selectedSymbol,
  onAnalyzeImpact,
  impactResult,
  loading,
  onSelectNodeByName
}) => {
  const [symbolInput, setSymbolInput] = useState(selectedSymbol || '');
  const [diffInput, setDiffInput] = useState('');
  const [showDiffInput, setShowDiffInput] = useState(false);
  const [expandedSections, setExpandedSections] = useState({
    entities: true,
    operations: true,
    tests: true,
    breakdown: false
  });

  React.useEffect(() => {
    if (selectedSymbol) {
      setSymbolInput(selectedSymbol);
    }
  }, [selectedSymbol]);

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const handleRunAnalysis = (e: React.FormEvent) => {
    e.preventDefault();
    onAnalyzeImpact(symbolInput.trim() || undefined, diffInput.trim() || undefined);
  };

  const getRiskBadge = (level?: string) => {
    switch (level?.toUpperCase()) {
      case 'CRITICAL':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-rose-500/20 text-rose-400 border border-rose-500/40 animate-pulse">
            <Flame size={12} className="text-rose-400" />
            <span>CRITICAL RISK</span>
          </span>
        );
      case 'HIGH':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-amber-500/20 text-amber-400 border border-amber-500/40">
            <AlertTriangle size={12} className="text-amber-400" />
            <span>HIGH RISK</span>
          </span>
        );
      case 'MEDIUM':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-[10px] font-mono font-medium bg-blue-500/20 text-blue-400 border border-blue-500/40">
            <ShieldCheck size={12} className="text-blue-400" />
            <span>MEDIUM RISK</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-[10px] font-mono font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
            <CheckCircle2 size={12} className="text-emerald-400" />
            <span>LOW RISK</span>
          </span>
        );
    }
  };

  const renderEntityIcon = (type?: string) => {
    switch (type?.toLowerCase()) {
      case 'file':
        return <FileCode size={13} className="text-emerald-400" />;
      case 'class':
        return <Box size={13} className="text-purple-400" />;
      default:
        return <Code size={13} className="text-blue-400" />;
    }
  };

  return (
    <div className="flex flex-col h-full bg-zinc-950 text-zinc-200 overflow-hidden">
      {/* Header / Query bar */}
      <div className="p-3.5 border-b border-zinc-800 bg-zinc-900/60 flex-shrink-0">
        <form onSubmit={handleRunAnalysis} className="space-y-2.5">
          <div className="flex items-center space-x-2">
            <div className="relative flex-1">
              <input
                type="text"
                placeholder="Target symbol (e.g. deliver, worker.py)"
                value={symbolInput}
                onChange={e => setSymbolInput(e.target.value)}
                className="w-full bg-zinc-950 border border-zinc-800 focus:border-blue-500 rounded-lg px-3 py-1.5 text-xs font-mono text-zinc-200 placeholder-zinc-500 outline-none"
              />
            </div>
            <button
              type="submit"
              disabled={loading || (!symbolInput.trim() && !diffInput.trim())}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50 transition-all flex-shrink-0"
            >
              <Play size={12} className={loading ? 'animate-spin' : ''} />
              <span>{loading ? 'Analyzing...' : 'Evaluate'}</span>
            </button>
          </div>

          <div className="flex items-center justify-between text-[11px] text-zinc-400">
            <button
              type="button"
              onClick={() => setShowDiffInput(!showDiffInput)}
              className="text-blue-400 hover:underline flex items-center space-x-1"
            >
              <span>{showDiffInput ? 'Hide Git Diff' : '+ Provide Git Diff'}</span>
            </button>
            <span className="font-mono text-[10px] text-zinc-500">Repo: {repoId}</span>
          </div>

          {showDiffInput && (
            <textarea
              placeholder="Paste unified git diff here (optional)..."
              value={diffInput}
              onChange={e => setDiffInput(e.target.value)}
              rows={3}
              className="w-full bg-zinc-950 border border-zinc-800 focus:border-blue-500 rounded-lg p-2 text-[10px] font-mono text-zinc-300 placeholder-zinc-600 outline-none resize-none"
            />
          )}
        </form>
      </div>

      {/* Main Analysis Content */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-4 custom-scrollbar">
        {loading && (
          <div className="flex flex-col items-center justify-center py-16 space-y-3">
            <Zap className="w-6 h-6 text-blue-400 animate-pulse" />
            <p className="text-xs font-mono text-zinc-400">Tracing multi-hop graph blast radius...</p>
          </div>
        )}

        {!loading && !impactResult && (
          <div className="flex flex-col items-center justify-center py-16 text-center space-y-2">
            <Zap size={24} className="text-zinc-700" />
            <p className="text-xs font-semibold text-zinc-400">No Impact Evaluation Performed</p>
            <p className="text-[11px] text-zinc-500 max-w-[240px]">
              Specify a symbol or paste a diff to calculate the affected blast radius, downstream calls, and required tests.
            </p>
          </div>
        )}

        {!loading && impactResult && (
          <>
            {/* Risk Overview Card */}
            <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-3.5 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-wider">Evaluation Scope</span>
                  <h3 className="text-sm font-semibold font-mono text-white">
                    {impactResult.target_symbol || 'Unified Diff Scope'}
                  </h3>
                </div>
                {getRiskBadge(impactResult.risk_level)}
              </div>

              {/* Blast radius summary stats */}
              <div className="grid grid-cols-3 gap-2 pt-2 border-t border-zinc-800/80">
                <div className="bg-zinc-950/60 p-2 rounded-lg border border-zinc-800/50 text-center">
                  <span className="text-[10px] text-zinc-400 block">Impacted Nodes</span>
                  <span className="text-sm font-bold font-mono text-blue-400">
                    {impactResult.impacted_entities?.length || 0}
                  </span>
                </div>
                <div className="bg-zinc-950/60 p-2 rounded-lg border border-zinc-800/50 text-center">
                  <span className="text-[10px] text-zinc-400 block">Downstream Ops</span>
                  <span className="text-sm font-bold font-mono text-amber-400">
                    {impactResult.downstream_operations?.length || 0}
                  </span>
                </div>
                <div className="bg-zinc-950/60 p-2 rounded-lg border border-zinc-800/50 text-center">
                  <span className="text-[10px] text-zinc-400 block">Affected Tests</span>
                  <span className="text-sm font-bold font-mono text-emerald-400">
                    {impactResult.connected_tests?.length || 0}
                  </span>
                </div>
              </div>
            </div>

            {/* Impacted Entities Section */}
            {impactResult.impacted_entities && impactResult.impacted_entities.length > 0 && (
              <div className="border border-zinc-800/80 rounded-xl overflow-hidden bg-zinc-900/40">
                <button
                  onClick={() => toggleSection('entities')}
                  className="w-full px-3 py-2 flex items-center justify-between bg-zinc-900/70 text-xs font-semibold text-zinc-300 hover:text-white"
                >
                  <span className="flex items-center space-x-1.5">
                    <Zap size={13} className="text-blue-400" />
                    <span>Blast Radius Entities ({impactResult.impacted_entities.length})</span>
                  </span>
                  {expandedSections.entities ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </button>
                {expandedSections.entities && (
                  <div className="divide-y divide-zinc-800/60 p-1">
                    {impactResult.impacted_entities.map((entity: ImpactedEntity, idx: number) => (
                      <div
                        key={entity.id || idx}
                        onClick={() => onSelectNodeByName && onSelectNodeByName(entity.name)}
                        className="p-2 hover:bg-zinc-800/40 rounded flex items-center justify-between cursor-pointer transition-colors"
                      >
                        <div className="flex items-center space-x-2 min-w-0">
                          {renderEntityIcon(entity.type)}
                          <div className="truncate">
                            <span className="font-mono text-xs font-medium text-zinc-200">{entity.name}</span>
                            {entity.source_path && (
                              <span className="block text-[10px] text-zinc-500 font-mono truncate">
                                {entity.source_path}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center space-x-2 flex-shrink-0">
                          {entity.distance !== undefined && (
                            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">
                              {entity.distance} hop{entity.distance > 1 ? 's' : ''}
                            </span>
                          )}
                          <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${
                            entity.risk_level === 'CRITICAL' ? 'bg-rose-500/20 text-rose-300' :
                            entity.risk_level === 'HIGH' ? 'bg-amber-500/20 text-amber-300' :
                            'bg-blue-500/10 text-blue-300'
                          }`}>
                            {entity.risk_level || entity.type}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Downstream Operations Section */}
            {impactResult.downstream_operations && impactResult.downstream_operations.length > 0 && (
              <div className="border border-zinc-800/80 rounded-xl overflow-hidden bg-zinc-900/40">
                <button
                  onClick={() => toggleSection('operations')}
                  className="w-full px-3 py-2 flex items-center justify-between bg-zinc-900/70 text-xs font-semibold text-zinc-300 hover:text-white"
                >
                  <span className="flex items-center space-x-1.5">
                    <AlertTriangle size={13} className="text-amber-400" />
                    <span>Downstream Operations ({impactResult.downstream_operations.length})</span>
                  </span>
                  {expandedSections.operations ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </button>
                {expandedSections.operations && (
                  <div className="divide-y divide-zinc-800/60 p-1">
                    {impactResult.downstream_operations.map((op: DownstreamOperation, idx: number) => (
                      <div key={idx} className="p-2 flex items-center justify-between text-xs font-mono">
                        <span className="text-zinc-200">{op.symbol_name}</span>
                        <div className="flex items-center space-x-1.5">
                          <span className="text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded text-[10px]">
                            {op.operation_type}
                          </span>
                          <span className="text-zinc-500">→</span>
                          <span className="text-zinc-300">{op.target}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Connected Tests Section */}
            {impactResult.connected_tests && impactResult.connected_tests.length > 0 && (
              <div className="border border-zinc-800/80 rounded-xl overflow-hidden bg-zinc-900/40">
                <button
                  onClick={() => toggleSection('tests')}
                  className="w-full px-3 py-2 flex items-center justify-between bg-zinc-900/70 text-xs font-semibold text-zinc-300 hover:text-white"
                >
                  <span className="flex items-center space-x-1.5">
                    <TestTube size={13} className="text-emerald-400" />
                    <span>Connected Tests ({impactResult.connected_tests.length})</span>
                  </span>
                  {expandedSections.tests ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </button>
                {expandedSections.tests && (
                  <div className="p-2 space-y-1 font-mono text-[11px]">
                    {impactResult.connected_tests.map((testName: string, idx: number) => (
                      <div
                        key={idx}
                        className="px-2 py-1 bg-zinc-950/60 rounded border border-zinc-800/60 text-emerald-300 flex items-center space-x-2"
                      >
                        <CheckCircle2 size={11} className="text-emerald-400" />
                        <span className="truncate">{testName}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Score Breakdown & Explanations */}
            {impactResult.score_breakdown && impactResult.score_breakdown.length > 0 && (
              <div className="border border-zinc-800/80 rounded-xl overflow-hidden bg-zinc-900/40">
                <button
                  onClick={() => toggleSection('breakdown')}
                  className="w-full px-3 py-2 flex items-center justify-between bg-zinc-900/70 text-xs font-semibold text-zinc-400 hover:text-white"
                >
                  <span>Score Rationale & Evidence ({impactResult.score_breakdown.length})</span>
                  {expandedSections.breakdown ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </button>
                {expandedSections.breakdown && (
                  <div className="p-2.5 space-y-1.5 text-xs text-zinc-300 font-sans">
                    {impactResult.score_breakdown.map((item: string, idx: number) => (
                      <div key={idx} className="flex items-start space-x-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>{item}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
