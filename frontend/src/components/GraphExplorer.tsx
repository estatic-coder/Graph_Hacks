import React, { useEffect, useRef, useState, useCallback } from 'react';
import cytoscape from 'cytoscape';
import { Network, Loader2, GitMerge } from 'lucide-react';
import { GraphToolbar, GraphLayoutType } from './GraphToolbar';

interface GraphExplorerProps {
  repoId: string;
  onNodeSelect: (nodeData: any) => void;
  affectedNodeIds?: string[];
  focusedNodeName?: string;
}

const GraphExplorer: React.FC<GraphExplorerProps> = ({
  repoId,
  onNodeSelect,
  affectedNodeIds,
  focusedNodeName
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [nodeCount, setNodeCount] = useState<number | null>(null);
  const [edgeCount, setEdgeCount] = useState<number | null>(null);
  const [currentLayout, setCurrentLayout] = useState<GraphLayoutType>('cose');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [filterType, setFilterType] = useState<string>('ALL');


  useEffect(() => {
    if (!containerRef.current) return;

    cyRef.current = cytoscape({
      container: containerRef.current,
      style: [
        /* ── Default / unknown ───────────────────────────── */
        {
          selector: 'node',
          style: {
            'background-color': '#111318',
            'background-opacity': 1,
            'label': 'data(name)',
            'color': '#64748b',
            'font-family': 'Inter, system-ui, sans-serif',
            'font-size': '10px',
            'font-weight': '400',
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-margin-y': 6,
            'text-max-width': '100px',
            'text-wrap': 'ellipsis',
            'border-width': 1,
            'border-color': '#2a2e3a',
            'border-opacity': 1,
            'width': 26,
            'height': 26,
            'transition-property': 'background-color, border-color, border-width, width, height',
            'transition-duration': '0.15s' as any,
          }
        },
        /* ── Repository — bright white ───────────────────── */
        {
          selector: 'node.repository',
          style: {
            'background-color': '#1c1e24',
            'border-color': '#e2e8f0',
            'border-width': 2,
            'width': 50,
            'height': 50,
            'color': '#f8fafc',
            'font-size': '11px',
            'font-weight': '600',
          }
        },
        /* ── File — light grey, round-rect ───────────────── */
        {
          selector: 'node.file',
          style: {
            'background-color': '#141720',
            'border-color': '#94a3b8',
            'border-width': 1.5,
            'shape': 'round-rectangle',
            'width': 36,
            'height': 36,
            'color': '#94a3b8',
          }
        },
        /* ── Class — mid grey, hexagon ───────────────────── */
        {
          selector: 'node.class',
          style: {
            'background-color': '#0f1117',
            'border-color': '#64748b',
            'border-width': 1.5,
            'shape': 'hexagon',
            'width': 36,
            'height': 36,
            'color': '#64748b',
          }
        },
        /* ── Function — dim grey, circle ─────────────────── */
        {
          selector: 'node.function',
          style: {
            'background-color': '#0c0e13',
            'border-color': '#475569',
            'border-width': 1,
            'width': 24,
            'height': 24,
            'color': '#475569',
          }
        },
        /* ── Endpoint — dark diamond ──────────────────────── */
        {
          selector: 'node.endpoint',
          style: {
            'background-color': '#0e1016',
            'border-color': '#334155',
            'border-width': 1.5,
            'shape': 'diamond',
            'width': 38,
            'height': 38,
            'color': '#475569',
          }
        },
        /* ── Tap overlay ─────────────────────────────────── */
        {
          selector: 'node:active',
          style: {
            'overlay-color': '#e2e8f0',
            'overlay-padding': 6,
            'overlay-opacity': 0.1,
          }
        },
        /* ── Selected — white ring ───────────────────────── */
        {
          selector: ':selected',
          style: {
            'border-width': 2,
            'border-color': '#e2e8f0',
            'background-color': '#1e2028',
            'color': '#f8fafc',
            'overlay-color': '#e2e8f0',
            'overlay-padding': 8,
            'overlay-opacity': 0.08,
          }
        },
        /* ── Impacted — light grey pulse ─────────────────── */
        {
          selector: 'node.impacted',
          style: {
            'border-width': 2,
            'border-color': '#cbd5e1',
            'background-color': '#1a1d24',
            'overlay-color': '#cbd5e1',
            'overlay-padding': 10,
            'overlay-opacity': 0.12,
            'color': '#cbd5e1',
          }
        },
        /* ── Changed — near-white alarm ──────────────────── */
        {
          selector: 'node.changed',
          style: {
            'border-width': 2.5,
            'border-color': '#f1f5f9',
            'background-color': '#1e2028',
            'overlay-color': '#f1f5f9',
            'overlay-padding': 10,
            'overlay-opacity': 0.15,
            'color': '#f8fafc',
          }
        },
        /* ── Edges ───────────────────────────────────────── */
        {
          selector: 'edge',
          style: {
            'width': 1,
            'line-color': '#1e2330',
            'line-style': 'solid',
            'target-arrow-color': '#2a3040',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 0.6,
            'curve-style': 'bezier',
            'label': 'data(label)',
            'font-size': '8px',
            'font-family': 'JetBrains Mono, monospace',
            'color': '#2a3040',
            'text-rotation': 'autorotate',
            'text-background-opacity': 1,
            'text-background-color': '#000000',
            'text-background-padding': '2px',
            'text-border-opacity': 0,
            'opacity': 0.7,
            'transition-property': 'opacity, line-color, width',
            'transition-duration': '0.15s' as any,
          }
        },
        /* ── Differentiated Edge Styles ───────────────────── */
        {
          selector: 'edge.calls, edge.edge-calls',
          style: {
            'width': 1.5,
            'line-color': '#2563eb',
            'target-arrow-color': '#3b82f6',
            'opacity': 0.85,
            'color': '#60a5fa',
          }
        },
        {
          selector: 'edge.feasible',
          style: {
            'width': 2,
            'line-color': '#10b981',
            'target-arrow-color': '#10b981',
            'opacity': 0.95,
            'color': '#34d399',
          }
        },
        {
          selector: 'edge.infeasible',
          style: {
            'width': 1.5,
            'line-color': '#f43f5e',
            'target-arrow-color': '#f43f5e',
            'line-style': 'dashed',
            'opacity': 0.75,
            'color': '#fb7185',
          }
        },
        {
          selector: 'edge.state-transition, edge.state_transition',
          style: {
            'width': 1.5,
            'line-color': '#a855f7',
            'target-arrow-color': '#c084fc',
            'line-style': 'dotted',
            'opacity': 0.9,
            'color': '#c084fc',
          }
        },
        {
          selector: 'edge.imports, edge.edge-imports',
          style: {
            'width': 1,
            'line-color': '#1e293b',
            'target-arrow-color': '#334155',
            'opacity': 0.45,
            'color': '#334155',
          }
        },
        {
          selector: 'edge.contains, edge.edge-contains',
          style: {
            'width': 1,
            'line-color': '#172554',
            'target-arrow-color': '#1e3a8a',
            'opacity': 0.35,
            'color': '#1e3a8a',
          }
        },
        /* ── Selected edge ───────────────────────────────── */
        {
          selector: 'edge:selected',
          style: {
            'line-color': '#94a3b8',
            'target-arrow-color': '#94a3b8',
            'width': 2,
            'opacity': 1,
            'color': '#e2e8f0',
          }
        },
      ],
      layout: { name: 'cose', animate: false, randomize: true }
    });

    cyRef.current.on('tap', 'node', (evt) => {
      onNodeSelect(evt.target.data());
    });

    const handleResize = () => {
      if (cyRef.current) {
        cyRef.current.resize();
        cyRef.current.fit(undefined, 48);
      }
    };
    window.addEventListener('resize', handleResize);

    const ro = new ResizeObserver(() => {
      if (cyRef.current) {
        cyRef.current.resize();
      }
    });
    if (containerRef.current) {
      ro.observe(containerRef.current);
    }

    return () => {
      window.removeEventListener('resize', handleResize);
      ro.disconnect();
      cyRef.current?.destroy();
    };
  }, [onNodeSelect]);

  /* ── Load graph data ──────────────────────────────────────── */
  useEffect(() => {
    if (!cyRef.current || !repoId) return;

    setIsLoading(true);
    fetch(`http://localhost:8000/api/graph/${repoId}`)
      .then(res => res.json())
      .then(data => {
        if (!cyRef.current) return;
        cyRef.current.elements().remove();

        if (data.elements && data.elements.length > 0) {
          cyRef.current.add(data.elements);

          const layout = cyRef.current.layout({
            name: 'cose',
            animate: false,
            idealEdgeLength: () => 90,
            nodeRepulsion: () => 6000,
            nodeOverlap: 20,
            gravity: 0.8,
            numIter: 1200,
            fit: true,
            padding: 48,
          } as any);

          layout.on('layoutstop', () => {
            /* Auto-fit with 48px padding so nothing clips */
            cyRef.current?.fit(undefined, 48);
            cyRef.current?.zoom({ level: Math.min(cyRef.current.zoom(), 1.2) });
          });

          layout.run();

          const nodes = data.elements.filter((el: any) => !el.data.source);
          const edges = data.elements.filter((el: any) =>  el.data.source);
          setNodeCount(nodes.length);
          setEdgeCount(edges.length);
        } else {
          setNodeCount(0);
          setEdgeCount(0);
        }
      })
      .catch(err => {
        console.error('Failed to load graph', err);
        cyRef.current?.elements().remove();
        setNodeCount(0);
        setEdgeCount(0);
      })
      .finally(() => setIsLoading(false));
  }, [repoId]);

  /* ── Highlight impacted nodes ─────────────────────────────── */
  useEffect(() => {
    if (!cyRef.current) return;
    cyRef.current.nodes().removeClass('impacted changed');
    affectedNodeIds?.forEach(id => {
      const node = cyRef.current?.$(`node[id = "${id}"]`);
      if (node?.length) node.addClass('impacted');
    });
  }, [affectedNodeIds]);

  /* ── Layout switching function ─────────────────────────────── */
  const runLayout = useCallback((layoutName: GraphLayoutType) => {
    if (!cyRef.current) return;
    const layoutConfig: any = {
      name: layoutName,
      animate: true,
      animationDuration: 400,
      fit: true,
      padding: 48,
    };
    if (layoutName === 'cose') {
      layoutConfig.idealEdgeLength = () => 90;
      layoutConfig.nodeRepulsion = () => 6000;
      layoutConfig.gravity = 0.8;
      layoutConfig.numIter = 1000;
    } else if (layoutName === 'concentric') {
      layoutConfig.concentric = (node: any) => {
        const lbl = node.data('label');
        if (lbl === 'Repository') return 4;
        if (lbl === 'File') return 3;
        if (lbl === 'Class') return 2;
        return 1;
      };
      layoutConfig.levelWidth = () => 1;
    } else if (layoutName === 'breadthfirst') {
      layoutConfig.directed = true;
      layoutConfig.spacingFactor = 1.2;
    }
    const layout = cyRef.current.layout(layoutConfig);
    layout.run();
  }, []);

  /* ── Dynamic search & type filtering ──────────────────────── */
  useEffect(() => {
    if (!cyRef.current) return;
    const q = searchQuery.trim().toLowerCase();
    cyRef.current.batch(() => {
      cyRef.current?.nodes().forEach(node => {
        const d = node.data();
        const matchesName = !q || (d.name && d.name.toLowerCase().includes(q));
        const matchesType = filterType === 'ALL' || (d.label && d.label.toUpperCase() === filterType);
        if (matchesName && matchesType) {
          node.style('opacity', '1');
        } else {
          node.style('opacity', '0.15');
        }
      });
    });
  }, [searchQuery, filterType]);

  /* ── Focus on node when requested ─────────────────────────── */
  useEffect(() => {
    if (!cyRef.current || !focusedNodeName) return;
    const target = cyRef.current.nodes().filter(n => n.data('name') === focusedNodeName || n.data('id') === focusedNodeName);
    if (target.length > 0) {
      cyRef.current.animate({
        center: { eles: target },
        zoom: 1.4,
        duration: 350
      });
      target.select();
      onNodeSelect(target.data());
    }
  }, [focusedNodeName, onNodeSelect]);

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        position: 'relative',
        background: '#000000',
        overflow: 'hidden',
      }}
    >
      {/* Pure dot-grid — very subtle */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(circle, #1e2330 1px, transparent 1px)',
          backgroundSize: '32px 32px',
          opacity: 0.6,
        }}
      />

      {/* Cytoscape canvas fills parent completely */}
      <div
        ref={containerRef}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          width: '100%',
          height: '100%',
        }}
      />

      {/* ── Status pill ─────────────────────────────────── */}
      <div className="absolute top-3 left-3 z-10">
        <div
          className="flex items-center space-x-2 px-2.5 py-1.5 rounded-lg"
          style={{
            background: 'rgba(0,0,0,0.75)',
            border: '1px solid #1e2330',
            backdropFilter: 'blur(12px)',
          }}
        >
          <GitMerge size={11} style={{ color: '#475569' }} />
          <span style={{ fontSize: '10px', fontFamily: 'JetBrains Mono, monospace', color: '#475569', letterSpacing: '0.1em' }}>
            GRAPH
          </span>
          {nodeCount !== null && !isLoading && (
            <span style={{ fontSize: '10px', fontFamily: 'JetBrains Mono, monospace', color: '#334155' }}>
              {nodeCount}N · {edgeCount ?? 0}E
            </span>
          )}
        </div>
      </div>

      {/* ── Graph Toolbar ───────────────────────────────── */}
      {!isLoading && nodeCount !== null && nodeCount > 0 && (
        <div className="absolute top-3 right-3 z-10">
          <GraphToolbar
            currentLayout={currentLayout}
            onChangeLayout={layout => {
              setCurrentLayout(layout);
              runLayout(layout);
            }}
            onFit={() => cyRef.current?.fit(undefined, 48)}
            onZoomIn={() => cyRef.current && cyRef.current.zoom(cyRef.current.zoom() * 1.2)}
            onZoomOut={() => cyRef.current && cyRef.current.zoom(cyRef.current.zoom() * 0.8)}
            onRelayout={() => runLayout(currentLayout)}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            selectedFilter={filterType}
            onFilterChange={setFilterType}
          />
        </div>
      )}



      {/* ── Loading overlay ──────────────────────────────── */}
      {isLoading && (
        <div
          className="absolute inset-0 flex flex-col items-center justify-center z-20 pointer-events-none"
          style={{ background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(6px)' }}
        >
          <Loader2 className="w-5 h-5 animate-spin" style={{ color: '#475569' }} />
          <p style={{ marginTop: '12px', fontSize: '11px', fontFamily: 'JetBrains Mono, monospace', color: '#334155' }}>
            building graph…
          </p>
        </div>
      )}

      {/* ── Empty state ──────────────────────────────────── */}
      {!isLoading && nodeCount === 0 && (
        <div className="absolute inset-0 flex flex-col items-center justify-center z-10 pointer-events-none p-6 text-center">
          <Network size={28} style={{ color: '#1e2330', marginBottom: '16px' }} />
          <p style={{ fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>No Graph Available</p>
          <p style={{ fontSize: '11px', color: '#1e2330', maxWidth: '240px', lineHeight: 1.6 }}>
            Index this repository to generate the knowledge graph.
          </p>
        </div>
      )}
    </div>
  );
};

export default GraphExplorer;
