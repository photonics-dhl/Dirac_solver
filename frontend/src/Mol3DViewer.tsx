/**
 * Mol3DViewer — interactive 3D molecular geometry viewer
 * Canvas-based, no external 3D library required.
 * Features: perspective projection, drag-to-rotate, scroll-to-zoom,
 *           depth-shaded spheres, bond detection, XYZ axis widget, auto-rotate.
 */
import React, { useRef, useEffect, useCallback, useMemo } from 'react';

// ── Element data ──────────────────────────────────────────────────

const ELEM_RGB: Record<string, [number, number, number]> = {
    H:  [226, 232, 240], He: [255, 105, 180], Li: [204, 128, 255],
    Be: [194, 255,   0], B:  [255, 181, 181], C:  [144, 144, 144],
    N:  [ 48,  80, 248], O:  [255,  13,  13], F:  [144, 224,  80],
    Na: [171,  92, 242], Mg: [138, 255,   0], Al: [191, 166, 166],
    Si: [240, 200, 160], P:  [255, 128,   0], S:  [255, 255,  48],
    Cl: [ 31, 240,  31],
};
const GET_RGB = (sym: string): [number, number, number] => ELEM_RGB[sym] ?? [160, 160, 160];

const COVALENT_R: Record<string, number> = {
    H: 0.31, He: 0.28, Li: 1.28, C: 0.77, N: 0.75, O: 0.73,
    F: 0.71, Na: 1.66, Al: 1.21, Si: 1.11, P: 1.07, S: 1.05, Cl: 1.02,
};
const GET_R = (sym: string) => COVALENT_R[sym] ?? 0.80;

// ── Molecule database (mirrors docker/workspace/server.py MOLECULES) ─

export interface Atom3D { symbol: string; x: number; y: number; z: number; }

export const MOLECULE_ATOMS: Record<string, Atom3D[]> = {
    H:   [{ symbol: 'H',  x:  0,      y:  0,      z:  0 }],
    He:  [{ symbol: 'He', x:  0,      y:  0,      z:  0 }],
    Li:  [{ symbol: 'Li', x:  0,      y:  0,      z:  0 }],
    Na:  [{ symbol: 'Na', x:  0,      y:  0,      z:  0 }],
    H2: [
        { symbol: 'H', x:  0, y: 0, z: -0.7 },
        { symbol: 'H', x:  0, y: 0, z:  0.7 },
    ],
    LiH: [
        { symbol: 'Li', x: 0, y: 0, z: -1.511 },
        { symbol: 'H',  x: 0, y: 0, z:  1.511 },
    ],
    CO: [
        { symbol: 'C', x: 0, y: 0, z: -1.066 },
        { symbol: 'O', x: 0, y: 0, z:  1.066 },
    ],
    N2: [
        { symbol: 'N', x: 0, y: 0, z: -1.03 },
        { symbol: 'N', x: 0, y: 0, z:  1.03 },
    ],
    H2O: [
        { symbol: 'O', x:  0,     y: 0, z:  0 },
        { symbol: 'H', x:  1.430, y: 0, z: -1.107 },
        { symbol: 'H', x: -1.430, y: 0, z: -1.107 },
    ],
    NH3: [
        { symbol: 'N', x:  0,      y:  0,      z:  0 },
        { symbol: 'H', x:  0,      y:  1.771,  z: -0.627 },
        { symbol: 'H', x:  1.533,  y: -0.886,  z: -0.627 },
        { symbol: 'H', x: -1.533,  y: -0.886,  z: -0.627 },
    ],
    CH4: [
        { symbol: 'C', x:  0,     y:  0,     z:  0 },
        { symbol: 'H', x:  1.186, y:  1.186, z:  1.186 },
        { symbol: 'H', x: -1.186, y: -1.186, z:  1.186 },
        { symbol: 'H', x:  1.186, y: -1.186, z: -1.186 },
        { symbol: 'H', x: -1.186, y:  1.186, z: -1.186 },
    ],
    C2H4: [
        { symbol: 'C', x:  1.261, y:  0,     z: 0 },
        { symbol: 'C', x: -1.261, y:  0,     z: 0 },
        { symbol: 'H', x:  2.332, y:  1.745, z: 0 },
        { symbol: 'H', x:  2.332, y: -1.745, z: 0 },
        { symbol: 'H', x: -2.332, y:  1.745, z: 0 },
        { symbol: 'H', x: -2.332, y: -1.745, z: 0 },
    ],
    Benzene: [
        { symbol: 'C', x:  0,      y:  1.396, z: 0 },
        { symbol: 'C', x:  1.209,  y:  0.698, z: 0 },
        { symbol: 'C', x:  1.209,  y: -0.698, z: 0 },
        { symbol: 'C', x:  0,      y: -1.396, z: 0 },
        { symbol: 'C', x: -1.209,  y: -0.698, z: 0 },
        { symbol: 'C', x: -1.209,  y:  0.698, z: 0 },
        { symbol: 'H', x:  0,      y:  2.484, z: 0 },
        { symbol: 'H', x:  2.151,  y:  1.242, z: 0 },
        { symbol: 'H', x:  2.151,  y: -1.242, z: 0 },
        { symbol: 'H', x:  0,      y: -2.484, z: 0 },
        { symbol: 'H', x: -2.151,  y: -1.242, z: 0 },
        { symbol: 'H', x: -2.151,  y:  1.242, z: 0 },
    ],
    Si: [
        { symbol: 'Si', x: 0,     y: 0,     z: 0 },
        { symbol: 'Si', x: 2.566, y: 2.566, z: 2.566 },
    ],
    Al2O3: [
        { symbol: 'Al', x:  0,      y:  0,      z:  2.263 },
        { symbol: 'Al', x:  0,      y:  0,      z: -2.263 },
        { symbol: 'O',  x:  2.386,  y:  0,      z:  0 },
        { symbol: 'O',  x: -1.193,  y:  2.067,  z:  0 },
        { symbol: 'O',  x: -1.193,  y: -2.067,  z:  0 },
    ],
};

// ── 3D math helpers ──────────────────────────────────────────────

function rotY(x: number, y: number, z: number, a: number) {
    const c = Math.cos(a), s = Math.sin(a);
    return { x: x * c + z * s, y, z: -x * s + z * c };
}
function rotX(x: number, y: number, z: number, a: number) {
    const c = Math.cos(a), s = Math.sin(a);
    return { x, y: y * c - z * s, z: y * s + z * c };
}
function project(
    atom: { x: number; y: number; z: number },
    rx: number, ry: number,
    scale: number, cx: number, cy: number
) {
    let p = rotY(atom.x, atom.y, atom.z, ry);
    p = rotX(p.x, p.y, p.z, rx);
    const fov = 6.0;
    const d = fov / (fov + p.z);
    return { sx: cx + p.x * d * scale, sy: cy - p.y * d * scale, sz: p.z };
}

// ── Component ────────────────────────────────────────────────────

interface Mol3DViewerProps {
    atoms: Atom3D[];
    boxRadius?: number;
    width?: number;
    height?: number;
    title?: string;
    showLegend?: boolean;
    showTable?: boolean;
}

export function Mol3DViewer({
    atoms,
    boxRadius = 5,
    width = 400,
    height = 300,
    title,
    showLegend = true,
    showTable = false,
}: Mol3DViewerProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const rotRef = useRef({ rx: 0.35, ry: 0.25 });
    const dragRef = useRef<{ x: number; y: number } | null>(null);
    const scaleRef = useRef(1.0);
    const autoRef = useRef(true);
    const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
    const [tableOpen, setTableOpen] = React.useState(false);

    // Bond detection (memoised — only recomputes when atoms changes)
    const bonds = useMemo<[number, number][]>(() => {
        const b: [number, number][] = [];
        for (let i = 0; i < atoms.length; i++) {
            for (let j = i + 1; j < atoms.length; j++) {
                const dx = atoms[i].x - atoms[j].x;
                const dy = atoms[i].y - atoms[j].y;
                const dz = atoms[i].z - atoms[j].z;
                const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
                const maxBond = (GET_R(atoms[i].symbol) + GET_R(atoms[j].symbol)) * 1.35 + 0.5;
                if (dist < maxBond) b.push([i, j]);
            }
        }
        return b;
    }, [atoms]);

    const drawFrame = useCallback(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const W = canvas.width;
        const H = canvas.height;
        const cx = W / 2;
        const cy = H / 2;
        const { rx, ry } = rotRef.current;
        const autoScale =
            (Math.min(W, H) / 2 - 30) * scaleRef.current / Math.max(boxRadius, 1.5);

        // Background
        ctx.fillStyle = '#0a0e1a';
        ctx.fillRect(0, 0, W, H);

        // Simulation box outline (dashed circle = sphere projection)
        const boxR2d = boxRadius * autoScale;
        ctx.beginPath();
        ctx.arc(cx, cy, Math.max(boxR2d * 0.98, 12), 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(0,212,255,0.10)';
        ctx.lineWidth = 0.8;
        ctx.setLineDash([5, 5]);
        ctx.stroke();
        ctx.setLineDash([]);

        // Project atoms
        const projs = atoms.map(a => project(a, rx, ry, autoScale, cx, cy));

        // Draw bonds
        for (const [i, j] of bonds) {
            ctx.beginPath();
            ctx.moveTo(projs[i].sx, projs[i].sy);
            ctx.lineTo(projs[j].sx, projs[j].sy);
            ctx.strokeStyle = 'rgba(255,255,255,0.20)';
            ctx.lineWidth = 1.8;
            ctx.stroke();
        }

        // Depth sort: far atoms first (painter's algorithm)
        const order = atoms.map((_, i) => i).sort((a, b) => projs[a].sz - projs[b].sz);

        // Draw atoms
        for (const i of order) {
            const a = atoms[i];
            const { sx, sy, sz } = projs[i];
            const baseR = GET_R(a.symbol) * autoScale * 0.45;
            const r = Math.max(4, Math.min(22, baseR));
            const col = GET_RGB(a.symbol);

            // Depth shading [0→1 where 1=closest]
            const depthNorm = Math.max(0, Math.min(1,
                (sz + boxRadius) / (2 * boxRadius + 0.01)));
            const bright = 0.45 + depthNorm * 0.55;

            // Radial gradient: off-center highlight for 3D sphere look
            const hlx = sx - r * 0.32;
            const hly = sy - r * 0.32;
            const grd = ctx.createRadialGradient(hlx, hly, r * 0.04, sx, sy, r);
            grd.addColorStop(0.0, `rgba(${col.map(c => Math.min(255, Math.round(c * 1.6))).join(',')},1)`);
            grd.addColorStop(0.5, `rgba(${col.map(c => Math.min(255, Math.round(c * bright))).join(',')},1)`);
            grd.addColorStop(1.0, `rgba(${col.map(c => Math.round(c * bright * 0.3)).join(',')},1)`);

            ctx.beginPath();
            ctx.arc(sx, sy, r, 0, Math.PI * 2);
            ctx.fillStyle = grd;
            ctx.fill();

            // Small specular highlight
            ctx.beginPath();
            ctx.arc(hlx, hly, r * 0.22, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(255,255,255,0.16)';
            ctx.fill();

            // Element symbol — only if atom is large enough
            if (r >= 8) {
                const fs = Math.max(7, Math.round(r * 0.72));
                ctx.font = `bold ${fs}px 'SF Mono', ui-monospace, monospace`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillStyle = `rgba(10,14,26,${0.85 * bright + 0.1})`;
                ctx.fillText(a.symbol, sx, sy + 0.5);
            }
        }

        // XYZ axis widget (bottom-right corner)
        const ax = W - 36, ay = H - 36, al = 20;
        const axesDef: Array<{ v: [number, number, number]; color: string; lbl: string }> = [
            { v: [al, 0, 0], color: '#ef4444', lbl: 'x' },
            { v: [0, al, 0], color: '#22c55e', lbl: 'y' },
            { v: [0,  0, al], color: '#3b82f6', lbl: 'z' },
        ];
        for (const axis of axesDef) {
            const tip = project(
                { x: axis.v[0] / autoScale, y: axis.v[1] / autoScale, z: axis.v[2] / autoScale },
                rx, ry, autoScale, ax, ay,
            );
            ctx.beginPath();
            ctx.moveTo(ax, ay);
            ctx.lineTo(tip.sx, tip.sy);
            ctx.strokeStyle = axis.color;
            ctx.lineWidth = 1.8;
            ctx.stroke();
            ctx.font = 'bold 9px monospace';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = axis.color;
            const lx = tip.sx + (tip.sx - ax) * 0.3;
            const ly = tip.sy + (tip.sy - ay) * 0.3;
            ctx.fillText(axis.lbl, lx, ly);
        }

        // Bohr scale label (top-left)
        ctx.font = '9px monospace';
        ctx.fillStyle = 'rgba(75,85,99,0.9)';
        ctx.textAlign = 'left';
        ctx.fillText(`Box r=${boxRadius.toFixed(1)} Bohr`, 8, 14);

    }, [atoms, bonds, boxRadius]);

    // Animation loop
    useEffect(() => {
        let raf: number;
        const loop = () => {
            if (autoRef.current && !dragRef.current) {
                rotRef.current.ry += 0.007;
            }
            drawFrame();
            raf = requestAnimationFrame(loop);
        };
        raf = requestAnimationFrame(loop);
        return () => cancelAnimationFrame(raf);
    }, [drawFrame]);

    // Mouse interaction
    const onMouseDown = (e: React.MouseEvent) => {
        e.preventDefault();
        dragRef.current = { x: e.clientX, y: e.clientY };
        autoRef.current = false;
        if (timerRef.current) clearTimeout(timerRef.current);
    };
    const onMouseMove = (e: React.MouseEvent) => {
        if (!dragRef.current) return;
        rotRef.current.ry += (e.clientX - dragRef.current.x) * 0.012;
        rotRef.current.rx += (e.clientY - dragRef.current.y) * 0.012;
        // Clamp X rotation to avoid flipping
        rotRef.current.rx = Math.max(-1.5, Math.min(1.5, rotRef.current.rx));
        dragRef.current = { x: e.clientX, y: e.clientY };
    };
    const onMouseUp = () => {
        dragRef.current = null;
        timerRef.current = setTimeout(() => { autoRef.current = true; }, 2500);
    };
    const onWheel = (e: React.WheelEvent) => {
        e.preventDefault();
        scaleRef.current = Math.max(0.25, Math.min(4.0,
            scaleRef.current * (e.deltaY > 0 ? 0.88 : 1.13)));
    };
    const onReset = () => {
        rotRef.current = { rx: 0.35, ry: 0.25 };
        scaleRef.current = 1.0;
        autoRef.current = true;
    };

    const uniqueElems = [...new Set(atoms.map(a => a.symbol))];

    return (
        <div style={{
            background: 'rgba(255,255,255,0.02)',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 8, overflow: 'hidden',
        }}>
            {/* Header */}
            <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.04)',
            }}>
                <span style={{
                    fontSize: 10, color: '#8892a4', fontWeight: 600,
                    textTransform: 'uppercase', letterSpacing: '0.05em',
                }}>
                    {title ?? '几何构型 (3D)'}
                </span>
                <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                    <span style={{ fontSize: 9, color: '#374151' }}>拖拽旋转 · 滚轮缩放</span>
                    <button onClick={onReset} style={{
                        fontSize: 9, padding: '2px 7px', borderRadius: 3, border: 'none',
                        cursor: 'pointer', background: 'rgba(255,255,255,0.05)',
                        color: '#8892a4', outline: '1px solid #1f2937',
                    }}>复位</button>
                </div>
            </div>

            {/* Canvas */}
            <canvas
                ref={canvasRef}
                width={width}
                height={height}
                style={{ display: 'block', cursor: 'grab', width: '100%', height: `${height}px` }}
                onMouseDown={onMouseDown}
                onMouseMove={onMouseMove}
                onMouseUp={onMouseUp}
                onMouseLeave={onMouseUp}
                onWheel={onWheel}
            />

            {/* Legend bar */}
            {showLegend && (
                <div style={{
                    padding: '5px 10px', display: 'flex', gap: 8, flexWrap: 'wrap',
                    alignItems: 'center', borderTop: '1px solid rgba(255,255,255,0.04)',
                }}>
                    {uniqueElems.map(sym => {
                        const c = GET_RGB(sym);
                        return (
                            <span key={sym} style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 9, color: '#8892a4' }}>
                                <span style={{
                                    display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                                    background: `rgb(${c.join(',')})`,
                                }} />
                                {sym}
                            </span>
                        );
                    })}
                    <span style={{ fontSize: 9, color: '#1f2937', marginLeft: 'auto' }}>
                        {atoms.length} 原子
                    </span>
                    {showTable && (
                        <button onClick={() => setTableOpen(o => !o)} style={{
                            fontSize: 9, padding: '1px 6px', borderRadius: 3, border: 'none',
                            cursor: 'pointer', background: 'rgba(255,255,255,0.04)',
                            color: '#4b5563', outline: '1px solid #1f2937',
                        }}>
                            {tableOpen ? '隐藏坐标' : '显示坐标'}
                        </button>
                    )}
                </div>
            )}

            {/* Coordinate table (optional) */}
            {showTable && tableOpen && (
                <table style={{
                    width: '100%', fontSize: 9, fontFamily: 'monospace',
                    borderCollapse: 'collapse', padding: '0 8px 6px',
                }}>
                    <thead>
                        <tr style={{ color: '#4b5563' }}>
                            {['符号', 'x (Bohr)', 'y (Bohr)', 'z (Bohr)'].map(h => (
                                <th key={h} style={{ textAlign: h === '符号' ? 'left' : 'right', padding: '2px 6px', fontWeight: 400 }}>{h}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {atoms.map((at, i) => {
                            const c = GET_RGB(at.symbol);
                            return (
                                <tr key={i} style={{ borderTop: '1px solid rgba(255,255,255,0.04)', color: `rgb(${c.join(',')})` }}>
                                    <td style={{ padding: '2px 6px' }}>{at.symbol}</td>
                                    <td style={{ padding: '2px 6px', textAlign: 'right' }}>{at.x.toFixed(4)}</td>
                                    <td style={{ padding: '2px 6px', textAlign: 'right' }}>{at.y.toFixed(4)}</td>
                                    <td style={{ padding: '2px 6px', textAlign: 'right' }}>{at.z.toFixed(4)}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            )}
        </div>
    );
}

export default Mol3DViewer;
