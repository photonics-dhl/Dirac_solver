/**
 * ResultsPanel — Adaptive visualization for all solver types:
 *   - Bound State: Wavefunction, Probability Density, Momentum Space, Potential, Energy Spectrum
 *   - Time Evolution: Wavepacket heatmap (x,t) + time slider + coefficient chart
 *   - Scattering: T(E)/R(E) curves + resonance markers + sample psi²(x)
 */

import React, { useMemo, useState } from 'react';

const API_BASE = '';

// ─── Shared Types ─────────────────────────────────────────────────

interface PhysicsResult {
    config: any;
    problemType: string;
    equationType: string;
    dimensionality?: string;
    x_grid?: number[];
    y_grid?: number[];
    p_grid?: number[];
    potential_V?: number[];
    hamiltonian: number[][];
    eigenvalues: number[];
    eigenvaluesSI?: string[];
    eigenvectors?: number[][];
    wavefunctions: Array<{
        psi_up: number[];
        psi_down: number[];
        psi_p_mag?: number[];
    }>;
    probabilityDensity: number[];
    verified: boolean;
    computationTime: number;
    timeEvolution?: {
        time_grid: number[];
        psi_t: number[][];
        initial_state: number[];
        initial_coefficients: number[];
        eigenvalues: number[];
    };
    scattering?: {
        energy_range: number[];
        transmission: number[];
        reflection: number[];
        resonances: number[];
        sample_wavefunctions: Array<{
            energy: number;
            psi_sq: number[];
            transmission: number;
        }>;
    };
    molecular?: {
        calcMode: 'gs' | 'td';
        moleculeName: string;
        energy_levels?: number[];
        homo_energy?: number;
        lumo_energy?: number;
        total_energy_hartree?: number;
        scf_iterations?: number;
        converged?: boolean;
        optical_spectrum?: {
            energy_ev: number[];
            cross_section: number[];
        };
        convergence_data?: {
            iterations: number[];
            energy_diff: number[];
        };
        dos_data?: {
            energy_ev: number[];
            dos: number[];
        };
        td_dipole?: {
            time: number[];
            dipole_x: number[];
            dipole_y: number[];
            dipole_z: number[];
        };
        band_structure_data?: {
            kpoints: number[];
            bands: number[][];
            fermi_energy_ev?: number;
        };
        density_difference_1d?: {
            x: number[];
            delta_rho: number[];
        };
    };
    density_1d?: number[];
}

// ─── SVG Chart Primitives ─────────────────────────────────────────

const CHART_W = 400;
const CHART_H = 220;
const PAD = { top: 24, right: 16, bottom: 30, left: 44 };
const INNER_W = CHART_W - PAD.left - PAD.right;
const INNER_H = CHART_H - PAD.top - PAD.bottom;

function ChartContainer({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <div style={{
            background: 'rgba(255,255,255,0.02)',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 10,
            padding: '8px',
            position: 'relative',
        }}>
            <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 4, fontWeight: 600, letterSpacing: '0.04em' }}>
                {title}
            </div>
            <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} width={CHART_W} height={CHART_H} style={{ width: '100%', height: 'auto', display: 'block' }}>
                {children}
            </svg>
        </div>
    );
}

type Tick = { pos: number; label: string };

function Axes({
    xLabel = '', yLabel = '',
    xTicks = [], yTicks = [],
    xMin, xMax, yMin, yMax,
}: {
    xLabel?: string; yLabel?: string;
    xTicks?: Tick[]; yTicks?: Tick[];
    xMin?: number; xMax?: number; yMin?: number; yMax?: number;
}) {
    const xt = xTicks.length ? xTicks : makeXTicks(xMin ?? 0, xMax ?? 1, 5);
    const yt = yTicks.length ? yTicks : makeYTicks(yMin ?? 0, yMax ?? 1, 4);
    return (
        <>
            <rect x={PAD.left} y={PAD.top} width={INNER_W} height={INNER_H}
                fill="rgba(255,255,255,0.01)" stroke="rgba(255,255,255,0.06)" strokeWidth={1} rx={2} />
            {xt.map((t, i) => (
                <g key={i}>
                    <line x1={t.pos} x2={t.pos} y1={PAD.top} y2={PAD.top + INNER_H + 4} stroke="rgba(255,255,255,0.06)" strokeWidth={1} />
                    <text x={t.pos} y={PAD.top + INNER_H + 14} textAnchor="middle" fill="#6b7280" fontSize={8}>{t.label}</text>
                </g>
            ))}
            {yt.map((t, i) => (
                <g key={i}>
                    <line x1={PAD.left - 4} x2={PAD.left + INNER_W} y1={t.pos} y2={t.pos} stroke="rgba(255,255,255,0.06)" strokeWidth={1} />
                    <text x={PAD.left - 6} y={t.pos + 3} textAnchor="end" fill="#6b7280" fontSize={8}>{t.label}</text>
                </g>
            ))}
            {xLabel && <text x={PAD.left + INNER_W / 2} y={CHART_H - 2} textAnchor="middle" fill="#4b5563" fontSize={8}>{xLabel}</text>}
            {yLabel && <text x={10} y={PAD.top + INNER_H / 2} textAnchor="middle" fill="#4b5563" fontSize={8}
                transform={`rotate(-90,10,${PAD.top + INNER_H / 2})`}>{yLabel}</text>}
        </>
    );
}

function LinePath({
    xData, yData, color, strokeWidth = 1.5,
    xMin: xMinProp, xMax: xMaxProp, yMin: yMinProp, yMax: yMaxProp,
}: {
    xData: number[]; yData: number[]; color: string; strokeWidth?: number;
    xMin?: number; xMax?: number; yMin?: number; yMax?: number;
}) {
    if (!xData || !yData || xData.length === 0 || yData.length === 0) return null;
    const xMin = xMinProp ?? Math.min(...xData);
    const xMax = xMaxProp ?? Math.max(...xData);
    const yMin = yMinProp ?? Math.min(...yData);
    const yMax = yMaxProp ?? Math.max(...yData);
    const xRange = xMax - xMin || 1;
    const yRange = yMax - yMin || 1;

    const pts = xData.map((x, i) => {
        const px = PAD.left + ((x - xMin) / xRange) * INNER_W;
        const py = PAD.top + INNER_H - ((yData[i] - yMin) / yRange) * INNER_H;
        return `${px.toFixed(2)},${py.toFixed(2)}`;
    }).join(' ');

    return <polyline points={pts} fill="none" stroke={color} strokeWidth={strokeWidth} opacity={0.9} />;
}

function FillPath({
    xData, yData, color, xMin: xMinProp, xMax: xMaxProp, yMin: yMinProp, yMax: yMaxProp,
}: {
    xData: number[]; yData: number[]; color: string;
    xMin?: number; xMax?: number; yMin?: number; yMax?: number;
}) {
    if (!xData || !yData || xData.length === 0) return null;
    const xMin = xMinProp ?? Math.min(...xData);
    const xMax = xMaxProp ?? Math.max(...xData);
    const yMin = yMinProp ?? 0;
    const yMax = yMaxProp ?? Math.max(...yData);
    const xRange = xMax - xMin || 1;
    const yRange = yMax - yMin || 1;
    const baseline = PAD.top + INNER_H;
    const pts = xData.map((x, i) => {
        const px = PAD.left + ((x - xMin) / xRange) * INNER_W;
        const py = PAD.top + INNER_H - ((yData[i] - yMin) / yRange) * INNER_H;
        return `${px.toFixed(2)},${py.toFixed(2)}`;
    });
    const first = pts[0].split(',');
    const last = pts[pts.length - 1].split(',');
    const filled = `${first[0]},${baseline} ` + pts.join(' ') + ` ${last[0]},${baseline}`;
    return <polygon points={filled} fill={color} fillOpacity={0.18} stroke={color} strokeWidth={1} />;
}

function makeYTicks(yMin: number, yMax: number, count: number = 4): Tick[] {
    const range = yMax - yMin || 1;
    const step = range / count;
    return Array.from({ length: count + 1 }, (_, i) => {
        const val = yMin + i * step;
        const py = PAD.top + INNER_H - ((val - yMin) / range) * INNER_H;
        return { pos: py, label: val.toFixed(Math.abs(val) < 10 && val !== 0 ? 2 : 0) };
    });
}

function makeXTicks(xMin: number, xMax: number, count: number = 5): Tick[] {
    const range = xMax - xMin || 1;
    const step = range / count;
    return Array.from({ length: count + 1 }, (_, i) => {
        const val = xMin + i * step;
        const px = PAD.left + ((val - xMin) / range) * INNER_W;
        return { pos: px, label: val.toFixed(1) };
    });
}

// ─── Data Extractors ─────────────────────────────────────────────

function extractWavefunction(result: PhysicsResult, idx: number) {
    const wf = result.wavefunctions?.[idx];
    const x = result.x_grid || [];
    if (!wf || x.length === 0) return { x: [0], psi: [0], psiSq: [0] };
    const psi = wf.psi_up.slice(0, x.length);
    return { x, psi, psiSq: psi.map(v => v * v) };
}

function extractPotential(result: PhysicsResult) {
    const x = result.x_grid || [0];
    const V = result.potential_V || x.map(() => 0);
    return { x, V };
}

function extractMomentum(result: PhysicsResult, idx: number) {
    if (!result.p_grid || !result.wavefunctions?.[idx]?.psi_p_mag) return [];
    const p = result.p_grid;
    const mag = result.wavefunctions[idx].psi_p_mag!;
    return p.map((pv, i) => ({ p: pv, mag: mag[i] ?? 0 }));
}

function safe(arr: number[]): number[] {
    return arr.filter(v => isFinite(v));
}

// ─── Views ────────────────────────────────────────────────────────

/** Time evolution heatmap rendered as stacked thin SVG rects */
function TimeEvolutionView({ result }: { result: PhysicsResult }) {
    const te = result.timeEvolution;
    const [timeIdx, setTimeIdx] = useState(0);

    // Fallback if the data is completely missing (e.g. state desync)
    if (!te || !te.psi_t || te.psi_t.length === 0) {
        return <div style={{ color: '#ef4444', fontSize: 13, padding: 20 }}>⚠️ Time Evolution data not available for this run. Please click 'Initiate Computation' again.</div>;
    }

    const x = result.x_grid || [];
    const psi_t = te.psi_t;
    const T = psi_t.length;
    const N = x.length;
    if (T === 0 || N === 0) return <div style={{ color: '#6b7280', fontSize: 12 }}>No time evolution data</div>;

    const xMin = Math.min(...x);
    const xMax = Math.max(...x);
    const tMax = te.time_grid[T - 1] ?? T;

    // Current snapshot
    const currentPsi = psi_t[timeIdx] || [];
    let maxPsi = Math.max(...psi_t.map(row => Math.max(...row)), 0.01);
    if (!isFinite(maxPsi) || maxPsi <= 0) maxPsi = 0.01;

    const V_arr = result.potential_V || x.map(() => 0);
    const vMin = Math.min(...V_arr);
    const vMax = Math.max(...V_arr);
    const vScale = vMax > vMin ? (maxPsi * 0.8) / (vMax - vMin) : 1;
    const vOffset = vMin;
    const scaled_V = V_arr.map(v => (v - vOffset) * vScale + maxPsi * 0.1);

    // Layout configuration
    const heatH = 140;
    const heatW = CHART_W - PAD.left - PAD.right;

    // Expected position <x> computation
    const dx = x[1] - x[0] || 0.1;
    const expectedX = psi_t.map(row => {
        let expX = 0;
        let norm = 0;
        for (let i = 0; i < N; i++) {
            expX += row[i] * x[i] * dx;
            norm += row[i] * dx;
        }
        return norm > 0 ? expX / norm : 0;
    });

    const expXMin = Math.min(...expectedX, xMin);
    const expXMax = Math.max(...expectedX, xMax);

    // Render Canvas Heatmap efficiently
    const canvasRef = React.useRef<HTMLCanvasElement>(null);
    React.useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        // Create ImageData
        const imgData = ctx.createImageData(N, T);
        for (let ti = 0; ti < T; ti++) {
            for (let ni = 0; ni < N; ni++) {
                const val = psi_t[ti][ni];
                const intensity = Math.min(val / maxPsi, 1);
                const r = Math.round(intensity * 139 + (1 - intensity) * 17);
                const g = Math.round(intensity * 92 + (1 - intensity) * 24);
                const b = Math.round(intensity * 246 + (1 - intensity) * 39);

                // flip ti so t=0 is at the bottom
                const flippedTi = T - 1 - ti;
                const idx = (flippedTi * N + ni) * 4;
                imgData.data[idx] = r;
                imgData.data[idx + 1] = g;
                imgData.data[idx + 2] = b;
                imgData.data[idx + 3] = 255; // Alpha
            }
        }
        ctx.putImageData(imgData, 0, 0);
    }, [psi_t, maxPsi, N, T]);

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {/* Info Box for Tunneling */}
            {result.config?.potentialType === 'InfiniteWell' && (
                <div style={{ background: 'rgba(56, 189, 248, 0.1)', border: '1px solid rgba(56, 189, 248, 0.2)', borderRadius: 6, padding: '8px 12px', fontSize: 11, color: '#38bdf8' }}>
                    <strong>Note on Tunneling:</strong> You are currently using an <em>Infinite Square Well</em>, which possesses walls of infinite energy. According to quantum mechanics, the probability of tunneling through an infinite barrier is strictly zero, meaning the wavepacket is permanently confined. To observe quantum tunneling, change the Potential Type to <strong>Finite Well</strong> or <strong>Step</strong> potential.
                </div>
            )}

            {/* Time slider */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 4px' }}>
                <span style={{ fontSize: 11, color: '#9ca3af', minWidth: 60 }}>t = {te.time_grid[timeIdx]?.toFixed(2) ?? '0'}</span>
                <input type="range" min={0} max={T - 1} value={timeIdx} onChange={e => setTimeIdx(Number(e.target.value))}
                    style={{ flex: 1, accentColor: '#8b5cf6' }} />
                <span style={{ fontSize: 11, color: '#6b7280' }}>T={tMax.toFixed(1)}</span>
            </div>

            {/* Heatmap via Canvas */}
            <div style={{ background: 'rgba(0,0,0,0.3)', borderRadius: 8, border: '1px solid rgba(255,255,255,0.06)', padding: 8 }}>
                <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 4 }}>|ψ(x,t)|² Heatmap</div>
                <div style={{ position: 'relative', width: heatW, height: heatH, marginLeft: PAD.left, background: '#111822' }}>
                    <canvas
                        ref={canvasRef}
                        width={N}
                        height={T}
                        style={{ width: '100%', height: '100%', imageRendering: 'pixelated' }}
                    />
                    {/* t-cursor line */}
                    <div style={{
                        position: 'absolute',
                        left: 0,
                        right: 0,
                        top: `${((T - 1 - timeIdx) / T) * 100}%`,
                        height: 1,
                        background: 'rgba(251, 191, 36, 0.8)',
                        boxShadow: '0 0 4px rgba(251, 191, 36, 0.5)'
                    }} />
                </div>
                {/* Axis labels */}
                <svg width={CHART_W} height={20} style={{ display: 'block', marginTop: 4 }}>
                    <text x={PAD.left + heatW / 2} y={14} textAnchor="middle" fill="#6b7280" fontSize={9}>Position x</text>
                    <text x={PAD.left} y={14} textAnchor="start" fill="#6b7280" fontSize={9}>{xMin.toFixed(1)}</text>
                    <text x={PAD.left + heatW} y={14} textAnchor="end" fill="#6b7280" fontSize={9}>{xMax.toFixed(1)}</text>
                </svg>
            </div>

            {/* Current time snapshot */}
            <ChartContainer title={`|ψ(x, t=${te.time_grid[timeIdx]?.toFixed(2)})|²`}>
                <Axes xLabel="x" yLabel="|ψ|²" xTicks={makeXTicks(xMin, xMax, 5)}
                    yTicks={makeYTicks(0, maxPsi * 1.1, 4)} />
                {/* Visual Potential V(x) overlay */}
                <LinePath xData={x} yData={scaled_V} color="#3f3f46" strokeWidth={2}
                    xMin={xMin} xMax={xMax} yMin={0} yMax={maxPsi * 1.1} />
                <FillPath xData={x} yData={currentPsi} color="#8b5cf6" xMin={xMin} xMax={xMax} yMin={0} yMax={maxPsi * 1.1} />
                <LinePath xData={x} yData={currentPsi} color="#8b5cf6" xMin={xMin} xMax={xMax} yMin={0} yMax={maxPsi * 1.1} />
                {/* Initial state overlay */}
                <LinePath xData={x} yData={te.initial_state} color="#22c55e" strokeWidth={1}
                    xMin={xMin} xMax={xMax} yMin={0} yMax={maxPsi * 1.1} />
            </ChartContainer>

            {/* Expected Value <x> trajectory */}
            <ChartContainer title={`Expected Position ⟨x⟩ over Time`}>
                <Axes xLabel="Time t" yLabel="Position ⟨x⟩"
                    xTicks={makeXTicks(0, tMax, 5)}
                    yTicks={makeYTicks(Math.min(-1, expXMin), Math.max(1, expXMax), 4)} />
                <LinePath xData={te.time_grid} yData={expectedX} color="#f43f5e" strokeWidth={2}
                    xMin={0} xMax={tMax} yMin={Math.min(-1, expXMin)} yMax={Math.max(1, expXMax)} />
                {/* Current time dot */}
                <circle
                    cx={PAD.left + ((te.time_grid[timeIdx] - 0) / (tMax || 1)) * INNER_W}
                    cy={PAD.top + INNER_H - ((expectedX[timeIdx] - Math.min(-1, expXMin)) / (Math.max(1, expXMax) - Math.min(-1, expXMin) || 1)) * INNER_H}
                    r={4} fill="#fbbf24" stroke="#000" strokeWidth={1}
                />
            </ChartContainer>

            {/* Eigenstate expansion coefficients */}
            <div style={{ background: 'rgba(0,0,0,0.3)', borderRadius: 8, border: '1px solid rgba(255,255,255,0.06)', padding: 8 }}>
                <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 2 }}>Initial Eigenstate Occupation |cₙ|² <span style={{ color: '#4b5563' }}>(Conserved Quantity)</span></div>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
                    {te.initial_coefficients.map((c, i) => (
                        <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                            <div style={{
                                width: 20, height: Math.max(2, c * 60),
                                background: `rgba(139,92,246,${0.3 + c * 0.7})`,
                                borderRadius: 2,
                                alignSelf: 'flex-end',
                            }} />
                            <span style={{ fontSize: 7, color: '#6b7280' }}>n{i}</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

/** Scattering T(E)/R(E) view */
function ScatteringView({ result }: { result: PhysicsResult }) {
    const sc = result.scattering;
    const [selectedSample, setSelectedSample] = useState(0);

    if (!sc || !sc.energy_range || sc.energy_range.length === 0) {
        return <div style={{ color: '#ef4444', fontSize: 13, padding: 20 }}>⚠️ Scattering data not available for this run. Please click 'Initiate Computation' again.</div>;
    }

    const eMin = Math.min(...sc.energy_range);
    const eMax = Math.max(...sc.energy_range);

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {/* T(E) and R(E) chart */}
            <ChartContainer title="Transmission T(E) & Reflection R(E)">
                <Axes xLabel="Energy E" yLabel="Probability"
                    xTicks={makeXTicks(eMin, eMax, 5)}
                    yTicks={makeYTicks(0, 1, 4)} />
                <LinePath xData={sc.energy_range} yData={sc.transmission} color="#22c55e"
                    xMin={eMin} xMax={eMax} yMin={0} yMax={1} strokeWidth={1.5} />
                <LinePath xData={sc.energy_range} yData={sc.reflection} color="#ef4444"
                    xMin={eMin} xMax={eMax} yMin={0} yMax={1} strokeWidth={1.5} />
                {/* Resonance markers */}
                {sc.resonances.map((Eres, i) => {
                    const px = PAD.left + ((Eres - eMin) / (eMax - eMin || 1)) * INNER_W;
                    return (
                        <g key={i}>
                            <line x1={px} x2={px} y1={PAD.top} y2={PAD.top + INNER_H}
                                stroke="#fbbf24" strokeWidth={1} strokeDasharray="3,3" opacity={0.6} />
                            <text x={px} y={PAD.top - 4} textAnchor="middle" fill="#fbbf24" fontSize={8}>
                                E={Eres.toFixed(2)}
                            </text>
                        </g>
                    );
                })}
                {/* Legend */}
                <line x1={PAD.left + INNER_W - 80} x2={PAD.left + INNER_W - 65} y1={PAD.top + 8} y2={PAD.top + 8} stroke="#22c55e" strokeWidth={2} />
                <text x={PAD.left + INNER_W - 60} y={PAD.top + 11} fill="#9ca3af" fontSize={8}>T(E)</text>
                <line x1={PAD.left + INNER_W - 40} x2={PAD.left + INNER_W - 25} y1={PAD.top + 8} y2={PAD.top + 8} stroke="#ef4444" strokeWidth={2} />
                <text x={PAD.left + INNER_W - 20} y={PAD.top + 11} fill="#9ca3af" fontSize={8}>R(E)</text>
            </ChartContainer>

            {/* Resonance list */}
            {sc.resonances.length > 0 && (
                <div style={{ background: 'rgba(251,191,36,0.05)', border: '1px solid rgba(251,191,36,0.15)', borderRadius: 8, padding: 8 }}>
                    <div style={{ fontSize: 10, color: '#d97706', fontWeight: 600, marginBottom: 4 }}>⚡ Resonances — Transmission Peaks</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {sc.resonances.map((E, i) => (
                            <div key={i} style={{
                                background: 'rgba(251,191,36,0.1)', borderRadius: 4, padding: '2px 8px',
                                fontSize: 11, color: '#fbbf24', fontFamily: 'monospace'
                            }}>
                                E{i + 1} = {E.toFixed(3)}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Sample wavefunction selector */}
            {sc.sample_wavefunctions.length > 0 && (
                <>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {sc.sample_wavefunctions.map((sw, i) => (
                            <button key={i} onClick={() => setSelectedSample(i)}
                                style={{
                                    padding: '3px 8px', fontSize: 10, borderRadius: 4, cursor: 'pointer',
                                    background: selectedSample === i ? 'rgba(34,197,94,0.2)' : 'rgba(255,255,255,0.04)',
                                    border: `1px solid ${selectedSample === i ? '#22c55e' : '#374151'}`,
                                    color: selectedSample === i ? '#22c55e' : '#9ca3af',
                                }}>
                                E={sw.energy.toFixed(1)} (T={sw.transmission.toFixed(2)})
                            </button>
                        ))}
                    </div>
                    <ChartContainer title={`|ψ(x)|² at E=${sc.sample_wavefunctions[selectedSample]?.energy.toFixed(2)}, T=${sc.sample_wavefunctions[selectedSample]?.transmission.toFixed(3)}`}>
                        <Axes xLabel="x" yLabel="|ψ|²"
                            xTicks={makeXTicks(Math.min(...(result.x_grid || [0])), Math.max(...(result.x_grid || [1])), 5)}
                            yTicks={makeYTicks(0, Math.max(...(sc.sample_wavefunctions[selectedSample]?.psi_sq || [1])) * 1.1, 4)} />
                        <FillPath xData={result.x_grid || []}
                            yData={sc.sample_wavefunctions[selectedSample]?.psi_sq || []}
                            color="#22c55e"
                            xMin={Math.min(...(result.x_grid || [0]))}
                            xMax={Math.max(...(result.x_grid || [1]))}
                            yMin={0}
                            yMax={Math.max(...(sc.sample_wavefunctions[selectedSample]?.psi_sq || [1])) * 1.1} />
                        <LinePath xData={result.x_grid || []}
                            yData={sc.sample_wavefunctions[selectedSample]?.psi_sq || []}
                            color="#22c55e"
                            xMin={Math.min(...(result.x_grid || [0]))}
                            xMax={Math.max(...(result.x_grid || [1]))}
                            yMin={0}
                            yMax={Math.max(...(sc.sample_wavefunctions[selectedSample]?.psi_sq || [1])) * 1.1} />
                    </ChartContainer>
                </>
            )}
        </div>
    );
}

/** Bound state view (existing charts) */
function BoundStateView({ result }: { result: PhysicsResult }) {
    const [selectedIndices, setSelectedIndices] = useState([
        0,
        result.eigenvalues.length > 1 ? 1 : 0
    ]);

    const wf = useMemo(() => extractWavefunction(result, selectedIndices[0]), [result, selectedIndices[0]]);
    const wf2 = useMemo(() => extractWavefunction(result, selectedIndices[1]), [result, selectedIndices[1]]);
    const pot = useMemo(() => extractPotential(result), [result]);

    const xMin = wf.x.length ? Math.min(...wf.x) : 0;
    const xMax = wf.x.length ? Math.max(...wf.x) : 1;

    const pData1 = useMemo(() => extractMomentum(result, selectedIndices[0]), [result, selectedIndices[0]]);
    const pData2 = useMemo(() => {
        if (result.eigenvalues.length <= 1) return [];
        return extractMomentum(result, selectedIndices[1]);
    }, [result, selectedIndices[1]]);

    const pTicksRange = useMemo(() => {
        if (!pData1.length || !result.p_grid?.length) return { min: -5, max: 5 };
        return { min: Math.min(...result.p_grid), max: Math.max(...result.p_grid) };
    }, [pData1, result.p_grid]);

    const maxPMag = useMemo(() => {
        let m = 0.01;
        if (pData1.length) m = Math.max(m, ...pData1.map(d => d.mag));
        if (pData2.length) m = Math.max(m, ...pData2.map(d => d.mag));
        return m * 1.1;
    }, [pData1, pData2]);

    const wfYMin = Math.min(...safe(wf.psi), ...safe(wf2.psi));
    const wfYMax = Math.max(...safe(wf.psi), ...safe(wf2.psi), 0.01);
    const psiSqMax = Math.max(...safe(wf.psiSq), ...safe(wf2.psiSq), 0.01);
    const potMin = Math.min(...safe(pot.V));
    const potMax = Math.max(...safe(pot.V), potMin + 0.01);

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {/* State selector */}
            <div style={{
                display: 'flex', gap: 16, padding: '10px 14px',
                background: 'rgba(255,255,255,0.02)', borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.05)', alignItems: 'center'
            }}>
                <span style={{ fontSize: 11, color: '#9ca3af', fontWeight: 500 }}>Display States:</span>
                {[0, 1].map(pi => (
                    <div key={pi} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{ width: 8, height: 8, borderRadius: '50%', background: pi === 0 ? '#6366f1' : '#f97316' }} />
                        <select value={selectedIndices[pi]}
                            onChange={e => {
                                const ns = [...selectedIndices];
                                ns[pi] = parseInt(e.target.value);
                                setSelectedIndices(ns);
                            }}
                            style={{ background: 'rgba(0,0,0,0.3)', color: '#e5e7eb', border: '1px solid #3f3f46', borderRadius: 4, padding: '3px 6px', fontSize: 11 }}>
                            {result.eigenvalues.map((ev, i) => (
                                <option key={i} value={i}>n={i} (E={ev.toFixed(3)})</option>
                            ))}
                        </select>
                    </div>
                ))}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                {/* Wavefunction */}
                <ChartContainer title={`ψ(x) — ${result.equationType}`}>
                    <Axes xLabel="x" yLabel="ψ(x)" xTicks={makeXTicks(xMin, xMax, 5)}
                        yTicks={makeYTicks(wfYMin, wfYMax, 4)} />
                    <LinePath xData={wf.x} yData={wf.psi} color="#6366f1"
                        xMin={xMin} xMax={xMax} yMin={wfYMin} yMax={wfYMax} />
                    <LinePath xData={wf2.x} yData={wf2.psi} color="#f97316" strokeWidth={1}
                        xMin={xMin} xMax={xMax} yMin={wfYMin} yMax={wfYMax} />
                </ChartContainer>

                {/* Probability density */}
                <ChartContainer title="|ψ(x)|²  Probability Density">
                    <Axes xLabel="x" yLabel="|ψ|²" xTicks={makeXTicks(xMin, xMax, 5)}
                        yTicks={makeYTicks(0, psiSqMax, 4)} />
                    <FillPath xData={wf.x} yData={wf.psiSq} color="#6366f1"
                        xMin={xMin} xMax={xMax} yMin={0} yMax={psiSqMax} />
                    <LinePath xData={wf.x} yData={wf.psiSq} color="#22c55e"
                        xMin={xMin} xMax={xMax} yMin={0} yMax={psiSqMax} />
                    <LinePath xData={wf2.x} yData={wf2.psiSq} color="#f97316" strokeWidth={1}
                        xMin={xMin} xMax={xMax} yMin={0} yMax={psiSqMax} />
                </ChartContainer>

                {/* Momentum space */}
                <ChartContainer title="Momentum Space |Φ(p)|">
                    {pData1.length > 0 ? (
                        <>
                            <Axes xLabel="p" yLabel="|Φ(p)|"
                                xTicks={makeXTicks(pTicksRange.min, pTicksRange.max, 5)}
                                yTicks={makeYTicks(0, maxPMag, 4)} />
                            <LinePath xData={pData1.map(d => d.p)} yData={pData1.map(d => d.mag)} color="#8b5cf6"
                                xMin={pTicksRange.min} xMax={pTicksRange.max} yMin={0} yMax={maxPMag} />
                            {pData2.length > 0 && (
                                <LinePath xData={pData2.map(d => d.p)} yData={pData2.map(d => d.mag)} color="#f97316" strokeWidth={1}
                                    xMin={pTicksRange.min} xMax={pTicksRange.max} yMin={0} yMax={maxPMag} />
                            )}
                        </>
                    ) : (
                        <text x={CHART_W / 2} y={CHART_H / 2} textAnchor="middle" fill="#4b5563" fontSize={11}>FFT data unavailable</text>
                    )}
                </ChartContainer>

                {/* Potential */}
                <ChartContainer title={`V(x) — ${result.config?.potentialType || 'Potential'}`}>
                    <Axes xLabel="x" yLabel="V(x)"
                        xTicks={makeXTicks(Math.min(...safe(pot.x)), Math.max(...safe(pot.x)), 5)}
                        yTicks={makeYTicks(potMin, potMax, 4)} />
                    <LinePath xData={pot.x} yData={pot.V} color="#eab308" strokeWidth={2}
                        xMin={Math.min(...safe(pot.x))} xMax={Math.max(...safe(pot.x))} yMin={potMin} yMax={potMax} />
                </ChartContainer>

                {/* Energy spectrum */}
                <ChartContainer title="Energy Spectrum Eₙ vs V(x)">
                    {(() => {
                        const eVals = result.eigenvalues;
                        const yMin2 = Math.min(...safe(pot.V), ...safe(eVals)) * 1.05;
                        const yMax2 = Math.max(...safe(pot.V), ...safe(eVals), 0.1) * 1.15;
                        const yRange = yMax2 - yMin2 || 1;
                        const xMin2 = Math.min(...safe(pot.x));
                        const xMax2 = Math.max(...safe(pot.x));
                        const xRange = xMax2 - xMin2 || 1;

                        // Use exact potential, no visual clamping
                        const potExact = pot.V;

                        return (
                            <>
                                <Axes xLabel="x" yLabel="E"
                                    xTicks={makeXTicks(xMin2, xMax2, 5)}
                                    yTicks={makeYTicks(yMin2, yMax2, 4)} />
                                <LinePath xData={pot.x} yData={potExact} color="#3f3f46" strokeWidth={2}
                                    xMin={xMin2} xMax={xMax2} yMin={yMin2} yMax={yMax2} />
                                {eVals.map((E, i) => {
                                    const eY = PAD.top + INNER_H - ((E - yMin2) / yRange) * INNER_H;
                                    const isSelected = selectedIndices.includes(i);
                                    const color = isSelected ? (selectedIndices[0] === i ? '#6366f1' : '#f97316') : '#22c55e';
                                    // Classical turning points
                                    let leftIdx = pot.V.findIndex(v => v < E + 0.05);
                                    let rightIdx = pot.V.length - 1;
                                    for (let j = pot.V.length - 1; j >= 0; j--) {
                                        if (pot.V[j] < E + 0.05) { rightIdx = j; break; }
                                    }
                                    if (leftIdx < 0) leftIdx = Math.floor(pot.x.length * 0.1);
                                    const px1 = PAD.left + ((pot.x[leftIdx] - xMin2) / xRange) * INNER_W;
                                    const px2 = PAD.left + ((pot.x[rightIdx] - xMin2) / xRange) * INNER_W;
                                    return (
                                        <g key={i}>
                                            <line x1={px1} x2={px2} y1={eY} y2={eY}
                                                stroke={color} strokeWidth={isSelected ? 2 : 1} opacity={isSelected ? 1 : 0.5} />
                                            {isSelected && (
                                                <>
                                                    <text x={px2 + 3} y={eY + 3} fill={color} fontSize={8} fontWeight={600}>n={i}</text>
                                                    <text x={px1 - 3} y={eY - 2} fill={color} fontSize={7} textAnchor="end">{E.toFixed(2)}</text>
                                                </>
                                            )}
                                        </g>
                                    );
                                })}
                            </>
                        );
                    })()}
                </ChartContainer>

                {/* Dirac lower component */}
                {result.equationType === 'Dirac' && (
                    <ChartContainer title="Lower Spinor Component ψ₋(x)">
                        <Axes xLabel="x" yLabel="ψ₋(x)" xTicks={makeXTicks(xMin, xMax, 5)}
                            yTicks={makeYTicks(
                                Math.min(...safe(result.wavefunctions[selectedIndices[0]]?.psi_down || [0])),
                                Math.max(...safe(result.wavefunctions[selectedIndices[0]]?.psi_down || [0.01]), 0.01), 4
                            )} />
                        <LinePath
                            xData={wf.x}
                            yData={result.wavefunctions[selectedIndices[0]]?.psi_down || []}
                            color="#a78bfa"
                            xMin={xMin} xMax={xMax}
                            yMin={Math.min(...safe(result.wavefunctions[selectedIndices[0]]?.psi_down || [0]))}
                            yMax={Math.max(...safe(result.wavefunctions[selectedIndices[0]]?.psi_down || [0.01]), 0.01)} />
                    </ChartContainer>
                )}
            </div>
        </div>
    );
}

// ─── Summary Header ───────────────────────────────────────────────

function ResultsSummary({ result }: { result: PhysicsResult }) {
    const pt = (result.problemType || 'boundstate').toLowerCase();
    const eq = result.equationType || '';

    const badges: { label: string; color: string }[] = [
        { label: eq, color: '#6366f1' },
        {
            label: pt === 'molecular'
                ? 'Molecular'
                : pt === 'boundstate'
                    ? 'Bound State'
                    : pt === 'timeevolution'
                        ? 'Time Evolution'
                        : 'Scattering',
            color: '#22c55e'
        },
        { label: result.equationType === 'Octopus DFT' ? '3D' : (result.dimensionality || '1D'), color: '#eab308' },
    ];
    if (result.verified) badges.push({ label: '✓ Verified', color: '#22c55e' });

    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', padding: '4px 0' }}>
            {badges.map((b, i) => (
                <span key={i} style={{
                    fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 12,
                    background: `${b.color}20`, border: `1px solid ${b.color}40`, color: b.color
                }}>{b.label}</span>
            ))}
            {result.computationTime > 0 && (
                <span style={{ fontSize: 10, color: '#4b5563', marginLeft: 'auto' }}>
                    {result.computationTime.toFixed(2)}s
                </span>
            )}
        </div>
    );
}

// ─── Main Export ─────────────────────────────────────────────────

export default function ResultsPanel({ result }: { result: PhysicsResult }) {
    const [isGenerating, setIsGenerating] = React.useState(false);
    const [genError, setGenError] = React.useState<string | null>(null);

    const handleGenerateExplanation = async () => {
        setIsGenerating(true);
        setGenError(null);
        try {
            const res = await fetch(`${API_BASE}/api/physics/explain`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(result)
            });
            const data = await res.json();
            if (res.ok && data.status === 'success') {
                window.open(`${API_BASE}/api/physics/explanation`, '_blank');
            } else {
                setGenError(data.error || 'Failed to generate explanation');
            }
        } catch (e: any) {
            setGenError(e.message);
        } finally {
            setIsGenerating(false);
        }
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '8px 0' }}>
            <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>

            {/* Summary row */}
            <ResultsSummary result={result} />

            {/* AI Explanation button */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button onClick={handleGenerateExplanation} disabled={isGenerating} style={{
                    background: 'linear-gradient(to right, #2563eb, #4f46e5)', color: 'white',
                    padding: '6px 14px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                    border: 'none', cursor: isGenerating ? 'not-allowed' : 'pointer', opacity: isGenerating ? 0.7 : 1,
                    display: 'flex', alignItems: 'center', gap: 6,
                }}>
                    {isGenerating ? (
                        <span style={{ width: 12, height: 12, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: 'white', borderRadius: '50%', animation: 'spin 1s linear infinite', display: 'inline-block' }} />
                    ) : '✦'}
                    {isGenerating ? 'Generating...' : 'Generate AI Explanation'}
                </button>
                {genError && <span style={{ fontSize: 11, color: '#ef4444' }}>{genError}</span>}
            </div>

            {/* Adaptive view based on problem type */}
            {/* Priority: molecular > timeevolution > scattering > default boundstate */}
            {result.molecular ? (
                <MolecularView result={result} />
            ) : result.timeEvolution ? (
                <TimeEvolutionView result={result} />
            ) : result.scattering ? (
                <ScatteringView result={result} />
            ) : (
                <BoundStateView result={result} />
            )}
        </div>
    );
}

// ─── Molecular View ────────────────────────────────────────────────

function MolecularView({ result }: { result: PhysicsResult }) {
    const mol = result.molecular;
    const [selectedState, setSelectedState] = React.useState(0);

    if (!mol) return null;

    // ── Optical Absorption Spectrum (TD mode) ──
    if (mol.calcMode === 'td' && mol.optical_spectrum) {
        const { energy_ev, cross_section } = mol.optical_spectrum;
        if (!energy_ev || energy_ev.length === 0) {
            return <div style={{ color: '#8892a4', fontSize: 12, padding: 20 }}>Waiting for spectral data…</div>;
        }
        const eMax = Math.max(...energy_ev);
        const csMax = Math.max(...cross_section);
        return (
            <div style={{ display: 'grid', gap: 12 }}>
                <ChartContainer title={`Optical Absorption Spectrum — ${mol.moleculeName}`}>
                    <Axes xMin={0} xMax={eMax} yMin={0} yMax={csMax} xLabel="Energy (eV)" yLabel="σ (Å²/eV)" />
                    <LinePath xData={energy_ev} yData={cross_section} color="#00d4ff" strokeWidth={2}
                        xMin={0} xMax={eMax} yMin={0} yMax={csMax} />
                </ChartContainer>
                {/* TD Dipole Chart — if backend supplied time-domain data */}
                {mol.td_dipole && mol.td_dipole.time.length > 0 && (
                    <TdDipolePanel dipole={mol.td_dipole} />
                )}
            </div>
        );
    }

    // ── Ground State Results ──
    const levels = mol.energy_levels || [];
    const homoEV = mol.homo_energy;
    const lumoEV = mol.lumo_energy;
    const gapEV = homoEV != null && lumoEV != null ? lumoEV - homoEV : null;

    // Wavefunction visualization (populated if axis_x output was enabled)
    const wf = result.wavefunctions?.[selectedState];
    const x = result.x_grid || [];
    const psi = wf?.psi_up || [];
    const psiSq = psi.map((v: number) => v * v);
    const potArr = result.potential_V || [];
    const xMin = x.length ? Math.min(...x) : 0;
    const xMax = x.length ? Math.max(...x) : 1;
    const psiMax = psiSq.length ? Math.max(...psiSq.filter(isFinite), 0.01) : 0.01;
    const potMin = potArr.length ? Math.min(...potArr.filter(isFinite)) : 0;
    const potMax = potArr.length ? Math.max(...potArr.filter(isFinite), potMin + 0.01) : 1;
    // Scale potential to overlay on wavefunction chart
    const potRange = potMax - potMin || 1;
    const scaledPot = potArr.map(v => ((v - potMin) / potRange) * psiMax * 0.4);
    const levelsMin = levels.length ? Math.min(...levels, homoEV ?? 0) - 2 : -20;
    const levelsMax = levels.length ? Math.max(...levels, lumoEV ?? 0) + 2 : 2;

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

            {/* Convergence & energy summary banner */}
            <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 8,
                background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.12)',
                borderRadius: 8, padding: '10px 14px',
            }}>
                <MetricCell label="Molecule" value={mol.moleculeName} accent="#00d4ff" />
                <MetricCell label="SCF Converged" value={mol.converged ? '✓ Yes' : '✗ No'}
                    accent={mol.converged ? '#22c55e' : '#ef4444'} />
                <MetricCell label="SCF Iterations" value={mol.scf_iterations != null ? String(mol.scf_iterations) : '—'} accent="#8892a4" />
                {mol.total_energy_hartree != null && (
                    <MetricCell label="Total Energy" value={`${mol.total_energy_hartree.toFixed(5)} H`} accent="#8892a4" />
                )}
                {homoEV != null && <MetricCell label="HOMO" value={`${homoEV.toFixed(3)} eV`} accent="#22c55e" />}
                {lumoEV != null && <MetricCell label="LUMO" value={`${lumoEV.toFixed(3)} eV`} accent="#ef4444" />}
                {gapEV != null && <MetricCell label="Gap (HOMO-LUMO)" value={`${gapEV.toFixed(3)} eV`} accent="#00d4ff" />}
            </div>

            {/* Kohn-Sham energy level diagram */}
            {levels.length > 0 && (
                <ChartContainer title={`Kohn-Sham Energy Levels — ${mol.moleculeName} (eV)`}>
                    <Axes xMin={0} xMax={1} yMin={levelsMin} yMax={levelsMax} yLabel="E (eV)" />
                    {levels.map((e, i) => {
                        const isHomo = homoEV != null && Math.abs(e - homoEV) < 0.001;
                        const isLumo = lumoEV != null && Math.abs(e - lumoEV) < 0.001;
                        const color = isHomo ? '#22c55e' : isLumo ? '#ef4444' : '#00d4ff';
                        const y = PAD.top + INNER_H - ((e - levelsMin) / ((levelsMax - levelsMin) || 1)) * INNER_H;
                        return (
                            <g key={i}>
                                <line x1={PAD.left + INNER_W * 0.15} x2={PAD.left + INNER_W * 0.85}
                                    y1={y} y2={y} stroke={color} strokeWidth={isHomo || isLumo ? 2 : 1}
                                    opacity={isHomo || isLumo ? 1 : 0.5} />
                                <text x={PAD.left + INNER_W * 0.87} y={y + 3} fill={color} fontSize={8}>
                                    {isHomo ? 'HOMO' : isLumo ? 'LUMO' : `n=${i}`}
                                </text>
                                <text x={PAD.left + INNER_W * 0.13} y={y + 3} fill={color} fontSize={7} textAnchor="end">
                                    {e.toFixed(2)}
                                </text>
                            </g>
                        );
                    })}
                    {/* HOMO-LUMO gap shading */}
                    {homoEV != null && lumoEV != null && (() => {
                        const yHomo = PAD.top + INNER_H - ((homoEV - levelsMin) / ((levelsMax - levelsMin) || 1)) * INNER_H;
                        const yLumo = PAD.top + INNER_H - ((lumoEV - levelsMin) / ((levelsMax - levelsMin) || 1)) * INNER_H;
                        return (
                            <rect x={PAD.left + INNER_W * 0.15} y={yLumo} width={INNER_W * 0.7}
                                height={yHomo - yLumo} fill="rgba(0,212,255,0.06)" stroke="none" />
                        );
                    })()}
                </ChartContainer>
            )}

            {/* SCF Convergence chart */}
            {mol.convergence_data && mol.convergence_data.iterations.length > 0 && (() => {
                const cd = mol.convergence_data!;
                const iters = cd.iterations.map(Number);
                const logDiffs = cd.energy_diff.map(v => isFinite(v) && v > 0 ? Math.log10(v) : -12);
                const logMin = Math.min(...logDiffs.filter(isFinite)) - 0.5;
                const logMax = Math.max(...logDiffs.filter(isFinite)) + 0.5;
                return (
                    <ChartContainer title="SCF Convergence — log₁₀(ΔE/H) per iteration">
                        <Axes xLabel="SCF iteration" yLabel="log₁₀(ΔE)"
                            xMin={iters[0]} xMax={iters[iters.length - 1]}
                            yMin={logMin} yMax={logMax} />
                        <LinePath xData={iters} yData={logDiffs} color="#22c55e"
                            xMin={iters[0]} xMax={iters[iters.length - 1]}
                            yMin={logMin} yMax={logMax} />
                    </ChartContainer>
                );
            })()}

            {/* Wavefunction chart — only if 1D slice data is available */}
            {x.length > 0 && psi.length > 0 && (
                <>
                    {/* State selector */}
                    {result.wavefunctions && result.wavefunctions.length > 1 && (
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            {result.eigenvalues.map((ev, i) => (
                                <button key={i} onClick={() => setSelectedState(i)}
                                    style={{
                                        padding: '3px 8px', fontSize: 10, borderRadius: 4, cursor: 'pointer', border: 'none',
                                        background: selectedState === i ? 'rgba(0,212,255,0.15)' : 'rgba(255,255,255,0.04)',
                                        outline: selectedState === i ? '1px solid #00d4ff' : '1px solid #374151',
                                        color: selectedState === i ? '#00d4ff' : '#8892a4',
                                    }}>
                                    n={i} ({ev.toFixed(3)} H)
                                </button>
                            ))}
                        </div>
                    )}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                        <ChartContainer title={`ψₙ(x) — state ${selectedState}`}>
                            <Axes xLabel="x (Bohr)" yLabel="ψ" xTicks={makeXTicks(xMin, xMax, 5)}
                                yTicks={makeYTicks(Math.min(...psi.filter(isFinite)), Math.max(...psi.filter(isFinite), 0.01), 4)} />
                            <LinePath xData={x} yData={psi} color="#00d4ff" xMin={xMin} xMax={xMax}
                                yMin={Math.min(...psi.filter(isFinite))} yMax={Math.max(...psi.filter(isFinite), 0.01)} />
                        </ChartContainer>
                        <ChartContainer title={`|ψₙ(x)|² — Probability Density`}>
                            <Axes xLabel="x (Bohr)" yLabel="|ψ|²" xTicks={makeXTicks(xMin, xMax, 5)}
                                yTicks={makeYTicks(0, psiMax * 1.1, 4)} />
                            {/* Potential overlay (scaled) */}
                            <LinePath xData={x} yData={scaledPot} color="#3f3f46" strokeWidth={1.5}
                                xMin={xMin} xMax={xMax} yMin={0} yMax={psiMax * 1.1} />
                            <FillPath xData={x} yData={psiSq} color="#00d4ff"
                                xMin={xMin} xMax={xMax} yMin={0} yMax={psiMax * 1.1} />
                            <LinePath xData={x} yData={psiSq} color="#00d4ff"
                                xMin={xMin} xMax={xMax} yMin={0} yMax={psiMax * 1.1} />
                        </ChartContainer>
                    </div>
                </>
            )}

            {/* Electron density n(x) */}
            {result.x_grid && result.x_grid.length > 0 && result.density_1d && result.density_1d.length > 0 && (() => {
                const rho = result.density_1d!;
                const xg = result.x_grid!;
                const rhoMax = Math.max(...rho.filter(isFinite), 0.001);
                return (
                    <ChartContainer title="Electron Density n(x)">
                        <Axes xLabel="x (Bohr)" yLabel="n(x) (a.u.)"
                            xMin={xg[0]} xMax={xg[xg.length - 1]}
                            yMin={0} yMax={rhoMax * 1.1} />
                        <FillPath xData={xg} yData={rho} color="#f59e0b"
                            xMin={xg[0]} xMax={xg[xg.length - 1]}
                            yMin={0} yMax={rhoMax * 1.1} />
                        <LinePath xData={xg} yData={rho} color="#f59e0b"
                            xMin={xg[0]} xMax={xg[xg.length - 1]}
                            yMin={0} yMax={rhoMax * 1.1} />
                    </ChartContainer>
                );
            })()}

            {/* Eigenvalue table */}
            {levels.length > 0 && (
                <div style={{
                    background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: 8, overflow: 'hidden',
                }}>
                    <div style={{ fontSize: 10, color: '#8892a4', padding: '6px 12px', borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 600 }}>
                        Kohn-Sham Eigenvalues
                    </div>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10, fontFamily: 'monospace' }}>
                        <thead>
                            <tr style={{ color: '#4b5563' }}>
                                <th style={{ padding: '4px 12px', textAlign: 'left', fontWeight: 400 }}>n</th>
                                <th style={{ padding: '4px 12px', textAlign: 'right', fontWeight: 400 }}>E (eV)</th>
                                <th style={{ padding: '4px 12px', textAlign: 'right', fontWeight: 400 }}>E (H)</th>
                                <th style={{ padding: '4px 12px', textAlign: 'left', fontWeight: 400 }}>Label</th>
                            </tr>
                        </thead>
                        <tbody>
                            {levels.map((e_eV, i) => {
                                const e_H = result.eigenvalues[i] ?? e_eV / 27.2114;
                                const isHomo = homoEV != null && Math.abs(e_eV - homoEV) < 0.001;
                                const isLumo = lumoEV != null && Math.abs(e_eV - lumoEV) < 0.001;
                                const rowColor = isHomo ? '#22c55e' : isLumo ? '#ef4444' : '#8892a4';
                                return (
                                    <tr key={i} style={{ borderTop: '1px solid rgba(255,255,255,0.03)', color: rowColor }}>
                                        <td style={{ padding: '3px 12px' }}>{i}</td>
                                        <td style={{ padding: '3px 12px', textAlign: 'right' }}>{e_eV.toFixed(4)}</td>
                                        <td style={{ padding: '3px 12px', textAlign: 'right' }}>{e_H.toFixed(5)}</td>
                                        <td style={{ padding: '3px 12px' }}>
                                            {isHomo ? <span style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)', padding: '1px 5px', borderRadius: 3 }}>HOMO</span>
                                                : isLumo ? <span style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', padding: '1px 5px', borderRadius: 3 }}>LUMO</span>
                                                    : ''}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Density of States */}
            {mol.dos_data && mol.dos_data.energy_ev.length > 0 && (() => {
                const dd = mol.dos_data!;
                const dosMax = Math.max(...dd.dos.filter(isFinite), 0.001);
                const eMinDOS = Math.min(...dd.energy_ev.filter(isFinite));
                const eMaxDOS = Math.max(...dd.energy_ev.filter(isFinite));
                return (
                    <ChartContainer title="Density of States (DOS)">
                        <Axes xLabel="E (eV)" yLabel="DOS (states/H)"
                            xMin={eMinDOS} xMax={eMaxDOS}
                            yMin={0} yMax={dosMax * 1.1} />
                        {homoEV != null && (() => {
                            const pxH = PAD.left + ((homoEV - eMinDOS) / ((eMaxDOS - eMinDOS) || 1)) * INNER_W;
                            return <line x1={pxH} x2={pxH} y1={PAD.top} y2={PAD.top + INNER_H}
                                stroke="#22c55e" strokeWidth={1} strokeDasharray="4,3" opacity={0.7} />;
                        })()}
                        <FillPath xData={dd.energy_ev} yData={dd.dos} color="#8b5cf6"
                            xMin={eMinDOS} xMax={eMaxDOS}
                            yMin={0} yMax={dosMax * 1.1} />
                        <LinePath xData={dd.energy_ev} yData={dd.dos} color="#a78bfa"
                            xMin={eMinDOS} xMax={eMaxDOS}
                            yMin={0} yMax={dosMax * 1.1} />
                    </ChartContainer>
                );
            })()}

            {levels.length === 0 && (
                <div style={{ color: '#4b5563', fontSize: 12, padding: 20, textAlign: 'center', border: '1px dashed #1f2937', borderRadius: 8 }}>
                    Kohn-Sham levels not parsed — check that Octopus converged and static/info is readable.
                </div>
            )}

            {/* TD Dipole — available in GS+unocc runs that follow a kick */}
            {mol.td_dipole && mol.td_dipole.time.length > 0 && (
                <TdDipolePanel dipole={mol.td_dipole} />
            )}

            {/* Band Structure — only for periodic crystals */}
            {mol.band_structure_data && mol.band_structure_data.kpoints.length > 0 && (
                <BandStructurePanel data={mol.band_structure_data} />
            )}

            {/* Charge Density Difference */}
            {mol.density_difference_1d && mol.density_difference_1d.x.length > 0 && (
                <DensityDifferencePanel data={mol.density_difference_1d} />
            )}

            {/* VisIt 3D Rendering Panel */}
            <VisItRenderPanel moleculeName={mol.moleculeName} />
        </div>
    );
}

// ─── TD Dipole Panel ──────────────────────────────────────────────

function TdDipolePanel({ dipole }: {
    dipole: { time: number[]; dipole_x: number[]; dipole_y: number[]; dipole_z: number[] };
}) {
    const [axis, setAxis] = React.useState<'x' | 'y' | 'z'>('z');
    const yData = axis === 'x' ? dipole.dipole_x : axis === 'y' ? dipole.dipole_y : dipole.dipole_z;
    const tMin = Math.min(...dipole.time);
    const tMax = Math.max(...dipole.time);
    const yMin = Math.min(...yData.filter(isFinite));
    const yMax = Math.max(...yData.filter(isFinite), yMin + 0.001);
    return (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 8, padding: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <span style={{ fontSize: 10, color: '#8892a4', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    TD Dipole Moment
                </span>
                {(['x', 'y', 'z'] as const).map(a => (
                    <button key={a} onClick={() => setAxis(a)}
                        style={{
                            padding: '2px 8px', fontSize: 10, borderRadius: 3, cursor: 'pointer', border: 'none',
                            background: axis === a ? 'rgba(0,212,255,0.15)' : 'rgba(255,255,255,0.04)',
                            outline: axis === a ? '1px solid rgba(0,212,255,0.4)' : '1px solid #1f2937',
                            color: axis === a ? '#00d4ff' : '#8892a4',
                        }}>d<sub>{a}</sub></button>
                ))}
            </div>
            <ChartContainer title={`d${axis}(t)   [a.u.]`}>
                <Axes xLabel="Time (a.u.)" yLabel={`d${axis}`}
                    xMin={tMin} xMax={tMax} yMin={yMin} yMax={yMax} />
                <LinePath xData={dipole.time} yData={yData} color="#a78bfa" strokeWidth={1.5}
                    xMin={tMin} xMax={tMax} yMin={yMin} yMax={yMax} />
            </ChartContainer>
        </div>
    );
}

// ─── Band Structure Panel ─────────────────────────────────────────

function BandStructurePanel({ data }: {
    data: { kpoints: number[]; bands: number[][]; fermi_energy_ev?: number };
}) {
    const { kpoints, bands, fermi_energy_ev } = data;
    if (!kpoints.length || !bands.length) return null;

    const allEnergies = bands.flat().filter(isFinite);
    const eMin = Math.min(...allEnergies) - 0.5;
    const eMax = Math.max(...allEnergies) + 0.5;
    const kMin = Math.min(...kpoints);
    const kMax = Math.max(...kpoints);

    return (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 8, padding: 8 }}>
            <div style={{ fontSize: 10, color: '#8892a4', fontWeight: 600, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Band Structure
                {fermi_energy_ev != null && (
                    <span style={{ marginLeft: 8, color: '#22c55e', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>
                        E_F = {fermi_energy_ev.toFixed(3)} eV
                    </span>
                )}
            </div>
            <ChartContainer title="E(k)  [eV]">
                <Axes xLabel="k-path" yLabel="E (eV)" xMin={kMin} xMax={kMax} yMin={eMin} yMax={eMax} />
                {/* Fermi level dashed line */}
                {fermi_energy_ev != null && (() => {
                    const yF = PAD.top + INNER_H - ((fermi_energy_ev - eMin) / ((eMax - eMin) || 1)) * INNER_H;
                    return <line x1={PAD.left} x2={PAD.left + INNER_W} y1={yF} y2={yF}
                        stroke="#22c55e" strokeWidth={1} strokeDasharray="4,3" opacity={0.6} />;
                })()}
                {/* Each band as LinePath */}
                {bands.map((band, bi) => (
                    <LinePath key={bi} xData={kpoints} yData={band} color="#00d4ff" strokeWidth={1}
                        xMin={kMin} xMax={kMax} yMin={eMin} yMax={eMax} />
                ))}
            </ChartContainer>
        </div>
    );
}

// ─── Density Difference Panel ─────────────────────────────────────

function DensityDifferencePanel({ data }: {
    data: { x: number[]; delta_rho: number[] };
}) {
    const { x, delta_rho } = data;
    if (!x.length) return null;

    const xMin = Math.min(...x);
    const xMax = Math.max(...x);
    const drMin = Math.min(...delta_rho.filter(isFinite));
    const drMax = Math.max(...delta_rho.filter(isFinite));
    const yAbs = Math.max(Math.abs(drMin), Math.abs(drMax), 0.001);

    return (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 8, padding: 8 }}>
            <div style={{ fontSize: 10, color: '#8892a4', fontWeight: 600, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Charge Density Difference  Δρ = ρ<sub>mol</sub> − Σρ<sub>atom</sub>
            </div>
            <ChartContainer title="Δρ(x)  [a.u.] — Positive = accumulation, Negative = depletion">
                <Axes xLabel="x (Bohr)" yLabel="Δρ" xMin={xMin} xMax={xMax} yMin={-yAbs} yMax={yAbs} />
                {/* Zero baseline */}
                <line x1={PAD.left} x2={PAD.left + INNER_W}
                    y1={PAD.top + INNER_H / 2} y2={PAD.top + INNER_H / 2}
                    stroke="rgba(255,255,255,0.08)" strokeWidth={1} />
                <LinePath xData={x} yData={delta_rho} color="#f59e0b" strokeWidth={1.5}
                    xMin={xMin} xMax={xMax} yMin={-yAbs} yMax={yAbs} />
                {/* Positive fill */}
                {(() => {
                    const posY = delta_rho.map(v => Math.max(0, v));
                    return <FillPath xData={x} yData={posY} color="#22c55e"
                        xMin={xMin} xMax={xMax} yMin={0} yMax={yAbs} />;
                })()}
                {/* Negative fill — mirror trick */}
                {(() => {
                    const negY = delta_rho.map(v => Math.max(0, -v));
                    return <FillPath xData={x} yData={negY} color="#ef4444"
                        xMin={xMin} xMax={xMax} yMin={0} yMax={yAbs} />;
                })()}
            </ChartContainer>
        </div>
    );
}

// ─── VisIt Render Panel ────────────────────────────────────────────

type VisItPlotType = 'wavefunction_1d' | 'density_2d' | 'density_3d';

function VisItRenderPanel({ moleculeName }: { moleculeName: string }) {
    const [plotType, setPlotType] = React.useState<VisItPlotType>('wavefunction_1d');
    const [loading, setLoading] = React.useState(false);
    const [pngBase64, setPngBase64] = React.useState<string | null>(null);
    const [status, setStatus] = React.useState<'idle' | 'not_available' | 'error'>('idle');
    const [errorMsg, setErrorMsg] = React.useState<string | null>(null);

    const PLOT_LABELS: Record<VisItPlotType, string> = {
        wavefunction_1d: 'Wavefunction 1D',
        density_2d:      'Density 2D slice',
        density_3d:      'Density 3D isosurface',
    };

    const handleRender = async () => {
        setLoading(true);
        setPngBase64(null);
        setErrorMsg(null);
        setStatus('idle');
        try {
            const resp = await fetch(`${API_BASE}/api/physics/visualize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ plotType }),
            });
            const data = await resp.json();
            if (data.status === 'ok' && data.pngBase64) {
                setPngBase64(data.pngBase64);
            } else if (data.status === 'not_available') {
                setStatus('not_available');
                setErrorMsg(data.reason);
            } else {
                setStatus('error');
                setErrorMsg(data.reason || 'VisIt render failed');
            }
        } catch (e: any) {
            setStatus('error');
            setErrorMsg(e.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{
            background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 8, padding: 12
        }}>
            <div style={{ fontSize: 10, color: '#8892a4', fontWeight: 600, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                3D Visualization  <span style={{ color: '#3f3f46', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>via VisIt</span>
            </div>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                {(Object.keys(PLOT_LABELS) as VisItPlotType[]).map(pt => (
                    <button key={pt} onClick={() => setPlotType(pt)}
                        style={{
                            padding: '3px 8px', fontSize: 10, borderRadius: 4, cursor: 'pointer', border: 'none',
                            background: plotType === pt ? 'rgba(0,212,255,0.12)' : 'rgba(255,255,255,0.04)',
                            outline: plotType === pt ? '1px solid rgba(0,212,255,0.4)' : '1px solid #1f2937',
                            color: plotType === pt ? '#00d4ff' : '#8892a4',
                        }}>
                        {PLOT_LABELS[pt]}
                    </button>
                ))}
                <button onClick={handleRender} disabled={loading}
                    style={{
                        marginLeft: 4, padding: '3px 10px', fontSize: 10, borderRadius: 4,
                        cursor: loading ? 'wait' : 'pointer', border: 'none',
                        background: loading ? 'rgba(0,212,255,0.05)' : 'rgba(0,212,255,0.15)',
                        outline: '1px solid rgba(0,212,255,0.3)',
                        color: loading ? '#4b5563' : '#00d4ff', fontWeight: 600,
                    }}>
                    {loading ? 'Rendering…' : '▶ Render'}
                </button>
            </div>

            {status === 'not_available' && (
                <div style={{ marginTop: 10, fontSize: 11, color: '#eab308', background: 'rgba(234,179,8,0.06)', border: '1px solid rgba(234,179,8,0.2)', borderRadius: 6, padding: '6px 10px' }}>
                    ⚠ {errorMsg}
                </div>
            )}
            {status === 'error' && (
                <div style={{ marginTop: 10, fontSize: 11, color: '#ef4444', background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 6, padding: '6px 10px' }}>
                    ✗ {errorMsg}
                </div>
            )}
            {pngBase64 && (
                <div style={{ marginTop: 10 }}>
                    <img src={`data:image/png;base64,${pngBase64}`} alt={`VisIt render: ${moleculeName}`}
                        style={{ maxWidth: '100%', borderRadius: 6, border: '1px solid rgba(255,255,255,0.06)' }} />
                </div>
            )}
            {status === 'idle' && !pngBase64 && !loading && (
                <div style={{ marginTop: 8, fontSize: 10, color: '#374151' }}>
                    Select a plot type and click Render. Requires VisIt installed on Windows host.
                </div>
            )}
        </div>
    );
}

function MetricCell({ label, value, accent }: { label: string; value: string; accent: string }) {
    return (
        <div>
            <div style={{ fontSize: 9, color: '#4b5563', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
            <div style={{ fontSize: 12, color: accent, fontFamily: 'monospace', fontWeight: 600, marginTop: 2 }}>{value}</div>
        </div>
    );
}
