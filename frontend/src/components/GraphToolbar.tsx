// frontend/src/components/GraphToolbar.tsx - Layout & Navigation Toolbar for Cytoscape (ASTERION V3)

import React from 'react';
import {
  Maximize2,
  ZoomIn,
  ZoomOut,
  RefreshCw,
  Search,
  Filter,
  Layers
} from 'lucide-react';

export type GraphLayoutType = 'cose' | 'concentric' | 'breadthfirst' | 'circle';

interface GraphToolbarProps {
  currentLayout: GraphLayoutType;
  onChangeLayout: (layout: GraphLayoutType) => void;
  onFit: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onRelayout: () => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  selectedFilter: string;
  onFilterChange: (filter: string) => void;
}

export const GraphToolbar: React.FC<GraphToolbarProps> = ({
  currentLayout,
  onChangeLayout,
  onFit,
  onZoomIn,
  onZoomOut,
  onRelayout,
  searchQuery,
  onSearchChange,
  selectedFilter,
  onFilterChange
}) => {
  return (
    <div className="flex items-center space-x-2 bg-zinc-950/80 backdrop-blur-md border border-zinc-800/80 px-2.5 py-1.5 rounded-xl text-xs shadow-lg">
      {/* Node Search */}
      <div className="relative flex items-center">
        <Search size={12} className="absolute left-2 text-zinc-500" />
        <input
          type="text"
          placeholder="Filter graph nodes..."
          value={searchQuery}
          onChange={e => onSearchChange(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 focus:border-blue-500 rounded-lg pl-6 pr-2 py-1 text-[11px] font-mono text-zinc-200 placeholder-zinc-600 outline-none w-36 focus:w-48 transition-all"
        />
      </div>

      <div className="h-4 w-px bg-zinc-800" />

      {/* Type filter */}
      <div className="flex items-center space-x-1">
        <Filter size={11} className="text-zinc-500" />
        <select
          value={selectedFilter}
          onChange={e => onFilterChange(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-2 py-1 text-[11px] font-mono text-zinc-300 outline-none cursor-pointer"
        >
          <option value="ALL">All Types</option>
          <option value="FILE">Files</option>
          <option value="CLASS">Classes</option>
          <option value="FUNCTION">Functions</option>
        </select>
      </div>

      <div className="h-4 w-px bg-zinc-800" />

      {/* Layout selector */}
      <div className="flex items-center space-x-1">
        <Layers size={11} className="text-zinc-500" />
        <select
          value={currentLayout}
          onChange={e => onChangeLayout(e.target.value as GraphLayoutType)}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-2 py-1 text-[11px] font-mono text-zinc-300 outline-none cursor-pointer"
        >
          <option value="cose">Force-Directed (CoSE)</option>
          <option value="concentric">Concentric Rings</option>
          <option value="breadthfirst">Breadth-First (DAG)</option>
          <option value="circle">Circular</option>
        </select>
      </div>

      <div className="h-4 w-px bg-zinc-800" />

      {/* Canvas actions */}
      <div className="flex items-center space-x-1">
        <button
          onClick={onRelayout}
          title="Re-run Layout"
          className="p-1 rounded-md text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
        >
          <RefreshCw size={13} />
        </button>
        <button
          onClick={onFit}
          title="Fit to Screen"
          className="p-1 rounded-md text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
        >
          <Maximize2 size={13} />
        </button>
        <button
          onClick={onZoomIn}
          title="Zoom In"
          className="p-1 rounded-md text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
        >
          <ZoomIn size={13} />
        </button>
        <button
          onClick={onZoomOut}
          title="Zoom Out"
          className="p-1 rounded-md text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
        >
          <ZoomOut size={13} />
        </button>
      </div>
    </div>
  );
};
