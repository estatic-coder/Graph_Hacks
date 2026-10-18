// frontend/src/components/ApprovalModal.tsx - Human-in-the-Loop Agent Action Authorization (ASTERION V3)

import React, { useState } from 'react';
import {
  ShieldAlert,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Flame,
  X,
  UserCheck,
  Terminal,
  FileCode,
  Zap
} from 'lucide-react';
import { ApprovalRequest } from '../types';

interface ApprovalModalProps {
  isOpen: boolean;
  onClose: () => void;
  requests: ApprovalRequest[];
  onApprove: (actionId: string, reviewer: string, notes?: string) => Promise<void>;
  onReject: (actionId: string, reviewer: string, notes?: string) => Promise<void>;
  loading: boolean;
}

export const ApprovalModal: React.FC<ApprovalModalProps> = ({
  isOpen,
  onClose,
  requests,
  onApprove,
  onReject,
  loading
}) => {
  const [reviewerName, setReviewerName] = useState('lead-architect');
  const [notes, setNotes] = useState<Record<string, string>>({});

  if (!isOpen) return null;

  const handleNotesChange = (id: string, text: string) => {
    setNotes(prev => ({ ...prev, [id]: text }));
  };

  const getRiskIcon = (level: string) => {
    switch (level?.toUpperCase()) {
      case 'CRITICAL':
        return <Flame size={14} className="text-rose-400" />;
      case 'HIGH':
        return <AlertTriangle size={14} className="text-amber-400" />;
      default:
        return <ShieldAlert size={14} className="text-blue-400" />;
    }
  };

  const getRiskClass = (level: string) => {
    switch (level?.toUpperCase()) {
      case 'CRITICAL':
        return 'bg-rose-500/10 border-rose-500/30 text-rose-300';
      case 'HIGH':
        return 'bg-amber-500/10 border-amber-500/30 text-amber-300';
      default:
        return 'bg-blue-500/10 border-blue-500/30 text-blue-300';
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="px-5 py-4 border-b border-zinc-800 flex items-center justify-between bg-zinc-950/80">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
              <ShieldAlert size={16} className="text-amber-400" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-zinc-100 flex items-center space-x-2">
                <span>Agent Authorization Gate</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400">
                  {requests.length} Pending
                </span>
              </h2>
              <p className="text-[11px] text-zinc-400">
                Autonomous agent actions requiring explicit human verification
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-zinc-400 hover:text-white rounded-lg hover:bg-zinc-800 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Global Reviewer Info */}
        <div className="px-5 py-2.5 bg-zinc-950/40 border-b border-zinc-800/60 flex items-center justify-between text-xs">
          <div className="flex items-center space-x-2">
            <UserCheck size={13} className="text-zinc-400" />
            <span className="text-zinc-400">Reviewer ID:</span>
            <input
              type="text"
              value={reviewerName}
              onChange={e => setReviewerName(e.target.value)}
              className="bg-zinc-900 border border-zinc-700 rounded px-2 py-0.5 text-xs font-mono text-zinc-200 outline-none w-36"
            />
          </div>
          <span className="text-[10px] font-mono text-zinc-500">Security Gate: Active</span>
        </div>

        {/* Requests List */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 custom-scrollbar">
          {requests.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center space-y-2">
              <CheckCircle size={28} className="text-emerald-500" />
              <p className="text-xs font-semibold text-zinc-300">All Agent Actions Authorized</p>
              <p className="text-[11px] text-zinc-500 max-w-xs">
                There are no pending agent modifications or high-risk commands waiting for authorization.
              </p>
            </div>
          ) : (
            requests.map(req => (
              <div
                key={req.action_id}
                className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 space-y-3"
              >
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center space-x-2">
                      <span className="font-mono text-xs font-semibold text-zinc-200">
                        {req.action_type}
                      </span>
                      <span
                        className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium border ${getRiskClass(
                          req.risk_level
                        )}`}
                      >
                        {getRiskIcon(req.risk_level)}
                        <span>{req.risk_level}</span>
                      </span>
                    </div>
                    <p className="text-xs text-zinc-300 font-sans">{req.description}</p>
                  </div>
                  <span className="text-[10px] font-mono text-zinc-500">
                    ID: {req.action_id}
                  </span>
                </div>

                {/* Payload parameters */}
                {req.payload && Object.keys(req.payload).length > 0 && (
                  <div className="bg-zinc-900/80 rounded-lg p-2.5 border border-zinc-800/80">
                    <span className="text-[10px] font-mono text-zinc-500 block mb-1">
                      Execution Payload:
                    </span>
                    <pre className="text-[10px] font-mono text-zinc-300 overflow-x-auto whitespace-pre-wrap">
                      {JSON.stringify(req.payload, null, 2)}
                    </pre>
                  </div>
                )}

                {/* Resolution Notes Input */}
                <div className="flex items-center space-x-2 pt-1">
                  <input
                    type="text"
                    placeholder="Resolution notes / reason (optional)..."
                    value={notes[req.action_id] || ''}
                    onChange={e => handleNotesChange(req.action_id, e.target.value)}
                    className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none"
                  />
                  <button
                    onClick={() => onApprove(req.action_id, reviewerName, notes[req.action_id])}
                    disabled={loading}
                    className="flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50 transition-colors"
                  >
                    <CheckCircle size={13} />
                    <span>Approve</span>
                  </button>
                  <button
                    onClick={() => onReject(req.action_id, reviewerName, notes[req.action_id])}
                    disabled={loading}
                    className="flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-rose-600/80 hover:bg-rose-600 text-white disabled:opacity-50 transition-colors"
                  >
                    <XCircle size={13} />
                    <span>Reject</span>
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-zinc-800 bg-zinc-950/60 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
