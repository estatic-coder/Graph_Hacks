// frontend/src/components/ChatPanel.tsx - Interactive Agent Chat with Formal Verification & Plan Display

import React, { useState, useRef, useEffect } from 'react';
import {
  Send,
  User,
  BrainCircuit,
  RotateCcw,
  Sparkles,
  ShieldCheck,
  AlertTriangle,
  ListTree,
  ChevronDown,
  ChevronRight
} from 'lucide-react';
import { ChatMessage, VerificationInfo, InvestigationPlanInfo } from '../types';

interface ChatPanelProps {
  messages: ChatMessage[];
  loading: boolean;
  onSendMessage: (text: string) => void;
  onResetChat: () => void;
  onSelectNodeByName?: (name: string) => void;
}

const renderMd = (text: string) => {
  let formatted = text.replace(/```([a-z0-9_-]*)\n([\s\S]*?)```/g, (_m, _lang, code) => {
    return `<pre class="my-2 p-2.5 bg-zinc-950/90 rounded-lg border border-zinc-800 text-[10px] font-mono text-zinc-300 overflow-x-auto whitespace-pre leading-snug"><code>${code.trim()}</code></pre>`;
  });

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

  formatted = formatted
    .replace(/^### (.+)$/gm, '<h4 class="text-[11px] font-bold text-zinc-200 mt-2.5 mb-1 uppercase tracking-wider flex items-center space-x-1.5"><span class="w-1.5 h-1.5 rounded-full bg-blue-400 inline-block mr-1"></span>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="text-xs font-bold text-zinc-100 mt-3 mb-1.5">$1</h3>');

  formatted = formatted.replace(/`([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+:[0-9]+(?:-[0-9]+)?)`/g, '<span class="citation-pill inline-flex items-center px-1.5 py-0.5 rounded bg-blue-950/40 text-blue-300 border border-blue-500/30 font-mono text-[9px] cursor-pointer hover:bg-blue-900/50" data-citation="$1">$1</span>');
  formatted = formatted.replace(/`([^`]+)`/g, '<code class="font-mono text-[10px] bg-zinc-800/90 text-zinc-300 px-1 py-0.5 rounded border border-zinc-700/40 cursor-pointer hover:border-blue-500/50" data-symbol="$1">$1</code>');
  formatted = formatted.replace(/\*\*(.+?)\*\*/g, '<strong class="text-white font-semibold">$1</strong>');
  formatted = formatted.replace(/^- (.+)$/gm, '<li class="ml-3 list-disc text-zinc-300 my-0.5">$1</li>');

  return formatted;
};

const SUGGESTED_PROMPTS = [
  "What is the impact of modifying deliver in OrbitOps?",
  "Enumerate static calls from create_incident to worker",
  "Who owns worker.py and which ADR governs retry policy?",
  "Which tests detect removing release(alert)?"
];

export const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  loading,
  onSendMessage,
  onResetChat,
  onSelectNodeByName
}) => {
  const [input, setInput] = useState('');
  const [expandedPlans, setExpandedPlans] = useState<Record<number, boolean>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;
    onSendMessage(input.trim());
    setInput('');
  };

  const togglePlan = (index: number) => {
    setExpandedPlans(prev => ({ ...prev, [index]: !prev[index] }));
  };

  const handleMessageClick = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    const citation = target.getAttribute('data-citation');
    const symbol = target.getAttribute('data-symbol');
    const name = citation ? citation.split(':')[0] : symbol;
    if (name && onSelectNodeByName) {
      onSelectNodeByName(name);
    }
  };

  return (
    <div className="flex flex-col h-full bg-zinc-900 border-l border-zinc-800">
      {/* Header */}
      <div className="p-3 border-b border-zinc-800 flex items-center justify-between bg-zinc-950/40">
        <div className="flex items-center space-x-2">
          <BrainCircuit className="w-4 h-4 text-blue-400" />
          <h2 className="text-xs font-semibold text-zinc-200">Investigation Copilot</h2>
          <span className="px-1.5 py-0.5 text-[9px] font-mono bg-blue-950/60 text-blue-400 border border-blue-800/40 rounded">
            ASTERION V3
          </span>
        </div>
        <button
          onClick={onResetChat}
          className="p-1 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 rounded transition"
          title="Reset conversation"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Message List */}
      <div
        className="flex-1 overflow-y-auto p-3 space-y-3.5 text-xs"
        onClick={handleMessageClick}
      >
        {messages.map((msg, index) => (
          <div
            key={index}
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div className="flex items-center space-x-1.5 mb-1 px-1">
              {msg.role === 'user' ? (
                <>
                  <span className="text-[10px] text-zinc-400 font-medium">You</span>
                  <User className="w-3 h-3 text-zinc-400" />
                </>
              ) : (
                <>
                  <BrainCircuit className="w-3 h-3 text-blue-400" />
                  <span className="text-[10px] text-blue-400 font-semibold tracking-wide">ASTERION AGENT</span>
                </>
              )}
            </div>

            {/* Message Bubble */}
            <div
              className={`max-w-[92%] rounded-xl px-3.5 py-2.5 leading-relaxed shadow-sm ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-none'
                  : 'bg-zinc-800/90 text-zinc-200 border border-zinc-700/60 rounded-bl-none'
              }`}
            >
              <div
                className="prose prose-invert max-w-none text-xs break-words"
                dangerouslySetInnerHTML={{ __html: renderMd(msg.content) }}
              />

              {/* Investigation Plan Accordion */}
              {msg.investigationPlan && (
                <div className="mt-3 pt-2.5 border-t border-zinc-700/60">
                  <button
                    onClick={() => togglePlan(index)}
                    className="flex items-center justify-between w-full text-[10px] text-zinc-400 hover:text-zinc-200 font-medium py-1"
                  >
                    <span className="flex items-center space-x-1.5">
                      <ListTree className="w-3.5 h-3.5 text-purple-400" />
                      <span>Executed Plan ({msg.investigationPlan.steps.length} steps)</span>
                    </span>
                    {expandedPlans[index] ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                  </button>
                  {expandedPlans[index] && (
                    <div className="mt-2 space-y-1.5 pl-2 border-l border-purple-500/30">
                      {msg.investigationPlan.steps.map((st, sIdx) => (
                        <div key={sIdx} className="text-[10px] font-mono text-zinc-300">
                          <span className="text-purple-400 font-bold">{st.step_id}:</span> {st.description}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Verification Report Badge */}
              {msg.verification && (
                <div className="mt-2.5 pt-2 border-t border-zinc-700/60 flex items-center justify-between text-[10px]">
                  <div className="flex items-center space-x-1.5">
                    {msg.verification.is_verified ? (
                      <span className="inline-flex items-center space-x-1 text-emerald-400 font-semibold">
                        <ShieldCheck className="w-3 h-3" />
                        <span>Formally Verified</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center space-x-1 text-amber-400 font-semibold">
                        <AlertTriangle className="w-3 h-3" />
                        <span>Verification Warning</span>
                      </span>
                    )}
                  </div>
                  <span className="text-zinc-400 font-mono text-[9px]">
                    Citations: {msg.verification.citations_valid}/{msg.verification.citations_checked} valid
                  </span>
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex items-center space-x-2 p-3 bg-zinc-800/40 rounded-xl border border-zinc-800 max-w-[85%]">
            <Sparkles className="w-3.5 h-3.5 text-blue-400 animate-spin" />
            <span className="text-xs text-zinc-400 font-mono">Traversing FalkorDB graph evidence...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Prompts */}
      <div className="px-3 py-2 border-t border-zinc-800/70 bg-zinc-950/20">
        <p className="text-[10px] text-zinc-400 mb-1.5 font-medium flex items-center space-x-1">
          <Sparkles className="w-2.5 h-2.5 text-blue-400" />
          <span>Suggested queries:</span>
        </p>
        <div className="flex flex-wrap gap-1.5">
          {SUGGESTED_PROMPTS.map((prompt, pIdx) => (
            <button
              key={pIdx}
              onClick={() => onSendMessage(prompt)}
              disabled={loading}
              className="text-[9.5px] px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700/50 transition text-left truncate max-w-full"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      {/* Input Form */}
      <form onSubmit={handleSubmit} className="p-3 border-t border-zinc-800 bg-zinc-950/60">
        <div className="flex items-center space-x-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Ask questions about architecture, call chains, or impact..."
            disabled={loading}
            className="flex-1 bg-zinc-900 border border-zinc-700/80 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder-zinc-400 focus:outline-none focus:border-blue-500 transition"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="p-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg transition"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
      </form>
    </div>
  );
};
