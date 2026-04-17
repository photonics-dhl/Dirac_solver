import { useCallback, useEffect, useState, useMemo } from 'react';
import {
    ReactFlow,
    Background,
    Controls,
    type Node,
    type Edge,
    MarkerType,
    Position,
    Handle,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import axios from 'axios';

const ENV_API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/$/, '');
const API_BASE = ENV_API_BASE || '';

// ─── Types ───────────────────────────────────────────────────────

interface SubTaskGraph {
    currentNode: string;
    nodes: { id: string; label: string; mode: string; isCheckpoint?: boolean }[];
    edges: { from: string; to: string; condition?: string }[];
}

interface ProjectTask {
    id: string;
    label: string;
    status: 'pending' | 'in-progress' | 'done' | 'blocked';
    progress: number;
}

interface DevState {
    currentNode: string;
    mode: string;
    taskName: string;
    taskStatus: string;
    history: { node: string; timestamp: string; duration: string }[];
    logs: string[];
    graphDefinition: {
        nodes: { id: string; label: string; mode: string; isCheckpoint?: boolean }[];
        edges: { from: string; to: string; condition?: string }[];
    };
    projectGraph?: {
        tasks: ProjectTask[];
        dependencies: { from: string; to: string }[];
    };
    subTaskGraphs?: Record<string, SubTaskGraph>;
    activeSubTask?: string | null;
    nodeResults?: Record<string, Record<string, any>>;
    userFeedback: {
        instruction: string;
        targetNode: string;
        timestamp: string;
    };
}

type ViewMode = 'devflow' | 'project' | 'subtask';

// ─── Color palettes ──────────────────────────────────────────────

const MODE_COLORS: Record<string, { bg: string; border: string; glow: string }> = {
    PLANNING: { bg: '#1e1b4b', border: '#6366f1', glow: '0 0 20px rgba(99,102,241,0.4)' },
    EXECUTION: { bg: '#052e16', border: '#22c55e', glow: '0 0 20px rgba(34,197,94,0.4)' },
    VERIFICATION: { bg: '#431407', border: '#f97316', glow: '0 0 20px rgba(249,115,22,0.4)' },
};

const STATUS_COLORS: Record<string, { bg: string; border: string; text: string }> = {
    'pending': { bg: '#18181b', border: '#27272a', text: '#6b7280' },
    'in-progress': { bg: '#052e16', border: '#22c55e', text: '#4ade80' },
    'done': { bg: '#1a1a2e', border: '#4b5563', text: '#9ca3af' },
    'blocked': { bg: '#2a0a0a', border: '#991b1b', text: '#fca5a5' },
};

// ─── Custom Node: Dev Flow Node ──────────────────────────────────

function FlowNode({ data }: { data: any }) {
    const isActive = data.isActive;
    const isCompleted = data.isCompleted;
    const modeColor = MODE_COLORS[data.mode] || MODE_COLORS.PLANNING;

    const borderColor = isActive ? modeColor.border : isCompleted ? '#4b5563' : '#27272a';
    const bgColor = isActive ? modeColor.bg : isCompleted ? '#1a1a1e' : '#111113';
    const glow = isActive ? modeColor.glow : 'none';
    const opacity = !isActive && !isCompleted ? 0.5 : 1;

    return (
        <div style={{
            background: bgColor, border: `2px solid ${borderColor}`, borderRadius: '12px',
            padding: '14px 22px', color: '#e5e7eb', fontSize: '13px', fontWeight: 500,
            textAlign: 'center', boxShadow: glow, opacity, transition: 'all 0.4s ease',
            minWidth: '160px', position: 'relative',
        }}>
            <Handle type="target" position={Position.Top} style={{ background: '#555', border: 'none', width: 8, height: 8 }} />
            <div style={{
                position: 'absolute', top: -10, right: -10, background: modeColor.border,
                color: '#fff', fontSize: '9px', fontWeight: 700, padding: '2px 7px',
                borderRadius: '6px', letterSpacing: '0.5px', opacity: isActive ? 1 : 0.4,
            }}>{data.mode}</div>
            {data.isCheckpoint && <span style={{ marginRight: 6, fontSize: '14px' }}>⏸</span>}
            {isActive && <span style={{
                position: 'absolute', top: 7, left: 10, width: 8, height: 8,
                borderRadius: '50%', background: modeColor.border, animation: 'pulse 1.5s infinite',
            }} />}
            {isCompleted && !isActive && <span style={{ marginRight: 6, color: '#6b7280', fontSize: '14px' }}>✓</span>}
            {data.label}
            <Handle type="source" position={Position.Bottom} style={{ background: '#555', border: 'none', width: 8, height: 8 }} />
        </div>
    );
}

// ─── Custom Node: Project Task Node ──────────────────────────────

function ProjectNode({ data }: { data: any }) {
    const sc = STATUS_COLORS[data.status] || STATUS_COLORS.pending;
    const isActive = data.status === 'in-progress';

    return (
        <div style={{
            background: sc.bg, border: `2px solid ${sc.border}`, borderRadius: '14px',
            padding: '16px 24px', color: '#e5e7eb', fontSize: '13px', fontWeight: 500,
            textAlign: 'center', minWidth: '200px', position: 'relative',
            boxShadow: isActive ? `0 0 20px ${sc.border}40` : 'none',
            transition: 'all 0.4s ease', cursor: 'pointer',
        }} title="Click to drill down">
            <Handle type="target" position={Position.Top} style={{ background: '#555', border: 'none', width: 8, height: 8 }} />

            {/* Task ID badge */}
            <div style={{
                position: 'absolute', top: -10, left: -10,
                background: isActive ? '#22c55e' : '#3f3f46', color: '#fff',
                fontSize: '10px', fontWeight: 700, padding: '2px 8px', borderRadius: '6px',
            }}>{data.taskId}</div>

            {/* Status badge */}
            <div style={{
                position: 'absolute', top: -10, right: -10,
                background: sc.border, color: '#fff',
                fontSize: '9px', fontWeight: 700, padding: '2px 7px',
                borderRadius: '6px', letterSpacing: '0.5px',
            }}>{data.status}</div>

            <div style={{ marginBottom: 8 }}>{data.label}</div>

            {/* Progress bar */}
            <div style={{
                width: '100%', height: 4, background: '#27272a', borderRadius: 2, overflow: 'hidden',
            }}>
                <div style={{
                    width: `${data.progress}%`, height: '100%',
                    background: data.progress === 100 ? '#4b5563' : '#22c55e',
                    borderRadius: 2, transition: 'width 0.6s ease',
                }} />
            </div>
            <div style={{ fontSize: '10px', color: '#6b7280', marginTop: 4 }}>{data.progress}%</div>

            <Handle type="source" position={Position.Bottom} style={{ background: '#555', border: 'none', width: 8, height: 8 }} />
        </div>
    );
}

const nodeTypes = { flowNode: FlowNode, projectNode: ProjectNode };

// ─── Layout: auto-position nodes in a DAG-like vertical layout ───

function layoutNodes(
    nodeIds: string[],
    edges: { from: string; to: string }[],
    includeStartEnd: boolean,
): Record<string, { x: number; y: number }> {
    // Topological sort for layering
    const adj: Record<string, string[]> = {};
    const inDeg: Record<string, number> = {};
    const allIds = includeStartEnd ? ['START', ...nodeIds, 'END'] : [...nodeIds];
    allIds.forEach(id => { adj[id] = []; inDeg[id] = 0; });
    edges.forEach(e => {
        if (adj[e.from]) adj[e.from].push(e.to);
        if (inDeg[e.to] !== undefined) inDeg[e.to]++;
    });

    const layers: string[][] = [];
    let queue = allIds.filter(id => inDeg[id] === 0);
    while (queue.length > 0) {
        layers.push([...queue]);
        const next: string[] = [];
        queue.forEach(n => {
            (adj[n] || []).forEach(m => {
                inDeg[m]--;
                if (inDeg[m] === 0) next.push(m);
            });
        });
        queue = next;
    }

    const positions: Record<string, { x: number; y: number }> = {};
    const xSpacing = 250;
    const ySpacing = 120;
    layers.forEach((layer, li) => {
        const totalWidth = (layer.length - 1) * xSpacing;
        const startX = 350 - totalWidth / 2;
        layer.forEach((id, ni) => {
            positions[id] = { x: startX + ni * xSpacing, y: li * ySpacing + 30 };
        });
    });
    return positions;
}

// ─── Main Component ──────────────────────────────────────────────

export default function DevFlowDashboard() {
    const [devState, setDevState] = useState<DevState | null>(null);
    const [viewMode, setViewMode] = useState<ViewMode>('project');
    const [activeSubTaskId, setActiveSubTaskId] = useState<string | null>(null);
    const [sidePanelWidth, setSidePanelWidth] = useState(340);
    const [inspectorHeight, setInspectorHeight] = useState(160);
    const [feedbackInput, setFeedbackInput] = useState('');
    const [feedbackStatus, setFeedbackStatus] = useState('');

    const fetchState = useCallback(async () => {
        try {
            const res = await axios.get(`${API_BASE}/api/dev-state`);
            setDevState(res.data);
        } catch { /* backend offline */ }
    }, []);

    useEffect(() => {
        fetchState();
        const interval = setInterval(fetchState, 2000);
        return () => clearInterval(interval);
    }, [fetchState]);

    const sendFeedback = async (instruction: string, targetNode?: string) => {
        try {
            await axios.post(`${API_BASE}/api/dev-state/feedback`, {
                instruction, targetNode: targetNode || '',
            });
            setFeedbackStatus('✓ Sent');
            setFeedbackInput('');
            setTimeout(() => setFeedbackStatus(''), 2000);
            fetchState();
        } catch { setFeedbackStatus('✗ Failed'); }
    };

    // ─── Build graph data based on viewMode ──────────────────────

    const { flowNodes, flowEdges } = useMemo(() => {
        if (!devState) return { flowNodes: [] as Node[], flowEdges: [] as Edge[] };

        if (viewMode === 'project' && devState.projectGraph) {
            // ── Project Overview Graph ──
            const pg = devState.projectGraph;
            const positions = layoutNodes(
                pg.tasks.map(t => t.id),
                pg.dependencies,
                true,
            );

            const nodes: Node[] = [
                {
                    id: 'START', position: positions.START || { x: 350, y: 0 },
                    data: { label: 'START' }, type: 'input',
                    style: {
                        background: '#18181b', border: '2px solid #3f3f46', borderRadius: '50%',
                        width: 60, height: 60, display: 'flex', alignItems: 'center',
                        justifyContent: 'center', color: '#a1a1aa', fontSize: '11px', fontWeight: 700,
                    },
                },
                ...pg.tasks.map(t => ({
                    id: t.id, position: positions[t.id] || { x: 0, y: 0 },
                    type: 'projectNode' as const,
                    data: { label: t.label, taskId: t.id, status: t.status, progress: t.progress },
                })),
                {
                    id: 'END', position: positions.END || { x: 350, y: 800 },
                    data: { label: 'END' }, type: 'output',
                    style: {
                        background: '#18181b', border: '2px solid #3f3f46', borderRadius: '50%',
                        width: 60, height: 60, display: 'flex', alignItems: 'center',
                        justifyContent: 'center', color: '#a1a1aa', fontSize: '11px', fontWeight: 700,
                    },
                },
            ];

            // Add START edges to tasks with no upstream dependency
            const hasUpstream = new Set(pg.dependencies.map(d => d.to));
            const startEdges: Edge[] = pg.tasks
                .filter(t => !hasUpstream.has(t.id))
                .map((t) => ({
                    id: `start-${t.id}`, source: 'START', target: t.id,
                    style: { stroke: '#4b5563', strokeWidth: 1.5 },
                    markerEnd: { type: MarkerType.ArrowClosed, color: '#4b5563', width: 14, height: 14 },
                }));

            // Add END edges from tasks with no downstream dependency
            const hasDownstream = new Set(pg.dependencies.map(d => d.from));
            const endEdges: Edge[] = pg.tasks
                .filter(t => !hasDownstream.has(t.id))
                .map(t => ({
                    id: `${t.id}-end`, source: t.id, target: 'END',
                    style: { stroke: '#4b5563', strokeWidth: 1.5 },
                    markerEnd: { type: MarkerType.ArrowClosed, color: '#4b5563', width: 14, height: 14 },
                }));

            const depEdges: Edge[] = pg.dependencies.map((d, i) => ({
                id: `dep-${i}`, source: d.from, target: d.to,
                style: { stroke: '#4b5563', strokeWidth: 1.5 },
                markerEnd: { type: MarkerType.ArrowClosed, color: '#4b5563', width: 14, height: 14 },
            }));

            return { flowNodes: nodes, flowEdges: [...startEdges, ...depEdges, ...endEdges] };

        } else if (viewMode === 'subtask' && activeSubTaskId && devState.subTaskGraphs?.[activeSubTaskId]) {
            // ── Sub-task Internal Graph ──
            const sg = devState.subTaskGraphs[activeSubTaskId];
            const positions = layoutNodes(
                sg.nodes.map(n => n.id),
                sg.edges,
                true,
            );

            const nodes: Node[] = [
                {
                    id: 'START', position: positions.START || { x: 350, y: 0 },
                    data: { label: 'START' }, type: 'input',
                    style: {
                        background: '#18181b', border: '2px solid #3f3f46', borderRadius: '50%',
                        width: 60, height: 60, display: 'flex', alignItems: 'center',
                        justifyContent: 'center', color: '#a1a1aa', fontSize: '11px', fontWeight: 700,
                    },
                },
                ...sg.nodes.map(n => ({
                    id: n.id, position: positions[n.id] || { x: 0, y: 0 },
                    type: 'flowNode' as const,
                    data: {
                        label: n.label, mode: n.mode,
                        isCheckpoint: n.isCheckpoint || false,
                        isActive: sg.currentNode === n.id,
                        isCompleted: false,
                    },
                })),
                {
                    id: 'END', position: positions.END || { x: 350, y: 600 },
                    data: { label: 'END' }, type: 'output',
                    style: {
                        background: '#18181b', border: '2px solid #3f3f46', borderRadius: '50%',
                        width: 60, height: 60, display: 'flex', alignItems: 'center',
                        justifyContent: 'center', color: '#a1a1aa', fontSize: '11px', fontWeight: 700,
                    },
                },
            ];

            const edges: Edge[] = sg.edges.map((e, i) => ({
                id: `sub-${i}`, source: e.from, target: e.to,
                label: e.condition || '', animated: sg.currentNode === e.from,
                style: {
                    stroke: e.condition
                        ? (e.condition === 'failed' ? '#ef4444' : '#22c55e')
                        : '#4b5563',
                    strokeWidth: sg.currentNode === e.from ? 2.5 : 1.5,
                },
                labelStyle: { fill: '#9ca3af', fontSize: 11, fontWeight: 500 },
                labelBgStyle: { fill: '#18181b', fillOpacity: 0.9 },
                markerEnd: { type: MarkerType.ArrowClosed, color: '#4b5563', width: 14, height: 14 },
            }));

            return { flowNodes: nodes, flowEdges: edges };

        } else {
            // ── Dev Flow (generic) ──
            const gd = devState.graphDefinition;
            if (!gd?.nodes) return { flowNodes: [] as Node[], flowEdges: [] as Edge[] };
            const completedNodes = new Set(devState.history?.map(h => h.node) || []);
            const positions = layoutNodes(gd.nodes.map(n => n.id), gd.edges, true);

            const nodes: Node[] = [
                {
                    id: 'START', position: positions.START || { x: 350, y: 0 },
                    data: { label: 'START' }, type: 'input',
                    style: {
                        background: '#18181b', border: '2px solid #3f3f46', borderRadius: '50%',
                        width: 60, height: 60, display: 'flex', alignItems: 'center',
                        justifyContent: 'center', color: '#a1a1aa', fontSize: '11px', fontWeight: 700,
                    },
                },
                ...gd.nodes.map(n => ({
                    id: n.id, position: positions[n.id] || { x: 0, y: 0 },
                    type: 'flowNode' as const,
                    data: {
                        label: n.label, mode: n.mode,
                        isCheckpoint: n.isCheckpoint || false,
                        isActive: devState.currentNode === n.id,
                        isCompleted: completedNodes.has(n.id),
                    },
                })),
                {
                    id: 'END', position: positions.END || { x: 350, y: 700 },
                    data: { label: 'END' }, type: 'output',
                    style: {
                        background: '#18181b', border: '2px solid #3f3f46', borderRadius: '50%',
                        width: 60, height: 60, display: 'flex', alignItems: 'center',
                        justifyContent: 'center', color: '#a1a1aa', fontSize: '11px', fontWeight: 700,
                    },
                },
            ];

            const edges: Edge[] = gd.edges.map((e, i) => ({
                id: `e-${i}`, source: e.from, target: e.to,
                label: e.condition || '', animated: devState.currentNode === e.from,
                style: {
                    stroke: e.condition
                        ? (e.condition === 'rejected' || e.condition === 'failed' ? '#ef4444' : '#22c55e')
                        : '#4b5563',
                    strokeWidth: devState.currentNode === e.from ? 2.5 : 1.5,
                },
                labelStyle: { fill: '#9ca3af', fontSize: 11, fontWeight: 500 },
                labelBgStyle: { fill: '#18181b', fillOpacity: 0.9 },
                markerEnd: { type: MarkerType.ArrowClosed, color: '#4b5563', width: 14, height: 14 },
            }));

            return { flowNodes: nodes, flowEdges: edges };
        }
    }, [devState, viewMode, activeSubTaskId]);

    // ─── Node click handlers ─────────────────────────────────────

    const onNodeClick = (_event: React.MouseEvent, node: Node) => {
        if (node.id === 'START' || node.id === 'END') return;

        if (viewMode === 'project') {
            // Drill down into sub-task
            if (devState?.subTaskGraphs?.[node.id]) {
                setActiveSubTaskId(node.id);
                setViewMode('subtask');
            }
        } else {
            sendFeedback(`Jump to node: ${node.id}`, node.id);
        }
    };

    // ─── Breadcrumb label ────────────────────────────────────────

    const activeTaskLabel = activeSubTaskId
        ? devState?.projectGraph?.tasks.find(t => t.id === activeSubTaskId)?.label || activeSubTaskId
        : '';

    return (
        <div style={{ display: 'flex', height: '100%', gap: 0 }}>
            {/* ── React Flow Canvas ── */}
            <div style={{ flex: 1, position: 'relative', minWidth: 200 }}>
                {/* View Mode Tabs + Breadcrumb */}
                <div style={{
                    position: 'absolute', top: 12, left: 12, zIndex: 10,
                    display: 'flex', alignItems: 'center', gap: 8,
                }}>
                    <div style={{
                        display: 'flex', gap: 2, background: '#18181b', border: '1px solid #27272a',
                        borderRadius: 8, padding: 3,
                    }}>
                        {(['devflow', 'project', 'subtask'] as ViewMode[]).map(mode => (
                            <button key={mode} onClick={() => {
                                setViewMode(mode);
                                if (mode !== 'subtask') setActiveSubTaskId(null);
                            }}
                                style={{
                                    padding: '5px 12px', borderRadius: 6, border: 'none', cursor: 'pointer',
                                    fontSize: 11, fontWeight: 600,
                                    background: viewMode === mode ? '#6366f1' : 'transparent',
                                    color: viewMode === mode ? '#fff' : '#6b7280',
                                    transition: 'all 0.2s ease',
                                }}
                            >
                                {mode === 'devflow' ? 'Dev Flow' : mode === 'project' ? 'Project' : 'Sub-task'}
                            </button>
                        ))}
                    </div>

                    {/* Breadcrumb */}
                    {viewMode === 'subtask' && activeSubTaskId && (
                        <div style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            background: '#18181b', border: '1px solid #27272a',
                            borderRadius: 8, padding: '5px 12px', fontSize: 11, color: '#9ca3af',
                        }}>
                            <span style={{ cursor: 'pointer', color: '#6366f1' }}
                                onClick={() => setViewMode('project')}>
                                Project
                            </span>
                            <span>›</span>
                            <span style={{ color: '#e5e7eb', fontWeight: 600 }}>
                                {activeSubTaskId}: {activeTaskLabel}
                            </span>
                        </div>
                    )}
                </div>

                <ReactFlow
                    key={`${viewMode}-${activeSubTaskId}`}
                    nodes={flowNodes}
                    edges={flowEdges}
                    nodeTypes={nodeTypes}
                    onNodeClick={onNodeClick}
                    fitView
                    fitViewOptions={{ padding: 0.25 }}
                    proOptions={{ hideAttribution: true }}
                    style={{ background: '#09090b' }}
                >
                    <Background color="#1a1a2e" gap={20} size={1} />
                    <Controls style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: '8px' }} />
                </ReactFlow>
            </div>

            {/* ── Resizer Drag Handle ── */}
            <div
                style={{
                    width: '6px', cursor: 'col-resize', background: '#111113', flexShrink: 0,
                    borderLeft: '1px solid #27272a', borderRight: '1px solid #27272a', zIndex: 10,
                    display: 'flex', alignItems: 'center', justifyContent: 'center'
                }}
                onMouseDown={(e) => {
                    const startX = e.clientX;
                    const startWidth = sidePanelWidth;
                    const onMouseMove = (moveEvent: MouseEvent) => {
                        const newWidth = Math.max(250, Math.min(600, startWidth - (moveEvent.clientX - startX)));
                        setSidePanelWidth(newWidth);
                    };
                    const onMouseUp = () => {
                        document.removeEventListener('mousemove', onMouseMove);
                        document.removeEventListener('mouseup', onMouseUp);
                    };
                    document.addEventListener('mousemove', onMouseMove);
                    document.addEventListener('mouseup', onMouseUp);
                }}
            >
                <div style={{ width: 2, height: 24, background: '#4b5563', borderRadius: 2 }} />
            </div>

            {/* ── Side Panel ── */}
            <div style={{
                width: sidePanelWidth, background: '#111113', flexShrink: 0,
                display: 'flex', flexDirection: 'column', overflow: 'hidden',
            }}>
                {/* Status Header */}
                <div style={{ padding: '16px 20px', borderBottom: '1px solid #27272a' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                        <span style={{
                            width: 10, height: 10, borderRadius: '50%',
                            background: devState?.mode === 'IDLE' ? '#6b7280' :
                                devState?.mode === 'PLANNING' ? '#6366f1' :
                                    devState?.mode === 'EXECUTION' ? '#22c55e' : '#f97316',
                            boxShadow: devState?.mode !== 'IDLE'
                                ? `0 0 10px ${devState?.mode === 'PLANNING' ? '#6366f1' : devState?.mode === 'EXECUTION' ? '#22c55e' : '#f97316'}`
                                : 'none',
                        }} />
                        <span style={{ color: '#e5e7eb', fontWeight: 600, fontSize: 14 }}>
                            {devState?.mode || 'DISCONNECTED'}
                        </span>
                    </div>
                    <div style={{ color: '#9ca3af', fontSize: 12 }}>{devState?.taskName || 'No active task'}</div>
                    <div style={{ color: '#6b7280', fontSize: 11, marginTop: 4 }}>{devState?.taskStatus || '—'}</div>
                </div>

                {/* Run button removed from here, users should configure and run from Dirac Solver view */}

                {/* Project Progress Summary (only in project view) */}
                {viewMode === 'project' && devState?.projectGraph && (
                    <div style={{ padding: '12px 20px', borderBottom: '1px solid #27272a' }}>
                        <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 600, letterSpacing: '0.5px', marginBottom: 8 }}>
                            PROJECT PROGRESS
                        </div>
                        {devState.projectGraph.tasks.map(t => (
                            <div key={t.id} style={{
                                display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6,
                                cursor: 'pointer', padding: '4px 6px', borderRadius: 6,
                            }}
                                onClick={() => { setActiveSubTaskId(t.id); setViewMode('subtask'); }}
                            >
                                <span style={{
                                    fontSize: 10, fontWeight: 700, color: '#6b7280', width: 24,
                                }}>{t.id}</span>
                                <div style={{ flex: 1, height: 4, background: '#27272a', borderRadius: 2, overflow: 'hidden' }}>
                                    <div style={{
                                        width: `${t.progress}%`, height: '100%', borderRadius: 2,
                                        background: t.progress === 100 ? '#4b5563' : t.status === 'in-progress' ? '#22c55e' : '#3f3f46',
                                    }} />
                                </div>
                                <span style={{ fontSize: 10, color: '#6b7280', width: 30, textAlign: 'right' }}>{t.progress}%</span>
                            </div>
                        ))}
                    </div>
                )}

                {/* Log Output */}
                <div style={{
                    flex: 1, overflow: 'auto', padding: '12px 16px',
                    fontFamily: '"JetBrains Mono", "Fira Code", monospace', fontSize: '11px', lineHeight: 1.7,
                }}>
                    <div style={{ color: '#4b5563', fontSize: 10, marginBottom: 8, borderBottom: '1px solid #1f1f23', paddingBottom: 6 }}>
                        // Antigravity Event Log
                    </div>
                    {(devState?.logs || []).map((log, i) => (
                        <div key={i} style={{
                            color: log.includes('ERROR') || log.includes('✗') ? '#ef4444'
                                : log.includes('✓') || log.includes('SUCCESS') ? '#22c55e'
                                    : log.includes('PLANNING') ? '#818cf8'
                                        : log.includes('EXECUTION') ? '#4ade80'
                                            : log.includes('VERIFICATION') ? '#fb923c'
                                                : '#9ca3af',
                            marginBottom: 2,
                        }}>{log}</div>
                    ))}
                </div>

                {/* Vertical Resizer */}
                {devState?.nodeResults && Object.keys(devState.nodeResults).length > 0 && (
                    <div
                        style={{
                            height: '6px', cursor: 'row-resize', background: '#111113', flexShrink: 0,
                            borderTop: '1px solid #27272a', borderBottom: '1px solid #27272a', zIndex: 10,
                            display: 'flex', alignItems: 'center', justifyContent: 'center'
                        }}
                        onMouseDown={(e) => {
                            const startY = e.clientY;
                            const startHeight = inspectorHeight;
                            const onMouseMove = (moveEvent: MouseEvent) => {
                                // dragging up increases height, dragging down decreases height
                                const newHeight = Math.max(100, startHeight + (startY - moveEvent.clientY));
                                setInspectorHeight(newHeight);
                            };
                            const onMouseUp = () => {
                                document.removeEventListener('mousemove', onMouseMove);
                                document.removeEventListener('mouseup', onMouseUp);
                            };
                            document.addEventListener('mousemove', onMouseMove);
                            document.addEventListener('mouseup', onMouseUp);
                        }}
                    >
                        <div style={{ width: 24, height: 2, background: '#4b5563', borderRadius: 2 }} />
                    </div>
                )}

                {/* Node Results Inspector (Phase 3) */}
                {devState?.nodeResults && Object.keys(devState.nodeResults).length > 0 && (
                    <div style={{ padding: '10px 16px', height: inspectorHeight, overflow: 'auto', flexShrink: 0 }}>
                        <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 600, letterSpacing: '0.5px', marginBottom: 6 }}>
                            NODE RESULTS INSPECTOR
                        </div>
                        {Object.entries(devState.nodeResults).map(([nodeId, data]: [string, any]) => (
                            <details key={nodeId} style={{ marginBottom: 4 }}>
                                <summary style={{
                                    cursor: 'pointer', fontSize: 11, color: '#a5b4fc', fontWeight: 600,
                                    padding: '3px 0', userSelect: 'none',
                                }}>
                                    📊 {nodeId} <span style={{ color: '#4b5563', fontWeight: 400 }}>({data.timestamp?.split('T')[1]?.slice(0, 8) || '—'})</span>
                                </summary>
                                <div style={{
                                    background: '#0d0d10', border: '1px solid #1f1f23', borderRadius: 6,
                                    padding: '6px 10px', marginTop: 2, marginLeft: 12,
                                    fontFamily: '"JetBrains Mono", monospace', fontSize: 10, lineHeight: 1.6,
                                }}>
                                    {Object.entries(data).filter(([k]) => k !== 'timestamp').map(([key, val]) => (
                                        <div key={key} style={{ display: 'flex', gap: 8 }}>
                                            <span style={{ color: '#6366f1', minWidth: 100 }}>{key}:</span>
                                            <span style={{ color: '#e5e7eb', wordBreak: 'break-all' }}>
                                                {typeof val === 'object' ? JSON.stringify(val, null, 0) : String(val)}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </details>
                        ))}
                    </div>
                )}

                {/* Feedback Input */}
                <div style={{ borderTop: '1px solid #27272a', padding: '12px 16px' }}>
                    <div style={{ color: '#6b7280', fontSize: 10, marginBottom: 6, fontWeight: 600, letterSpacing: '0.5px' }}>
                        SEND INSTRUCTION TO ANTIGRAVITY
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                        <input
                            value={feedbackInput}
                            onChange={(e) => setFeedbackInput(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && feedbackInput.trim() && sendFeedback(feedbackInput.trim())}
                            placeholder="e.g. Start P2, skip to test..."
                            style={{
                                flex: 1, background: '#1a1a1e', border: '1px solid #27272a',
                                borderRadius: 8, padding: '8px 12px', color: '#e5e7eb', fontSize: 12, outline: 'none',
                            }}
                        />
                        <button onClick={() => feedbackInput.trim() && sendFeedback(feedbackInput.trim())} style={{
                            background: '#6366f1', border: 'none', borderRadius: 8,
                            padding: '8px 14px', color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                        }}>Send</button>
                    </div>
                    {feedbackStatus && (
                        <div style={{ marginTop: 4, fontSize: 11, color: feedbackStatus.includes('✓') ? '#22c55e' : '#ef4444' }}>
                            {feedbackStatus}
                        </div>
                    )}
                    {devState?.userFeedback?.instruction && (
                        <div style={{
                            marginTop: 8, padding: '8px 10px', background: '#1e1b4b',
                            border: '1px solid #4338ca', borderRadius: 8, fontSize: 11, color: '#a5b4fc',
                        }}>
                            <strong>Pending:</strong> {devState.userFeedback.instruction}
                            {devState.userFeedback.targetNode && (
                                <span style={{ color: '#6366f1' }}> → {devState.userFeedback.targetNode}</span>
                            )}
                        </div>
                    )}
                </div>
            </div>

            <style>{`
                @keyframes pulse {
                    0%, 100% { opacity: 1; transform: scale(1); }
                    50% { opacity: 0.4; transform: scale(1.4); }
                }
            `}</style>
        </div>
    );
}
