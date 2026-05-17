import { PlayCircle, Loader2 } from 'lucide-react';
import type { EngineMode } from '../hooks/useOctopusConfig';

interface Props {
    engineMode: EngineMode;
    isComputing: boolean;
    dockerStatus: string;
    onRun: () => void;
    onPause: () => void;
}

const ENGINE_COLORS: Record<string, { bg: string; fg: string; bd: string; label: string }> = {
    octopus3D: { bg: 'rgba(0,212,255,0.12)', fg: '#00d4ff', bd: 'rgba(0,212,255,0.35)', label: 'Octopus-v16 MCP' },
    vasp: { bg: 'rgba(168,85,247,0.12)', fg: '#a855f7', bd: 'rgba(168,85,247,0.35)', label: 'VASP PAW-PBE' },
    local1D: { bg: 'rgba(255,255,255,0.05)', fg: '#8892a4', bd: '#1e2d45', label: 'Local Python Engine' },
};

export function ComputeButton({ engineMode, isComputing, dockerStatus, onRun, onPause }: Props) {
    const c = ENGINE_COLORS[engineMode] || ENGINE_COLORS.local1D;

    const dotColor = dockerStatus === 'online' ? '#22c55e' : dockerStatus === 'offline' ? '#ef4444' : '#6b7280';

    return (
        <div className="mt-4 pt-3 flex flex-col gap-2" style={{ borderTop: '1px solid #1a2035' }}>
            <div className="flex justify-between items-center px-1">
                <span className="text-xs font-mono" style={{ color: '#8892a4' }}>{c.label}</span>
                <div className="flex items-center gap-1.5">
                    <div className="w-2 h-2 rounded-full" style={{ background: dotColor }} />
                    <span className="text-xs font-mono uppercase tracking-wider" style={{ color: dotColor }}>
                        {dockerStatus}
                    </span>
                </div>
            </div>
            <button
                onClick={onRun}
                disabled={isComputing}
                className="w-full disabled:opacity-40 disabled:cursor-not-allowed font-semibold rounded-xl px-4 py-3 flex items-center justify-center gap-2 transition-all"
                style={{
                    background: isComputing ? 'rgba(0,212,255,0.08)' : c.bg,
                    color: c.fg,
                    border: `1px solid ${c.bd}`,
                }}
            >
                {isComputing ? <Loader2 className="w-5 h-5 animate-spin" /> : <PlayCircle className="w-5 h-5" />}
                {isComputing ? 'Computing...' : 'Initiate Computation'}
            </button>
            <button
                onClick={onPause}
                disabled={!isComputing}
                className="w-full disabled:opacity-40 disabled:cursor-not-allowed font-semibold rounded-xl px-4 py-2.5 flex items-center justify-center gap-2 transition-all"
                style={{
                    background: 'rgba(245,158,11,0.14)',
                    color: '#f59e0b',
                    border: '1px solid rgba(245,158,11,0.35)',
                }}
            >
                Pause
            </button>
        </div>
    );
}
