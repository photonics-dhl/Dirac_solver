/**
 * GeometryEditor — custom molecular/atomic geometry builder for waveguide & lattice models.
 * All internal coordinates are in Bohr (atomic units). Display can switch to Ångström.
 * Patterns work in the YZ cross-section plane; linear_chain goes along X by default.
 *
 * Unit cell: a single atom OR any molecule from MOLECULE_ATOMS.
 * Each lattice node expands the unit cell by shifting its (y, z) position.
 */

import React, { useState, useEffect, useMemo } from 'react';
import { Atom3D, MOLECULE_ATOMS, Mol3DViewer } from './Mol3DViewer';

// ── Constants ──────────────────────────────────────────────────────

const BOHR_PER_ANG = 1.8897259886;
const ANG_PER_BOHR = 1 / BOHR_PER_ANG;

type PatternType =
    | 'regular_ring'
    | 'coupled_rings'
    | 'grid_2d'
    | 'linear_chain'
    | 'hex_packing'
    | 'hole_array'
    | 'manual';

type CoordUnit = 'bohr' | 'angstrom';

// ── Unit-cell expansion helpers ────────────────────────────────────

/** Place the unit cell at each YZ node (X stays from molecule's own coords). */
function expandYZ(nodes: Array<{ y: number; z: number }>, unit: Atom3D[]): Atom3D[] {
    const result: Atom3D[] = [];
    for (const node of nodes) {
        for (const atom of unit) {
            result.push({ symbol: atom.symbol, x: atom.x, y: atom.y + node.y, z: atom.z + node.z });
        }
    }
    return result;
}

/** Place the unit cell at each X node (Y, Z stay from molecule's own coords). */
function expandX(nodes: Array<{ x: number }>, unit: Atom3D[]): Atom3D[] {
    const result: Atom3D[] = [];
    for (const node of nodes) {
        for (const atom of unit) {
            result.push({ symbol: atom.symbol, x: atom.x + node.x, y: atom.y, z: atom.z });
        }
    }
    return result;
}

// ── Pattern generators (all coords in Bohr) ────────────────────────

function genRegularRing(
    n: number, radius: number, cy: number, cz: number
): Array<{ y: number; z: number }> {
    return Array.from({ length: n }, (_, i) => ({
        y: cy + radius * Math.sin((2 * Math.PI * i) / n),
        z: cz + radius * Math.cos((2 * Math.PI * i) / n),
    }));
}

function genGrid2D(
    rows: number, cols: number,
    sY: number, sZ: number,
    oy: number, oz: number,
): Array<{ y: number; z: number }> {
    const nodes: Array<{ y: number; z: number }> = [];
    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            nodes.push({ y: oy + c * sY, z: oz + r * sZ });
        }
    }
    return nodes;
}

function genLinearChain(
    n: number, spacing: number, axis: 'x' | 'y' | 'z', origin: number
): Array<{ x: number }> | Array<{ y: number; z: number }> {
    if (axis === 'x') return Array.from({ length: n }, (_, i) => ({ x: origin + i * spacing }));
    if (axis === 'y') return Array.from({ length: n }, (_, i) => ({ y: origin + i * spacing, z: 0 }));
    return Array.from({ length: n }, (_, i) => ({ y: 0, z: origin + i * spacing }));
}

function genHexPacking(
    rows: number, cols: number, a: number
): Array<{ y: number; z: number }> {
    const rowSpacing = a * Math.sqrt(3) / 2;
    const nodes: Array<{ y: number; z: number }> = [];
    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            nodes.push({
                y: c * a + (r % 2 === 0 ? 0 : a / 2),
                z: r * rowSpacing,
            });
        }
    }
    // Center pattern around origin
    if (nodes.length === 0) return nodes;
    const ysArr = nodes.map(n => n.y);
    const zsArr = nodes.map(n => n.z);
    const meanY = (Math.max(...ysArr) + Math.min(...ysArr)) / 2;
    const meanZ = (Math.max(...zsArr) + Math.min(...zsArr)) / 2;
    return nodes.map(n => ({ y: n.y - meanY, z: n.z - meanZ }));
}

function genHoleArray(
    rows: number, cols: number,
    sY: number, sZ: number,
    holeRows: number, holeCols: number,
): Array<{ y: number; z: number }> {
    const oy = -((cols - 1) * sY) / 2;
    const oz = -((rows - 1) * sZ) / 2;
    const hRs = Math.floor((rows - holeRows) / 2);
    const hCs = Math.floor((cols - holeCols) / 2);
    const nodes: Array<{ y: number; z: number }> = [];
    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            const inHole = r >= hRs && r < hRs + holeRows && c >= hCs && c < hCs + holeCols;
            if (!inHole) nodes.push({ y: oy + c * sY, z: oz + r * sZ });
        }
    }
    return nodes;
}

// ── Component ──────────────────────────────────────────────────────

export interface GeometryEditorProps {
    onChange: (atoms: Atom3D[]) => void;
    boxRadius: number;
    /** Optional preset atoms to offer as a quick-import seed */
    initAtoms?: Atom3D[];
    /** Label for the preset (e.g. "N2") shown in the import button */
    initLabel?: string;
}

export function GeometryEditor({ onChange, boxRadius, initAtoms, initLabel }: GeometryEditorProps) {

    // ── UI state ─────────────────────────────────────────────────
    const [pattern, setPattern] = useState<PatternType>('regular_ring');
    const [unitKey, setUnitKey] = useState<string>('_atom_');  // MOLECULE_ATOMS key or '_atom_'
    const [atomSym, setAtomSym] = useState('H');
    const [coordUnit, setCoordUnit] = useState<CoordUnit>('bohr');

    // All numeric state is stored in BOHR (atomic units)
    // regular_ring
    const [rN, setRN] = useState(6);
    const [rRadius, setRRadius] = useState(10.0);
    const [rCy, setRCy] = useState(0.0);
    const [rCz, setRCz] = useState(0.0);

    // coupled_rings — ring 1
    const [c1N, setC1N] = useState(6);
    const [c1R, setC1R] = useState(6.0);
    const [c1Cy, setC1Cy] = useState(-10.0);
    const [c1Cz, setC1Cz] = useState(0.0);
    // coupled_rings — ring 2
    const [c2N, setC2N] = useState(6);
    const [c2R, setC2R] = useState(6.0);
    const [c2Cy, setC2Cy] = useState(10.0);
    const [c2Cz, setC2Cz] = useState(0.0);

    // grid_2d
    const [gRows, setGRows] = useState(3);
    const [gCols, setGCols] = useState(3);
    const [gSY, setGSY] = useState(5.0);
    const [gSZ, setGSZ] = useState(5.0);
    const [gOY, setGOY] = useState(-5.0);
    const [gOZ, setGOZ] = useState(-5.0);

    // linear_chain
    const [lN, setLN] = useState(5);
    const [lSp, setLSp] = useState(5.0);
    const [lAxis, setLAxis] = useState<'x' | 'y' | 'z'>('x');
    const [lOrig, setLOrig] = useState(-10.0);

    // hex_packing
    const [hRows, setHRows] = useState(3);
    const [hCols, setHCols] = useState(4);
    const [hA, setHA] = useState(5.0);

    // hole_array
    const [hoRows, setHoRows] = useState(5);
    const [hoCols, setHoCols] = useState(5);
    const [hoSY, setHoSY] = useState(5.0);
    const [hoSZ, setHoSZ] = useState(5.0);
    const [hoHR, setHoHR] = useState(1);
    const [hoHC, setHoHC] = useState(1);

    // manual
    const [manAtoms, setManAtoms] = useState<Atom3D[]>([
        { symbol: 'H', x: 0, y: 0, z: 0 },
    ]);

    // ── Unit helpers ──────────────────────────────────────────────
    const toBohr = (v: number) => coordUnit === 'angstrom' ? v * BOHR_PER_ANG : v;
    const disp = (bohrVal: number) =>
        parseFloat((coordUnit === 'angstrom' ? bohrVal * ANG_PER_BOHR : bohrVal).toFixed(5));
    const u = coordUnit === 'angstrom' ? 'Å' : 'Bohr';

    // ── Unit cell atoms ───────────────────────────────────────────
    const unitAtoms: Atom3D[] = useMemo(() => {
        if (unitKey === '_atom_') return [{ symbol: atomSym || 'H', x: 0, y: 0, z: 0 }];
        return MOLECULE_ATOMS[unitKey] ?? [{ symbol: 'H', x: 0, y: 0, z: 0 }];
    }, [unitKey, atomSym]);

    // ── Generate atoms ────────────────────────────────────────────
    const generatedAtoms: Atom3D[] = useMemo(() => {
        if (pattern === 'manual') return manAtoms;

        if (pattern === 'regular_ring') {
            return expandYZ(genRegularRing(rN, rRadius, rCy, rCz), unitAtoms);
        }
        if (pattern === 'coupled_rings') {
            const n1 = genRegularRing(c1N, c1R, c1Cy, c1Cz);
            const n2 = genRegularRing(c2N, c2R, c2Cy, c2Cz);
            return expandYZ([...n1, ...n2], unitAtoms);
        }
        if (pattern === 'grid_2d') {
            return expandYZ(genGrid2D(gRows, gCols, gSY, gSZ, gOY, gOZ), unitAtoms);
        }
        if (pattern === 'linear_chain') {
            if (lAxis === 'x') {
                return expandX(
                    genLinearChain(lN, lSp, 'x', lOrig) as Array<{ x: number }>,
                    unitAtoms,
                );
            }
            return expandYZ(
                genLinearChain(lN, lSp, lAxis, lOrig) as Array<{ y: number; z: number }>,
                unitAtoms,
            );
        }
        if (pattern === 'hex_packing') {
            return expandYZ(genHexPacking(hRows, hCols, hA), unitAtoms);
        }
        if (pattern === 'hole_array') {
            return expandYZ(genHoleArray(hoRows, hoCols, hoSY, hoSZ, hoHR, hoHC), unitAtoms);
        }
        return [];
    }, [
        pattern, unitAtoms,
        rN, rRadius, rCy, rCz,
        c1N, c1R, c1Cy, c1Cz, c2N, c2R, c2Cy, c2Cz,
        gRows, gCols, gSY, gSZ, gOY, gOZ,
        lN, lSp, lAxis, lOrig,
        hRows, hCols, hA,
        hoRows, hoCols, hoSY, hoSZ, hoHR, hoHC,
        manAtoms,
    ]);

    // Notify parent on change
    useEffect(() => { onChange(generatedAtoms); }, [generatedAtoms, onChange]);

    // ── Input helpers ─────────────────────────────────────────────
    const numStyled: React.CSSProperties = {
        width: '100%', background: '#0d1525', border: '1px solid #1f2937',
        borderRadius: 4, color: '#e2e8f0', padding: '3px 6px', fontSize: 10,
        boxSizing: 'border-box',
    };
    const lblStyle: React.CSSProperties = {
        display: 'flex', flexDirection: 'column', gap: 2, fontSize: 10, color: '#8892a4',
    };

    function NI({
        label, bohrVal, setBohr, step = 1.0, min,
    }: { label: string; bohrVal: number; setBohr: (v: number) => void; step?: number; min?: number }) {
        return (
            <label style={lblStyle}>
                <span>{label}</span>
                <input type="number" value={disp(bohrVal)} step={step}
                    min={min}
                    onChange={e => setBohr(toBohr(parseFloat(e.target.value) || 0))}
                    style={numStyled} />
            </label>
        );
    }

    function II({ label, val, set }: { label: string; val: number; set: (v: number) => void }) {
        return (
            <label style={lblStyle}>
                <span>{label}</span>
                <input type="number" value={val} step={1} min={1}
                    onChange={e => set(Math.max(1, parseInt(e.target.value) || 1))}
                    style={numStyled} />
            </label>
        );
    }

    const selStyle: React.CSSProperties = {
        background: '#0d1525', border: '1px solid #1f2937', borderRadius: 4,
        color: '#e2e8f0', padding: '4px 6px', fontSize: 10, width: '100%',
    };
    const grid2: React.CSSProperties = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 10 };
    const grid4: React.CSSProperties = { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 5, marginBottom: 6 };
    const secLabel: React.CSSProperties = { fontSize: 9, color: '#374151', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' };

    // formula summary
    const formula = useMemo(() => {
        const counts: Record<string, number> = {};
        for (const a of generatedAtoms) counts[a.symbol] = (counts[a.symbol] || 0) + 1;
        return Object.entries(counts).sort(([a], [b]) => a.localeCompare(b))
            .map(([s, n]) => n === 1 ? s : `${s}${n}`).join('');
    }, [generatedAtoms]);

    return (
        <div style={{
            background: 'rgba(0,0,0,0.25)',
            border: '1px solid rgba(0,212,255,0.18)',
            borderRadius: 8, padding: 12, marginTop: 8,
        }}>
            {/* ── Header ── */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: '#00d4ff', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                    几何构型编辑器
                </span>
                {/* Import from preset button */}
                {initAtoms && initAtoms.length > 0 && (
                    <button
                        onClick={() => { setPattern('manual'); setManAtoms(initAtoms!); }}
                        title={`将 ${initLabel ?? '预设分子'} 的坐标导入到手动编辑模式`}
                        style={{
                            fontSize: 9, padding: '2px 8px', borderRadius: 3, border: 'none',
                            cursor: 'pointer', background: 'rgba(0,212,255,0.08)',
                            color: '#00d4ff', outline: '1px solid rgba(0,212,255,0.25)',
                        }}
                    >
                        ← 导入 {initLabel ?? '预设'}
                    </button>
                )}
                {/* Coord unit toggle */}
                <div style={{ display: 'flex', border: '1px solid #1f2937', borderRadius: 5, overflow: 'hidden', marginLeft: 'auto' }}>
                    {(['bohr', 'angstrom'] as CoordUnit[]).map(cu => (
                        <button key={cu} onClick={() => setCoordUnit(cu)} style={{
                            padding: '2px 8px', fontSize: 9, cursor: 'pointer', border: 'none',
                            background: coordUnit === cu ? 'rgba(0,212,255,0.15)' : 'transparent',
                            color: coordUnit === cu ? '#00d4ff' : '#4b5563',
                        }}>
                            {cu === 'bohr' ? 'Bohr' : 'Å'}
                        </button>
                    ))}
                </div>
            </div>

            {/* ── Unit Cell ── */}
            <div style={{ marginBottom: 10 }}>
                <div style={secLabel}>单元格 (Unit Cell)</div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <select value={unitKey} onChange={e => setUnitKey(e.target.value)} style={{ ...selStyle, flex: 1 }}>
                        <option value="_atom_">— 单个原子 —</option>
                        <optgroup label="分子 (Molecules)">
                            {Object.keys(MOLECULE_ATOMS).map(k => (
                                <option key={k} value={k}>{k}</option>
                            ))}
                        </optgroup>
                    </select>
                    {unitKey === '_atom_' && (
                        <input type="text" value={atomSym} maxLength={2}
                            onChange={e => setAtomSym(e.target.value.trim() || 'H')}
                            placeholder="元素"
                            style={{ width: 44, background: '#0d1525', border: '1px solid #1f2937', borderRadius: 4, color: '#00d4ff', padding: '4px 6px', fontSize: 11, textAlign: 'center' }} />
                    )}
                </div>
            </div>

            {/* ── Pattern ── */}
            <div style={{ marginBottom: 10 }}>
                <div style={secLabel}>排列模式 (Pattern)</div>
                <select value={pattern} onChange={e => setPattern(e.target.value as PatternType)} style={selStyle}>
                    <option value="regular_ring">正多边形环 — YZ 平面</option>
                    <option value="coupled_rings">耦合环对 — 两个独立环</option>
                    <option value="grid_2d">二维矩阵格栅 — YZ 平面</option>
                    <option value="linear_chain">线性链 — 沿轴排列</option>
                    <option value="hex_packing">六边形密排 (蜂窝)</option>
                    <option value="hole_array">矩阵格栅挖孔 (小孔阵列)</option>
                    <option value="manual">手动输入坐标</option>
                </select>
            </div>

            {/* ── Pattern params ── */}

            {pattern === 'regular_ring' && (
                <div style={grid2}>
                    <II label="N (节点数)" val={rN} set={setRN} />
                    <NI label={`半径 (${u})`} bohrVal={rRadius} setBohr={setRRadius} step={0.5} />
                    <NI label={`中心 Y (${u})`} bohrVal={rCy} setBohr={setRCy} step={0.5} />
                    <NI label={`中心 Z (${u})`} bohrVal={rCz} setBohr={setRCz} step={0.5} />
                </div>
            )}

            {pattern === 'coupled_rings' && (<>
                <div style={{ ...secLabel, marginBottom: 4 }}>环 1</div>
                <div style={grid4}>
                    <II label="N₁" val={c1N} set={setC1N} />
                    <NI label={`R₁ (${u})`} bohrVal={c1R} setBohr={setC1R} step={0.5} />
                    <NI label={`Y₁ (${u})`} bohrVal={c1Cy} setBohr={setC1Cy} step={0.5} />
                    <NI label={`Z₁ (${u})`} bohrVal={c1Cz} setBohr={setC1Cz} step={0.5} />
                </div>
                <div style={secLabel}>环 2</div>
                <div style={{ ...grid4, marginBottom: 10 }}>
                    <II label="N₂" val={c2N} set={setC2N} />
                    <NI label={`R₂ (${u})`} bohrVal={c2R} setBohr={setC2R} step={0.5} />
                    <NI label={`Y₂ (${u})`} bohrVal={c2Cy} setBohr={setC2Cy} step={0.5} />
                    <NI label={`Z₂ (${u})`} bohrVal={c2Cz} setBohr={setC2Cz} step={0.5} />
                </div>
            </>)}

            {pattern === 'grid_2d' && (
                <div style={grid2}>
                    <II label="行数 (Z方向)" val={gRows} set={setGRows} />
                    <II label="列数 (Y方向)" val={gCols} set={setGCols} />
                    <NI label={`间距 ΔY (${u})`} bohrVal={gSY} setBohr={setGSY} step={0.5} />
                    <NI label={`间距 ΔZ (${u})`} bohrVal={gSZ} setBohr={setGSZ} step={0.5} />
                    <NI label={`起点 Y (${u})`} bohrVal={gOY} setBohr={setGOY} step={0.5} />
                    <NI label={`起点 Z (${u})`} bohrVal={gOZ} setBohr={setGOZ} step={0.5} />
                </div>
            )}

            {pattern === 'linear_chain' && (
                <div style={grid2}>
                    <II label="节点数" val={lN} set={setLN} />
                    <NI label={`间距 (${u})`} bohrVal={lSp} setBohr={setLSp} step={0.5} />
                    <label style={lblStyle}>
                        <span>方向轴</span>
                        <select value={lAxis} onChange={e => setLAxis(e.target.value as any)} style={selStyle}>
                            <option value="x">X — 波导传播方向</option>
                            <option value="y">Y</option>
                            <option value="z">Z</option>
                        </select>
                    </label>
                    <NI label={`起点 (${u})`} bohrVal={lOrig} setBohr={setLOrig} step={0.5} />
                </div>
            )}

            {pattern === 'hex_packing' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6, marginBottom: 10 }}>
                    <II label="行数" val={hRows} set={setHRows} />
                    <II label="列数" val={hCols} set={setHCols} />
                    <NI label={`晶格常数 (${u})`} bohrVal={hA} setBohr={setHA} step={0.5} />
                </div>
            )}

            {pattern === 'hole_array' && (
                <div style={grid2}>
                    <II label="总行数" val={hoRows} set={setHoRows} />
                    <II label="总列数" val={hoCols} set={setHoCols} />
                    <NI label={`间距 ΔY (${u})`} bohrVal={hoSY} setBohr={setHoSY} step={0.5} />
                    <NI label={`间距 ΔZ (${u})`} bohrVal={hoSZ} setBohr={setHoSZ} step={0.5} />
                    <II label="孔洞行数" val={hoHR} set={setHoHR} />
                    <II label="孔洞列数" val={hoHC} set={setHoHC} />
                </div>
            )}

            {/* ── Manual table ── */}
            {pattern === 'manual' && (
                <div style={{ marginBottom: 10 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                        <span style={{ fontSize: 10, color: '#8892a4' }}>坐标 ({u})</span>
                        <button
                            onClick={() => setManAtoms(prev => [...prev, { symbol: 'H', x: 0, y: 0, z: 0 }])}
                            style={{
                                fontSize: 9, padding: '2px 8px', borderRadius: 3, border: 'none',
                                cursor: 'pointer', background: 'rgba(0,212,255,0.10)',
                                color: '#00d4ff', outline: '1px solid rgba(0,212,255,0.3)',
                            }}>
                            + 添加原子
                        </button>
                    </div>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 9 }}>
                        <thead>
                            <tr style={{ color: '#4b5563' }}>
                                <th style={{ textAlign: 'left', padding: '2px 4px', width: 38 }}>元素</th>
                                <th style={{ padding: '2px 4px' }}>x</th>
                                <th style={{ padding: '2px 4px' }}>y</th>
                                <th style={{ padding: '2px 4px' }}>z</th>
                                <th style={{ width: 20 }} />
                            </tr>
                        </thead>
                        <tbody>
                            {manAtoms.map((at, i) => (
                                <tr key={i} style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                                    <td style={{ padding: '1px 2px' }}>
                                        <input type="text" value={at.symbol} maxLength={2}
                                            onChange={e => setManAtoms(prev => prev.map((a, j) =>
                                                j === i ? { ...a, symbol: e.target.value.trim() || 'H' } : a))}
                                            style={{ width: 34, background: '#0d1525', border: '1px solid #1f2937', borderRadius: 3, color: '#00d4ff', padding: '2px 4px', textAlign: 'center', fontSize: 9 }} />
                                    </td>
                                    {(['x', 'y', 'z'] as const).map(coord => (
                                        <td key={coord} style={{ padding: '1px 2px' }}>
                                            <input type="number" step={0.1}
                                                value={disp(at[coord])}
                                                onChange={e => {
                                                    const v = toBohr(parseFloat(e.target.value) || 0);
                                                    setManAtoms(prev => prev.map((a, j) => j === i ? { ...a, [coord]: v } : a));
                                                }}
                                                style={{ ...numStyled, padding: '2px 4px' }} />
                                        </td>
                                    ))}
                                    <td style={{ padding: '1px 2px', textAlign: 'center' }}>
                                        <button
                                            onClick={() => setManAtoms(prev => prev.filter((_, j) => j !== i))}
                                            style={{ fontSize: 10, padding: '0 4px', borderRadius: 2, border: 'none', cursor: 'pointer', background: 'rgba(239,68,68,0.12)', color: '#ef4444' }}>
                                            ×
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* ── Summary ── */}
            <div style={{ fontSize: 9, color: '#374151', marginBottom: 4, fontFamily: 'monospace' }}>
                {generatedAtoms.length} 个原子
                {formula ? ` · ${formula}` : ''}
                {generatedAtoms.length === 0 && <span style={{ color: '#ef4444' }}> — 无原子，请检查参数</span>}
            </div>

            {/* ── Octopus coordinate file preview ── */}
            {generatedAtoms.length > 0 && (
                <details style={{ marginBottom: 8 }}>
                    <summary style={{ fontSize: 9, color: '#4b5563', cursor: 'pointer', userSelect: 'none' }}>
                        %Coordinates (Octopus inp 格式，前 {Math.min(50, generatedAtoms.length)} / {generatedAtoms.length} 个原子)
                    </summary>
                    <pre style={{
                        fontSize: 8, color: '#8892a4', fontFamily: "'SF Mono', ui-monospace, monospace",
                        background: '#050912', borderRadius: 4, padding: '6px 8px',
                        marginTop: 4, overflow: 'auto', maxHeight: 180, lineHeight: 1.5,
                    }}>
                        {`%Coordinates\n` +
                         generatedAtoms.slice(0, 50).map(a =>
                             `  '${a.symbol}' | ${a.x.toFixed(6)} | ${a.y.toFixed(6)} | ${a.z.toFixed(6)}`
                         ).join('\n') +
                         `\n%` +
                         (generatedAtoms.length > 50 ? `\n  # ... 还有 ${generatedAtoms.length - 50} 个原子未显示` : '')}
                    </pre>
                </details>
            )}

            {/* ── Live 3D preview ── */}
            <Mol3DViewer
                atoms={generatedAtoms}
                boxRadius={Math.max(boxRadius, 5)}
                width={380}
                height={280}
                showLegend
            />
        </div>
    );
}

export default GeometryEditor;
