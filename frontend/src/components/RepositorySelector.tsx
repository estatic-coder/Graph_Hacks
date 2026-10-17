import React, { useState, useRef, useEffect } from 'react';
import { 
  FolderGit2, 
  ChevronDown, 
  Plus, 
  RefreshCw, 
  Trash2, 
  Check, 
  GitBranch, 
  FileArchive, 
  HardDrive,
  AlertTriangle,
  Loader2
} from 'lucide-react';
import { RepositoryMetadata } from './ImportRepositoryModal';

interface RepositorySelectorProps {
  repositories: RepositoryMetadata[];
  activeRepoId: string;
  onSelectRepo: (repoId: string) => void;
  onOpenImportModal: () => void;
  onReindexRepo: (repoId: string) => Promise<void>;
  onDeleteRepo: (repoId: string) => Promise<void>;
  isIndexing: boolean;
}

export const RepositorySelector: React.FC<RepositorySelectorProps> = ({
  repositories,
  activeRepoId,
  onSelectRepo,
  onOpenImportModal,
  onReindexRepo,
  onDeleteRepo,
  isIndexing
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const activeRepo = repositories.find(r => r.id === activeRepoId) || repositories[0];

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setDeleteConfirmId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleConfirmDelete = async (repoId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setIsDeleting(true);
    try {
      await onDeleteRepo(repoId);
      setDeleteConfirmId(null);
    } finally {
      setIsDeleting(false);
    }
  };

  const renderSourceIcon = (type: string) => {
    switch (type) {
      case 'github': return <GitBranch size={13} className="text-purple-400" />;
      case 'zip': return <FileArchive size={13} className="text-amber-400" />;
      default: return <HardDrive size={13} className="text-blue-400" />;
    }
  };

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case 'ready':
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            ready
          </span>
        );
      case 'indexing':
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20 animate-pulse">
            indexing
          </span>
        );
      case 'error':
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
            error
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-400 border border-slate-700">
            empty
          </span>
        );
    }
  };

  return (
    <div className="relative inline-block text-left" ref={dropdownRef}>
      <div className="flex items-center space-x-2">
        {/* Dropdown Toggle Button */}
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="group flex items-center space-x-2.5 bg-slate-800/80 hover:bg-slate-800 text-slate-200 px-3 py-1.5 rounded-lg border border-slate-700/60 hover:border-blue-500/50 shadow-sm transition-all duration-200"
        >
          <FolderGit2 size={15} className="text-blue-400" />
          <span className="text-xs font-semibold max-w-[160px] truncate">
            {activeRepo ? activeRepo.name : 'Select Repository'}
          </span>
          {activeRepo?.is_demo && (
            <span className="text-[10px] bg-blue-500/20 text-blue-300 font-mono px-1.5 py-0.2 rounded border border-blue-500/30">
              demo
            </span>
          )}
          <ChevronDown 
            size={13} 
            className={`text-slate-400 transition-transform duration-200 ${isOpen ? 'rotate-180 text-blue-400' : ''}`} 
          />
        </button>

        {/* Quick Action: Re-index button */}
        <button
          onClick={() => activeRepo && onReindexRepo(activeRepo.id)}
          disabled={isIndexing || !activeRepo}
          title="Re-index current repository"
          className="p-1.5 bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg border border-slate-700/60 transition-all disabled:opacity-40"
        >
          <RefreshCw size={13} className={isIndexing ? 'animate-spin text-blue-400' : ''} />
        </button>

        {/* Quick Action: Import button */}
        <button
          onClick={onOpenImportModal}
          title="Import new repository"
          className="flex items-center space-x-1.5 text-xs bg-blue-600 hover:bg-blue-500 text-white px-2.5 py-1.5 rounded-lg font-medium shadow-sm transition-all"
        >
          <Plus size={13} />
          <span>Import</span>
        </button>
      </div>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute left-0 mt-2 w-80 rounded-xl bg-slate-900 border border-slate-800 shadow-2xl z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
          <div className="px-3 py-2.5 bg-slate-950/60 border-b border-slate-800 flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Repositories</span>
            <span className="text-[10px] text-slate-500 font-mono">{repositories.length} registered</span>
          </div>

          <div className="max-h-64 overflow-y-auto py-1 divide-y divide-slate-800/40">
            {repositories.length === 0 ? (
              <div className="p-4 text-center text-xs text-slate-500">
                No repositories available.
              </div>
            ) : (
              repositories.map((repo) => {
                const isSelected = repo.id === activeRepoId;
                const isConfirming = deleteConfirmId === repo.id;

                return (
                  <div
                    key={repo.id}
                    onClick={() => {
                      onSelectRepo(repo.id);
                      setIsOpen(false);
                      setDeleteConfirmId(null);
                    }}
                    className={`px-3 py-2.5 flex items-center justify-between cursor-pointer transition-colors ${
                      isSelected ? 'bg-blue-600/10 hover:bg-blue-600/15' : 'hover:bg-slate-800/50'
                    }`}
                  >
                    <div className="flex items-start space-x-2.5 min-w-0 flex-1">
                      <div className="mt-0.5">{renderSourceIcon(repo.source_type)}</div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center space-x-1.5">
                          <span className={`text-xs font-semibold truncate ${isSelected ? 'text-blue-300' : 'text-slate-200'}`}>
                            {repo.name}
                          </span>
                          {repo.is_demo && (
                            <span className="text-[9px] bg-slate-800 text-slate-400 px-1 rounded font-mono">
                              demo
                            </span>
                          )}
                        </div>
                        <div className="flex items-center space-x-2 mt-0.5">
                          {renderStatusBadge(repo.status)}
                          <span className="text-[10px] text-slate-500 font-mono">
                            {repo.stats?.files_scanned ? `${repo.stats.files_scanned} files` : 'no scan'}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center space-x-1.5 ml-2" onClick={(e) => e.stopPropagation()}>
                      {isSelected && (
                        <Check size={14} className="text-blue-400 mr-1 flex-shrink-0" />
                      )}

                      {/* Delete Action (Protected if Demo) */}
                      {!repo.is_demo && (
                        isConfirming ? (
                          <div className="flex items-center space-x-1 animate-in fade-in">
                            <button
                              onClick={(e) => handleConfirmDelete(repo.id, e)}
                              disabled={isDeleting}
                              className="px-2 py-0.5 bg-rose-600 hover:bg-rose-500 text-white text-[10px] font-semibold rounded"
                            >
                              {isDeleting ? <Loader2 size={10} className="animate-spin" /> : 'Confirm'}
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); setDeleteConfirmId(null); }}
                              className="px-1.5 py-0.5 bg-slate-800 text-slate-400 hover:text-white text-[10px] rounded"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={(e) => { e.stopPropagation(); setDeleteConfirmId(repo.id); }}
                            title="Delete repository and graph"
                            className="p-1 text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded transition-colors"
                          >
                            <Trash2 size={13} />
                          </button>
                        )
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Footer inside Dropdown */}
          <div className="p-2 bg-slate-950/60 border-t border-slate-800">
            <button
              onClick={() => {
                setIsOpen(false);
                onOpenImportModal();
              }}
              className="w-full flex items-center justify-center space-x-2 py-1.5 px-3 bg-slate-800 hover:bg-blue-600 text-slate-300 hover:text-white rounded-lg text-xs font-medium transition-colors"
            >
              <Plus size={13} />
              <span>Import New Repository...</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
