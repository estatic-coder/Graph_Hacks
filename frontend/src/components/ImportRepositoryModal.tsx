import React, { useState, useRef } from 'react';
import { 
  X, 
  Upload, 
  FolderOpen, 
  Github, 
  Loader2, 
  CheckCircle2, 
  AlertCircle, 
  FileArchive, 
  ArrowRight,
  Database,
  Layers,
  Sparkles
} from 'lucide-react';

export interface RepositoryMetadata {
  id: string;
  name: string;
  source_type: 'local' | 'zip' | 'github';
  source_path: string;
  source_url?: string | null;
  created_at: string;
  last_indexed_at?: string | null;
  status: 'ready' | 'indexing' | 'error' | 'empty';
  error_message?: string | null;
  stats: {
    files_scanned?: number;
    symbols_extracted?: number;
    relationships_created?: number;
  };
  is_demo?: boolean;
}

interface ImportRepositoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportSuccess: (repo: RepositoryMetadata) => void;
}

type TabType = 'zip' | 'local' | 'github';

export const ImportRepositoryModal: React.FC<ImportRepositoryModalProps> = ({
  isOpen,
  onClose,
  onImportSuccess
}) => {
  const [activeTab, setActiveTab] = useState<TabType>('zip');
  
  // Form states
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [zipRepoName, setZipRepoName] = useState('');
  
  const [localPath, setLocalPath] = useState('');
  const [localRepoName, setLocalRepoName] = useState('');
  
  const [githubUrl, setGithubUrl] = useState('');
  const [githubBranch, setGithubBranch] = useState('');
  const [githubRepoName, setGithubRepoName] = useState('');
  
  // Status states
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [importedRepo, setImportedRepo] = useState<RepositoryMetadata | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  if (!isOpen) return null;

  const resetForm = () => {
    setZipFile(null);
    setZipRepoName('');
    setLocalPath('');
    setLocalRepoName('');
    setGithubUrl('');
    setGithubBranch('');
    setGithubRepoName('');
    setErrorMessage(null);
    setImportedRepo(null);
    setStatusMessage('');
  };

  const handleClose = () => {
    if (isSubmitting) return;
    resetForm();
    onClose();
  };

  const handleFileSelect = (file: File) => {
    if (!file.name.toLowerCase().endsWith('.zip')) {
      setErrorMessage('Please select a valid .zip archive.');
      return;
    }
    setZipFile(file);
    setErrorMessage(null);
    if (!zipRepoName) {
      const baseName = file.name.replace(/\.zip$/i, '').replace(/[^a-zA-Z0-9_-]/g, '-');
      setZipRepoName(baseName);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleUploadZip = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!zipFile) {
      setErrorMessage('Please select a ZIP file to upload.');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setStatusMessage('Uploading and safely extracting archive...');

    const formData = new FormData();
    formData.append('file', zipFile);
    if (zipRepoName.trim()) {
      formData.append('name', zipRepoName.trim());
    }

    try {
      const response = await fetch('http://localhost:8000/api/repositories/upload', {
        method: 'POST',
        body: formData
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Upload failed');
      }

      setStatusMessage('Indexing code entities and knowledge graph...');
      setImportedRepo(data.repository);
      onImportSuccess(data.repository);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to upload repository');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleImportLocal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!localPath.trim()) {
      setErrorMessage('Please enter the server directory path.');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setStatusMessage('Validating local directory and scanning files...');

    try {
      const response = await fetch('http://localhost:8000/api/repositories/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: localPath.trim(),
          name: localRepoName.trim() || undefined
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Import failed');
      }

      setImportedRepo(data.repository);
      onImportSuccess(data.repository);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to import local folder');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleImportGithub = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!githubUrl.trim()) {
      setErrorMessage('Please enter a GitHub repository URL.');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setStatusMessage('Cloning repository shallowly (max 45s)...');

    try {
      const response = await fetch('http://localhost:8000/api/repositories/github', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: githubUrl.trim(),
          branch: githubBranch.trim() || undefined,
          name: githubRepoName.trim() || undefined
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'GitHub clone failed');
      }

      setImportedRepo(data.repository);
      onImportSuccess(data.repository);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to clone GitHub repository');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in duration-200">
      <div 
        className="w-full max-w-xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="px-6 py-5 border-b border-slate-800/80 flex items-center justify-between bg-slate-900/60">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-blue-500/10 rounded-xl border border-blue-500/20 text-blue-400">
              <FolderOpen size={20} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-100">Import Repository</h2>
              <p className="text-xs text-slate-400">Connect and index code for graph-native intelligence</p>
            </div>
          </div>
          <button 
            onClick={handleClose}
            disabled={isSubmitting}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 rounded-lg transition-colors disabled:opacity-50"
          >
            <X size={18} />
          </button>
        </div>

        {/* Success State */}
        {importedRepo ? (
          <div className="p-8 flex flex-col items-center text-center space-y-6">
            <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <CheckCircle2 size={32} />
            </div>
            <div className="space-y-1">
              <h3 className="text-lg font-bold text-white">Repository Imported & Ready!</h3>
              <p className="text-xs text-slate-400 font-mono">
                {importedRepo.name} ({importedRepo.id})
              </p>
            </div>

            {/* Quick Stats Grid */}
            <div className="w-full grid grid-cols-3 gap-3 bg-slate-950/60 border border-slate-800 rounded-xl p-4">
              <div className="flex flex-col items-center">
                <span className="text-[11px] text-slate-500 uppercase tracking-wider font-semibold">Files</span>
                <span className="text-base font-bold text-slate-200 mt-0.5">
                  {importedRepo.stats?.files_scanned ?? 0}
                </span>
              </div>
              <div className="flex flex-col items-center border-x border-slate-800">
                <span className="text-[11px] text-slate-500 uppercase tracking-wider font-semibold">Symbols</span>
                <span className="text-base font-bold text-blue-400 mt-0.5">
                  {importedRepo.stats?.symbols_extracted ?? 0}
                </span>
              </div>
              <div className="flex flex-col items-center">
                <span className="text-[11px] text-slate-500 uppercase tracking-wider font-semibold">Edges</span>
                <span className="text-base font-bold text-indigo-400 mt-0.5">
                  {importedRepo.stats?.relationships_created ?? 0}
                </span>
              </div>
            </div>

            <div className="flex items-center space-x-3 w-full">
              <button
                onClick={handleClose}
                className="flex-1 py-2.5 px-4 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-xl shadow-lg shadow-blue-500/20 flex items-center justify-center space-x-2 transition-all"
              >
                <span>View Knowledge Graph</span>
                <ArrowRight size={14} />
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Tab Selectors */}
            <div className="flex border-b border-slate-800 bg-slate-950/40 px-6 pt-3 space-x-4">
              <button
                onClick={() => { setActiveTab('zip'); setErrorMessage(null); }}
                disabled={isSubmitting}
                className={`flex items-center space-x-2 pb-3 text-xs font-medium border-b-2 transition-all ${
                  activeTab === 'zip'
                    ? 'border-blue-500 text-blue-400'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <FileArchive size={14} />
                <span>ZIP Archive</span>
              </button>
              <button
                onClick={() => { setActiveTab('local'); setErrorMessage(null); }}
                disabled={isSubmitting}
                className={`flex items-center space-x-2 pb-3 text-xs font-medium border-b-2 transition-all ${
                  activeTab === 'local'
                    ? 'border-blue-500 text-blue-400'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <FolderOpen size={14} />
                <span>Local Folder</span>
              </button>
              <button
                onClick={() => { setActiveTab('github'); setErrorMessage(null); }}
                disabled={isSubmitting}
                className={`flex items-center space-x-2 pb-3 text-xs font-medium border-b-2 transition-all ${
                  activeTab === 'github'
                    ? 'border-blue-500 text-blue-400'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <Github size={14} />
                <span>GitHub</span>
              </button>
            </div>

            {/* Error Banner */}
            {errorMessage && (
              <div className="mx-6 mt-4 p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl flex items-start space-x-2.5 text-rose-300 text-xs">
                <AlertCircle size={16} className="text-rose-400 flex-shrink-0 mt-0.5" />
                <span className="leading-relaxed">{errorMessage}</span>
              </div>
            )}

            {/* Tab Contents */}
            <div className="p-6">
              {activeTab === 'zip' && (
                <form onSubmit={handleUploadZip} className="space-y-4">
                  {/* Dropzone */}
                  <div
                    onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                    onDragLeave={() => setIsDragOver(false)}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                    className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all flex flex-col items-center justify-center space-y-2 ${
                      isDragOver 
                        ? 'border-blue-500 bg-blue-500/5' 
                        : zipFile 
                        ? 'border-emerald-500/40 bg-emerald-500/5' 
                        : 'border-slate-800 hover:border-slate-700 bg-slate-950/30'
                    }`}
                  >
                    <input 
                      type="file" 
                      ref={fileInputRef} 
                      onChange={(e) => e.target.files && handleFileSelect(e.target.files[0])}
                      accept=".zip" 
                      className="hidden" 
                    />
                    <div className="p-3 bg-slate-800 rounded-full text-slate-400">
                      {zipFile ? <CheckCircle2 size={24} className="text-emerald-400" /> : <Upload size={24} className="text-blue-400" />}
                    </div>
                    {zipFile ? (
                      <div className="space-y-0.5">
                        <p className="text-xs font-semibold text-white">{zipFile.name}</p>
                        <p className="text-[10px] text-slate-400 font-mono">
                          {(zipFile.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        <p className="text-xs font-medium text-slate-300">
                          Click to select or drag and drop a <span className="text-blue-400">.zip</span> archive
                        </p>
                        <p className="text-[10px] text-slate-500">
                          ZipSlip and ZipBomb protection enabled (max 50 MB)
                        </p>
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-slate-400 mb-1">
                      Repository Display Name (optional)
                    </label>
                    <input
                      type="text"
                      value={zipRepoName}
                      onChange={(e) => setZipRepoName(e.target.value)}
                      placeholder="e.g. backend-api"
                      disabled={isSubmitting}
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500 transition-colors"
                    />
                  </div>

                  <div className="pt-2 flex justify-end space-x-3">
                    <button
                      type="button"
                      onClick={handleClose}
                      disabled={isSubmitting}
                      className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={!zipFile || isSubmitting}
                      className="flex items-center space-x-2 px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-semibold rounded-xl shadow-lg shadow-blue-500/20 transition-all"
                    >
                      {isSubmitting ? (
                        <>
                          <Loader2 size={14} className="animate-spin" />
                          <span>{statusMessage || 'Processing...'}</span>
                        </>
                      ) : (
                        <>
                          <Upload size={14} />
                          <span>Upload & Index</span>
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}

              {activeTab === 'local' && (
                <form onSubmit={handleImportLocal} className="space-y-4">
                  <div>
                    <label className="block text-[11px] font-medium text-slate-400 mb-1">
                      Absolute Server Path <span className="text-rose-400">*</span>
                    </label>
                    <input
                      type="text"
                      value={localPath}
                      onChange={(e) => setLocalPath(e.target.value)}
                      placeholder="/home/zeraphynx/Projects/asterion/sample-repo"
                      disabled={isSubmitting}
                      required
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-white font-mono placeholder-slate-600 focus:outline-none focus:border-blue-500 transition-colors"
                    />
                    <p className="text-[10px] text-slate-500 mt-1">
                      Specify an accessible directory path on the host filesystem.
                    </p>
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-slate-400 mb-1">
                      Repository Display Name (optional)
                    </label>
                    <input
                      type="text"
                      value={localRepoName}
                      onChange={(e) => setLocalRepoName(e.target.value)}
                      placeholder="e.g. sample-repo"
                      disabled={isSubmitting}
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500 transition-colors"
                    />
                  </div>

                  <div className="pt-2 flex justify-end space-x-3">
                    <button
                      type="button"
                      onClick={handleClose}
                      disabled={isSubmitting}
                      className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={!localPath.trim() || isSubmitting}
                      className="flex items-center space-x-2 px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-semibold rounded-xl shadow-lg shadow-blue-500/20 transition-all"
                    >
                      {isSubmitting ? (
                        <>
                          <Loader2 size={14} className="animate-spin" />
                          <span>{statusMessage || 'Importing...'}</span>
                        </>
                      ) : (
                        <>
                          <FolderOpen size={14} />
                          <span>Import & Index</span>
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}

              {activeTab === 'github' && (
                <form onSubmit={handleImportGithub} className="space-y-4">
                  <div>
                    <label className="block text-[11px] font-medium text-slate-400 mb-1">
                      GitHub Repository URL <span className="text-rose-400">*</span>
                    </label>
                    <input
                      type="url"
                      value={githubUrl}
                      onChange={(e) => setGithubUrl(e.target.value)}
                      placeholder="https://github.com/fastapi/fastapi.git"
                      disabled={isSubmitting}
                      required
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500 transition-colors"
                    />
                    <p className="text-[10px] text-slate-500 mt-1">
                      Performs a shallow clone (<code className="text-slate-400">--depth 1</code>) with a 45-second timeout.
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-medium text-slate-400 mb-1">
                        Branch / Tag (optional)
                      </label>
                      <input
                        type="text"
                        value={githubBranch}
                        onChange={(e) => setGithubBranch(e.target.value)}
                        placeholder="main"
                        disabled={isSubmitting}
                        className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500 transition-colors"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-slate-400 mb-1">
                        Display Name (optional)
                      </label>
                      <input
                        type="text"
                        value={githubRepoName}
                        onChange={(e) => setGithubRepoName(e.target.value)}
                        placeholder="fastapi"
                        disabled={isSubmitting}
                        className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-blue-500 transition-colors"
                      />
                    </div>
                  </div>

                  <div className="pt-2 flex justify-end space-x-3">
                    <button
                      type="button"
                      onClick={handleClose}
                      disabled={isSubmitting}
                      className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={!githubUrl.trim() || isSubmitting}
                      className="flex items-center space-x-2 px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-semibold rounded-xl shadow-lg shadow-blue-500/20 transition-all"
                    >
                      {isSubmitting ? (
                        <>
                          <Loader2 size={14} className="animate-spin" />
                          <span>{statusMessage || 'Cloning...'}</span>
                        </>
                      ) : (
                        <>
                          <Github size={14} />
                          <span>Clone & Index</span>
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};
