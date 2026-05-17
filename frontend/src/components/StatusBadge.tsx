import type { RunStatus } from '../hooks/useSolverRunner';

interface Props {
    status: RunStatus;
    elapsedSeconds: number;
    isComputing: boolean;
}

const STATUS_STYLE: Record<string, { bg: string; fg: string; bd: string }> = {
    SUCCESS: { bg: 'rgba(34,197,94,0.08)', fg: '#22c55e', bd: 'rgba(34,197,94,0.2)' },
    ERROR: { bg: 'rgba(239,68,68,0.08)', fg: '#ef4444', bd: 'rgba(239,68,68,0.2)' },
    RUNNING: { bg: 'rgba(0,212,255,0.08)', fg: '#00d4ff', bd: 'rgba(0,212,255,0.2)' },
    PAUSED: { bg: 'rgba(245,158,11,0.08)', fg: '#f59e0b', bd: 'rgba(245,158,11,0.2)' },
    IDLE: { bg: 'rgba(255,255,255,0.04)', fg: '#4b5563', bd: '#1a2035' },
};

function fmtDuration(seconds: number): string {
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds - mins * 60;
    return `${mins}m ${secs.toFixed(1)}s`;
}

export function StatusBadge({ status, elapsedSeconds, isComputing }: Props) {
    const s = STATUS_STYLE[status] || STATUS_STYLE.IDLE;
    return (
        <div
            className="text-xs py-1 px-3 mt-3 rounded font-mono tracking-widest"
            style={{ background: s.bg, color: s.fg, border: `1px solid ${s.bd}` }}
        >
            {status}{isComputing ? ` | ${fmtDuration(elapsedSeconds)}` : ''}
        </div>
    );
}
