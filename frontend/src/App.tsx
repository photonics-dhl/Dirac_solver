import React, { useState, useEffect } from 'react';
import { Activity, Cpu, Settings2, PlayCircle, Loader2, Atom, Zap, Grid3x3, FlaskConical, ChevronDown, ChevronRight } from 'lucide-react';
import DevFlowDashboard from './DevFlowDashboard';
import ResultsPanel from './ResultsPanel'; type TabId = 'solver' | 'devflow';

export default function App() {
    const [activeTab, setActiveTab] = useState<TabId>('solver')

    return (
        <div className="h-screen flex flex-col text-white font-sans" style={{ background: '#0a0e1a' }}>
            {/* ── Top Nav Bar ── */}
            <div className="flex items-center gap-3 px-8 py-3 shrink-0" style={{ borderBottom: '1px solid #1a2035' }}>
                <Activity className="w-6 h-6" style={{ color: '#00d4ff' }} />
                <h1 className="text-xl font-light tracking-tight mr-8" style={{ color: '#e2e8f0', letterSpacing: '-0.02em' }}>Dirac Solver</h1>

                <div className="flex gap-1 rounded-lg p-1" style={{ background: '#0d1525', border: '1px solid #1a2035' }}>
                    <button
                        onClick={() => setActiveTab('solver')}
                        className="flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-colors"
                        style={activeTab === 'solver' ? { background: 'rgba(0,212,255,0.12)', color: '#00d4ff', outline: '1px solid rgba(0,212,255,0.3)' } : { color: '#8892a4' }}
                    >
                        <Cpu className="w-4 h-4" />
                        Dirac Solver
                    </button>
                </div>
            </div>

            {/* ── Tab Content ── */}
            <div className="flex-1 overflow-hidden relative" style={{ display: 'flex' }}>
                <div style={{ display: activeTab === 'solver' ? 'block' : 'none', flex: 1, height: '100%', overflow: 'auto' }}>
                    <DiracSolverView />
                </div>
                <div style={{ display: activeTab === 'devflow' ? 'block' : 'none', flex: 1, height: '100%' }}>
                    <DevFlowDashboard />
                </div>
            </div>
        </div>
    )
}

// ═══════════════════════════════════════════════════════════════════
// Collapsible Section Component
// ═══════════════════════════════════════════════════════════════════
function Section({ title, icon, defaultOpen = true, children }: {
    title: string; icon: React.ReactNode; defaultOpen?: boolean; children: React.ReactNode
}) {
    const [open, setOpen] = useState(defaultOpen);
    return (
        <div className="rounded-xl overflow-hidden mb-3" style={{ border: '1px solid #1a2035' }}>
            <button onClick={() => setOpen(!open)}
                className="w-full flex items-center gap-2 px-4 py-3 transition-colors text-left"
                style={{ background: '#0d1525' }}>
                {open ? <ChevronDown className="w-4 h-4" style={{ color: '#8892a4' }} /> : <ChevronRight className="w-4 h-4" style={{ color: '#8892a4' }} />}
                {icon}
                <span className="text-sm font-medium" style={{ color: '#cbd5e1' }}>{title}</span>
            </button>
            {open && <div className="p-4 space-y-3" style={{ background: '#060d1a' }}>{children}</div>}
        </div>
    );
}

// ═══════════════════════════════════════════════════════════════════
// Field Component — labeled input/select with consistent styling
// ═══════════════════════════════════════════════════════════════════
function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
    return (
        <div className="space-y-1">
            <label className="text-xs font-medium" style={{ color: '#8892a4' }}>{label}</label>
            {children}
            {hint && <p className="text-[10px] mt-0.5" style={{ color: '#455060' }}>{hint}</p>}
        </div>
    );
}

const inputClass = "w-full rounded-lg px-3 py-2 text-sm text-white outline-none transition-colors" +
    " bg-[#0a1220] border border-[#1e2d45] focus:border-[#00d4ff] focus:ring-1 focus:ring-[#00d4ff] focus:ring-opacity-30";
const selectClass = inputClass;

// ═══════════════════════════════════════════════════════════════════
// Dirac Solver View — COMSOL-style multi-panel physics config
// ═══════════════════════════════════════════════════════════════════
function DiracSolverView() {
    // ── Physical Constants ──
    const [unitSystem, setUnitSystem] = useState('natural');
    const [particleMass, setParticleMass] = useState('0.511');  // MeV/c²
    const [particleCharge, setParticleCharge] = useState('-1');
    const [electronEnergy, setElectronEnergy] = useState('1.0');  // MeV

    // ── Geometry & Grid ──
    const [dimensionality, setDimensionality] = useState('1D');
    const [spatialRange, setSpatialRange] = useState('10.0');
    const [gridPoints, setGridPoints] = useState('100');
    const [boundaryCondition, setBoundaryCondition] = useState('dirichlet');

    // ── Engine Mode ──
    const [engineMode, setEngineMode] = useState<'local1D' | 'octopus3D'>('local1D');

    // ── Octopus Parameters ──
    const [octopusCalcMode, setOctopusCalcMode] = useState<'gs' | 'td' | 'unocc'>('gs');
    const [octopusDimensions, setOctopusDimensions] = useState('3D');
    const [octopusPeriodic, setOctopusPeriodic] = useState<'off' | 'x' | 'xy' | 'xyz'>('off');
    const [octopusSpacing, setOctopusSpacing] = useState('0.3');
    const [octopusRadius, setOctopusRadius] = useState('5.0');
    const [octopusBoxShape, setOctopusBoxShape] = useState('sphere');
    const [octopusMolecule, setOctopusMolecule] = useState('H2');
    const [octopusTdSteps, setOctopusTdSteps] = useState('200');
    const [octopusTdTimeStep, setOctopusTdTimeStep] = useState('0.05');
    const [octopusPropagator, setOctopusPropagator] = useState('aetrs');
    const [octopusExtraStates, setOctopusExtraStates] = useState('4');
    const [xcFunctional, setXcFunctional] = useState('lda_x+lda_c_pz');
    const [mixingScheme, setMixingScheme] = useState('broyden');
    const [spinComponents, setSpinComponents] = useState('unpolarized');

    // ── Potential Field (Local 1D) ──
    const [potentialType, setPotentialType] = useState('InfiniteWell');
    const [potentialStrength, setPotentialStrength] = useState('-1.0');
    const [wellWidth, setWellWidth] = useState('1.0');
    const [customExpression, setCustomExpression] = useState('');
    const [potentialDataMode, setPotentialDataMode] = useState<'analytical' | 'data'>('analytical');

    // ── Equation & Picture ──
    const [equationType, setEquationType] = useState('Schrodinger');
    const [problemType, setProblemType] = useState('boundstate');
    const [picture, setPicture] = useState('auto');

    // ── Time Evolution Config ──
    const [numTimeSteps, setNumTimeSteps] = useState('50');
    const [totalTime, setTotalTime] = useState('5.0');
    const [gaussianCenter, setGaussianCenter] = useState('0.0');
    const [gaussianWidth, setGaussianWidth] = useState('0.05');
    const [gaussianMomentum, setGaussianMomentum] = useState('5.0');

    // ── Scattering Config ──
    const [scatteringEMin, setScatteringEMin] = useState('0.0');
    const [scatteringEMax, setScatteringEMax] = useState('20.0');
    const [scatteringESteps, setScatteringESteps] = useState('200');

    // ── Execution ──
    const [isComputing, setIsComputing] = useState(false);
    const [status, setStatus] = useState('IDLE');
    const [logs, setLogs] = useState<string[]>(['[System] Solver initialized. Configure parameters and run.']);
    const [result, setResult] = useState<any>(null);
    const [dockerStatus, setDockerStatus] = useState<'checking' | 'online' | 'offline'>('checking');

    useEffect(() => {
        fetch(`${import.meta.env.VITE_MCP_BASE_URL ?? 'http://localhost:8000'}/health`)
            .then(res => res.json())
            .then(data => setDockerStatus(data.status === 'ok' ? 'online' : 'offline'))
            .catch(() => setDockerStatus('offline'));
    }, []);

    // Auto-determine picture
    const effectivePicture = picture === 'auto'
        ? (problemType === 'scattering' ? 'interaction' : 'schrodinger')
        : picture;

    const gridSpacing = parseFloat(spatialRange) / parseInt(gridPoints);

    const handleRun = () => {
        setIsComputing(true);
        setStatus('RUNNING');
        setResult(null);
        const currentLabel = engineMode === 'octopus3D' ? 'Octopus' : equationType;
        const dimLabel = engineMode === 'octopus3D' ? '' : `(${dimensionality}, ${effectivePicture} picture)`;
        setLogs([`[System] Starting ${currentLabel} solver${dimLabel}...`]);

        try {
            const config = {
                // Physical constants
                unitSystem,
                mass: parseFloat(particleMass),
                charge: parseFloat(particleCharge),
                energy: parseFloat(electronEnergy),
                // Geometry
                dimensionality,
                spatialRange: parseFloat(spatialRange),
                gridPoints: parseInt(gridPoints),
                gridSpacing,
                boundaryCondition,
                // Potential
                potentialType,
                potentialStrength: parseFloat(potentialStrength),
                wellWidth: parseFloat(wellWidth),
                customExpression: potentialType === 'Custom' ? customExpression : undefined,
                potentialDataMode,
                // Equation
                equationType,
                problemType,
                picture: effectivePicture,
                // Time evolution
                numTimeSteps: parseInt(numTimeSteps),
                totalTime: parseFloat(totalTime),
                gaussianCenter: parseFloat(gaussianCenter),
                gaussianWidth: parseFloat(gaussianWidth),
                gaussianMomentum: parseFloat(gaussianMomentum),
                // Scattering
                scatteringEnergyMin: parseFloat(scatteringEMin),
                scatteringEnergyMax: parseFloat(scatteringEMax),
                scatteringEnergySteps: parseInt(scatteringESteps),
                // Octopus Parameters
                engineMode,
                octopusDimensions,
                calcMode: octopusCalcMode,
                octopusPeriodic,
                octopusSpacing: parseFloat(octopusSpacing),
                octopusRadius: parseFloat(octopusRadius),
                octopusBoxShape,
                molecule: octopusMolecule,
                octopusTdSteps: parseInt(octopusTdSteps),
                octopusTdTimeStep: parseFloat(octopusTdTimeStep),
                octopusPropagator,
                octopusExtraStates: parseInt(octopusExtraStates),
                xcFunctional,
                mixingScheme,
                spinComponents,
            };

            const query = encodeURIComponent(JSON.stringify(config));
            // Guard: tracks whether 'result' was received so onerror doesn't
            // show a false error when the server closes the connection after delivery.
            let resultReceived = false;
            const eventSource = new EventSource(`${import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:3001'}/api/physics/stream?config=${query}`);

            eventSource.addEventListener('log', (e: any) => {
                try {
                    const logMsg = JSON.parse(e.data);
                    setLogs(prev => {
                        // Avoid duplicates if the server accidentally sends the same string twice quickly
                        if (prev[prev.length - 1] === logMsg) return prev;
                        return [...prev, logMsg];
                    });
                } catch (err) {
                    console.error("Failed to parse log event", err);
                }
            });

            eventSource.addEventListener('result', (e: any) => {
                resultReceived = true;
                try {
                    const resData = JSON.parse(e.data);
                    setStatus('SUCCESS');
                    setResult(resData);
                    setLogs(prev => [
                        ...prev,
                        `✓ Computation complete via ${resData.engine || (config.engineMode === 'octopus3D' ? 'Octopus-v16' : 'local-python')}.`,
                        `  Results: ${resData.eigenvalues?.length || 0} eigenvalues found.`,
                    ]);
                } catch (err) {
                    setStatus('ERROR');
                    setLogs(prev => [...prev, `✗ Error processing final result`]);
                } finally {
                    eventSource.close();
                    setIsComputing(false);
                }
            });

            // Server-sent pipeline error (named SSE event)
            eventSource.addEventListener('pipeline_error', (e: any) => {
                setStatus('ERROR');
                try {
                    const errData = JSON.parse(e.data);
                    setLogs(prev => [...prev, `✗ Pipeline Error: ${errData.message || 'Unknown error'}`]);
                } catch {
                    setLogs(prev => [...prev, `✗ Pipeline Error: (unparseable)`]);
                }
                eventSource.close();
                setIsComputing(false);
            });

            // Native EventSource connection error (network drop / server crash)
            eventSource.onerror = () => {
                // If the result already arrived, this is just the server closing the
                // connection after delivery — not a real error. Close silently.
                if (resultReceived || eventSource.readyState === EventSource.CLOSED) {
                    eventSource.close();
                    return;
                }
                setStatus('ERROR');
                setLogs(prev => [...prev, `✗ Streaming Error: Connection lost or server crashed`]);
                eventSource.close();
                setIsComputing(false);
            };

        } catch (e: any) {
            setStatus('ERROR');
            setLogs(prev => [...prev, `✗ Initialization Error: ${e.message}`]);
            setIsComputing(false);
        }
    };


    return (
        <div className="h-full flex">
            {/* ── Left: Parameter Panels ── */}
            <div className="w-[380px] shrink-0 overflow-auto p-4" style={{ borderRight: '1px solid #1a2035' }}>
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        <Settings2 className="w-5 h-5" style={{ color: '#00d4ff' }} />
                        <h2 className="text-lg font-medium" style={{ color: '#e2e8f0' }}>Physics Configuration</h2>
                    </div>
                </div>

                {/* Engine Mode Toggle */}
                <div className="flex rounded-lg p-1 mb-4" style={{ background: '#0d1525', border: '1px solid #1a2035' }}>
                    <button onClick={() => setEngineMode('local1D')}
                        className="flex-1 py-1.5 text-xs font-medium rounded-md transition-colors"
                        style={engineMode === 'local1D'
                            ? { background: 'rgba(255,255,255,0.06)', color: '#8892a4', outline: '1px solid #1e2d45' }
                            : { color: '#4b5563' }}>
                        Local 1D
                    </button>
                    <button onClick={() => setEngineMode('octopus3D')}
                        className="flex-1 py-1.5 text-xs font-medium rounded-md transition-colors"
                        style={engineMode === 'octopus3D'
                            ? { background: 'rgba(0,212,255,0.12)', color: '#00d4ff', outline: '1px solid rgba(0,212,255,0.35)' }
                            : { color: '#8892a4' }}>
                        Octopus3D ◈
                    </button>
                </div>

                {engineMode === 'local1D' ? (
                    <>
                        {/* A. Physical Constants */}
                        <Section title="Physical Constants" icon={<Atom className="w-4 h-4 text-purple-400" />}>
                            <Field label="Unit System">
                                <select value={unitSystem} onChange={e => setUnitSystem(e.target.value)} className={selectClass}>
                                    <option value="natural">Natural Units (ℏ=c=1)</option>
                                    <option value="SI">SI Units</option>
                                    <option value="gaussian">Gaussian Units</option>
                                </select>
                            </Field>
                            <div className="grid grid-cols-2 gap-2">
                                <Field label={`Particle Mass${unitSystem === 'natural' ? '' : ' (MeV/c²)'}`}>
                                    <input type="number" value={particleMass} onChange={e => setParticleMass(e.target.value)}
                                        step="0.001" className={inputClass} />
                                </Field>
                                <Field label="Charge (e)">
                                    <input type="number" value={particleCharge} onChange={e => setParticleCharge(e.target.value)}
                                        className={inputClass} />
                                </Field>
                            </div>
                            <Field label={`Electron Energy${unitSystem === 'natural' ? '' : ' (MeV)'}`} hint="Total energy of the incident particle">
                                <input type="number" value={electronEnergy} onChange={e => setElectronEnergy(e.target.value)}
                                    step="0.1" className={inputClass} />
                            </Field>
                            <div className="text-[10px] text-gray-600 bg-[#18181b] rounded-lg p-2 mt-1">
                                α = e²/(4πℏc) ≈ 1/137.036 &nbsp;|&nbsp; λ_C = ℏ/(mc) ≈ {(1 / parseFloat(particleMass || '0.511')).toFixed(4)}
                            </div>
                        </Section>

                        {/* B. Geometry & Grid */}
                        <Section title="Geometry & Grid" icon={<Grid3x3 className="w-4 h-4 text-green-400" />}>
                            <Field label="Dimensionality">
                                <select value={dimensionality} onChange={e => setDimensionality(e.target.value)} className={selectClass}>
                                    <option value="1D">1D — Linear</option>
                                    <option value="2D">2D — Planar</option>
                                    <option value="3D">3D — Volumetric</option>
                                </select>
                            </Field>
                            <div className="grid grid-cols-2 gap-2">
                                <Field label="Spatial Range L" hint="Domain: [-L/2, L/2]">
                                    <input type="number" value={spatialRange} onChange={e => setSpatialRange(e.target.value)}
                                        step="0.5" className={inputClass} />
                                </Field>
                                <Field label="Grid Points N">
                                    <input type="number" value={gridPoints} onChange={e => setGridPoints(e.target.value)}
                                        min="10" step="10" className={inputClass} />
                                </Field>
                            </div>
                            <div className="text-[10px] text-gray-500 bg-[#18181b] rounded-lg p-2">
                                δx = L/N = {isFinite(gridSpacing) ? gridSpacing.toFixed(6) : '—'} &nbsp;|&nbsp;
                                Total cells: {parseInt(gridPoints) || 0}{dimensionality !== '1D' && <span>^{dimensionality === '2D' ? '2' : '3'}</span>}
                            </div>
                            <Field label="Boundary Condition">
                                <select value={boundaryCondition} onChange={e => setBoundaryCondition(e.target.value)} className={selectClass}>
                                    <option value="dirichlet">Dirichlet (ψ=0 at boundary)</option>
                                    <option value="periodic">Periodic (ψ(0) = ψ(L))</option>
                                    <option value="absorbing">Absorbing (PML)</option>
                                </select>
                            </Field>
                        </Section>

                        {/* C. Potential Field */}
                        <Section title="Potential Field V(r)" icon={<Zap className="w-4 h-4 text-yellow-400" />}>
                            <div className="flex gap-2 mb-2">
                                <button onClick={() => setPotentialDataMode('analytical')}
                                    className={`flex-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${potentialDataMode === 'analytical' ? 'bg-yellow-600/20 text-yellow-300 border border-yellow-600' : 'bg-[#1a1a1e] text-gray-500 border border-gray-800'
                                        }`}>Analytical</button>
                                <button onClick={() => setPotentialDataMode('data')}
                                    className={`flex-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${potentialDataMode === 'data' ? 'bg-yellow-600/20 text-yellow-300 border border-yellow-600' : 'bg-[#1a1a1e] text-gray-500 border border-gray-800'
                                        }`}>Data Import</button>
                            </div>
                            {potentialDataMode === 'analytical' ? (
                                <>
                                    <Field label="Potential Type">
                                        <select value={potentialType} onChange={e => setPotentialType(e.target.value)} className={selectClass}>
                                            <option value="FreeSpace">Free Space (V=0)</option>
                                            <option value="InfiniteWell">Infinite Square Well</option>
                                            <option value="FiniteWell">Finite Square Well</option>
                                            <option value="Coulomb">Coulomb (-Ze²/r)</option>
                                            <option value="Harmonic">Harmonic Oscillator (½mω²x²)</option>
                                            <option value="Step">Step Potential</option>
                                            <option value="Custom">Custom Expression</option>
                                        </select>
                                    </Field>
                                    {(potentialType === 'FiniteWell' || potentialType === 'InfiniteWell') && (
                                        <div className="grid grid-cols-2 gap-2">
                                            <Field label="Well Width">
                                                <input type="number" value={wellWidth} onChange={e => setWellWidth(e.target.value)}
                                                    step="0.1" className={inputClass} />
                                            </Field>
                                            <Field label="Depth V₀">
                                                <input type="number" value={potentialStrength} onChange={e => setPotentialStrength(e.target.value)}
                                                    step="0.1" className={inputClass} />
                                            </Field>
                                        </div>
                                    )}
                                    {potentialType === 'Coulomb' && (
                                        <Field label="Nuclear Charge Z">
                                            <input type="number" value={potentialStrength} onChange={e => setPotentialStrength(e.target.value)}
                                                step="1" className={inputClass} />
                                        </Field>
                                    )}
                                    {potentialType === 'Custom' && (
                                        <Field label="V(x) Expression" hint="Use x,y,z variables. e.g., -1/sqrt(x^2+1)">
                                            <input type="text" value={customExpression} onChange={e => setCustomExpression(e.target.value)}
                                                placeholder="-1/sqrt(x^2+1)" className={inputClass} />
                                        </Field>
                                    )}
                                </>
                            ) : (
                                <Field label="Upload V(r) Data" hint="CSV format: x, V(x) per row">
                                    <input type="file" accept=".csv,.json,.txt"
                                        className="w-full text-xs text-gray-400 file:mr-4 file:py-2 file:px-3 file:rounded-lg file:border file:border-gray-700 file:text-sm file:text-gray-300 file:bg-[#1a1a1e] file:cursor-pointer" />
                                </Field>
                            )}
                        </Section>

                        {/* D. Equation & Picture */}
                        <Section title="Equation & Formalism" icon={<FlaskConical className="w-4 h-4 text-cyan-400" />}>
                            <Field label="Governing Equation">
                                <select value={equationType} onChange={e => setEquationType(e.target.value)} className={selectClass}>
                                    <option value="Schrodinger">Schrödinger Equation</option>
                                    <option value="Dirac">Dirac Equation</option>
                                    <option value="KleinGordon">Klein-Gordon Equation</option>
                                </select>
                            </Field>
                            <Field label="Problem Type">
                                <select value={problemType} onChange={e => setProblemType(e.target.value)} className={selectClass}>
                                    <option value="boundstate">Bound State (Eigenvalue)</option>
                                    <option value="timeevolution">Time Evolution</option>
                                    <option value="scattering">Scattering</option>
                                </select>
                            </Field>
                            <Field label="Quantum Picture" hint={`Auto: ${problemType === 'scattering' ? 'Interaction' : 'Schrödinger'} picture`}>
                                <select value={picture} onChange={e => setPicture(e.target.value)} className={selectClass}>
                                    <option value="auto">Auto (recommended)</option>
                                    <option value="schrodinger">Schrödinger Picture</option>
                                    <option value="interaction">Interaction Picture</option>
                                </select>
                            </Field>
                            <div className="text-[10px] text-cyan-800 bg-cyan-950/30 border border-cyan-900/50 rounded-lg p-2">
                                {equationType === 'Dirac' && '(iγᵘ∂ᵘ - m)ψ = 0 — 4-component spinor, relativistic'}
                                {equationType === 'Schrodinger' && 'iℏ∂ψ/∂t = Hψ — non-relativistic wave equation'}
                                {equationType === 'KleinGordon' && '(∂ᵘ∂ᵘ + m²)φ = 0 — spin-0 relativistic'}
                            </div>
                        </Section>

                        {/* E. Time Evolution Config */}
                        {problemType === 'timeevolution' && (
                            <Section title="Time Evolution Config" icon={<FlaskConical className="w-4 h-4 text-pink-400" />}>
                                <div className="grid grid-cols-2 gap-2">
                                    <Field label="Total Time">
                                        <input type="number" value={totalTime} onChange={e => setTotalTime(e.target.value)}
                                            step="1" className={inputClass} />
                                    </Field>
                                    <Field label="Time Steps">
                                        <input type="number" value={numTimeSteps} onChange={e => setNumTimeSteps(e.target.value)}
                                            step="10" className={inputClass} />
                                    </Field>
                                </div>
                                <div className="text-[10px] text-pink-900/70 mb-1 font-medium">Initial Gaussian Wavepacket ψ₀(x)</div>
                                <div className="grid grid-cols-3 gap-2">
                                    <Field label="Center x₀" hint="Fraction of range">
                                        <input type="number" value={gaussianCenter} onChange={e => setGaussianCenter(e.target.value)}
                                            step="0.1" className={inputClass} />
                                    </Field>
                                    <Field label="Width σ" hint="Fraction of range">
                                        <input type="number" value={gaussianWidth} onChange={e => setGaussianWidth(e.target.value)}
                                            step="0.05" min="0.01" className={inputClass} />
                                    </Field>
                                    <Field label="Momentum k₀">
                                        <input type="number" value={gaussianMomentum} onChange={e => setGaussianMomentum(e.target.value)}
                                            step="1" className={inputClass} />
                                    </Field>
                                </div>
                            </Section>
                        )}

                        {/* F. Scattering Config */}
                        {problemType === 'scattering' && (
                            <Section title="Scattering Config" icon={<Zap className="w-4 h-4 text-orange-400" />}>
                                <div className="grid grid-cols-3 gap-2">
                                    <Field label="E min">
                                        <input type="number" value={scatteringEMin} onChange={e => setScatteringEMin(e.target.value)}
                                            step="0.5" className={inputClass} />
                                    </Field>
                                    <Field label="E max">
                                        <input type="number" value={scatteringEMax} onChange={e => setScatteringEMax(e.target.value)}
                                            step="1" className={inputClass} />
                                    </Field>
                                    <Field label="Steps">
                                        <input type="number" value={scatteringESteps} onChange={e => setScatteringESteps(e.target.value)}
                                            step="50" className={inputClass} />
                                    </Field>
                                </div>
                                <div className="text-[10px] text-gray-500 bg-[#18181b] rounded-lg p-2">
                                    T(E) + R(E) = 1 computed via Transfer Matrix Method
                                </div>
                            </Section>
                        )}
                    </>
                ) : (
                    /* ── Octopus Molecular 3D Config ── */
                    <>
                        <Section title="Octopus System Configuration" icon={<Grid3x3 className="w-4 h-4 text-indigo-400" />}>
                            <Field label="Dimensionality">
                                <select value={octopusDimensions} onChange={e => setOctopusDimensions(e.target.value)} className={selectClass}>
                                    <option value="1D">1D — Model System</option>
                                    <option value="2D">2D — Model System</option>
                                    <option value="3D">3D — Molecular System</option>
                                </select>
                            </Field>
                            <Field label="Calculation Mode">
                                <select value={octopusCalcMode} onChange={e => setOctopusCalcMode(e.target.value as any)} className={selectClass}>
                                    <option value="gs">Ground State (GS)</option>
                                    <option value="td">Time-Dependent (TD)</option>
                                    <option value="unocc">Unoccupied (激发态)</option>
                                </select>
                            </Field>

                            <Field label="Periodic Boundary Conditions">
                                <select
                                    value={octopusPeriodic}
                                    onChange={e => setOctopusPeriodic(e.target.value as any)}
                                    className={selectClass}
                                >
                                    <option value="off">None (Dirichlet)</option>
                                    <option value="x">1D — X Axis</option>
                                    <option value="xy">2D — XY Plane</option>
                                    <option value="xyz">3D — XYZ Space</option>
                                </select>
                            </Field>

                            {octopusDimensions !== '1D' ? (
                                <Section title="Molecule / Atom" icon={<Atom className="w-4 h-4 text-blue-400" />}>
                                    <select value={octopusMolecule} onChange={e => setOctopusMolecule(e.target.value)} className={selectClass}>
                                        <option value="H">Hydrogen Atom (H)</option>
                                        <option value="He">Helium Atom (He)</option>
                                        <option value="H2">Hydrogen Molecule (H₂)</option>
                                        <option value="N2">Nitrogen Molecule (N₂)</option>
                                        <option value="CH4">Methane (CH₄)</option>
                                        <option value="Benzene">Benzene (C₆H₆)</option>
                                    </select>
                                    {octopusDimensions === '2D' && (
                                        <div className="text-[10px] text-yellow-600 bg-yellow-950/30 border border-yellow-900/50 rounded-lg p-2 mt-1">
                                            2D mode: bond axis projected onto xy-plane.
                                        </div>
                                    )}
                                </Section>
                            ) : (
                                <Section title="Model Potential" icon={<Zap className="w-4 h-4 text-yellow-400" />}>
                                    <select value={potentialType} onChange={e => setPotentialType(e.target.value)} className={selectClass}>
                                        <option value="Harmonic">Harmonic Oscillator</option>
                                        <option value="InfiniteWell">Infinite Square Well</option>
                                        <option value="Custom">Custom Formula</option>
                                    </select>
                                </Section>
                            )}
                        </Section>

                        <Section title="Mesh & Box Settings" icon={<Grid3x3 className="w-4 h-4 text-green-400" />}>
                            <div className="grid grid-cols-2 gap-2">
                                <Field label="Grid Spacing">
                                    <input type="number" value={octopusSpacing} onChange={e => setOctopusSpacing(e.target.value)} step="0.1" className={inputClass} />
                                </Field>
                                <Field label="Box Radius">
                                    <input type="number" value={octopusRadius} onChange={e => setOctopusRadius(e.target.value)} step="0.5" className={inputClass} />
                                </Field>
                            </div>
                            <Field label="Box Shape">
                                <select value={octopusBoxShape} onChange={e => setOctopusBoxShape(e.target.value)} className={selectClass}>
                                    <option value="sphere">Sphere</option>
                                    <option value="cylinder">Cylinder</option>
                                    <option value="parallelepiped">Parallelepiped</option>
                                </select>
                            </Field>
                        </Section>

                        {octopusCalcMode === 'td' && (
                            <Section title="TD Propagation" icon={<Zap className="w-4 h-4 text-yellow-400" />}>
                                <div className="grid grid-cols-2 gap-2">
                                    <Field label="Max Steps">
                                        <input type="number" value={octopusTdSteps} onChange={e => setOctopusTdSteps(e.target.value)} className={inputClass} />
                                    </Field>
                                    <Field label="Time Step">
                                        <input type="number" value={octopusTdTimeStep} onChange={e => setOctopusTdTimeStep(e.target.value)} step="0.01" className={inputClass} />
                                    </Field>
                                </div>
                                <Field label="Propagator">
                                    <select value={octopusPropagator} onChange={e => setOctopusPropagator(e.target.value)} className={selectClass}>
                                        <option value="aetrs">AETRS (Recommended)</option>
                                        <option value="exp0">Exponential (Order 0)</option>
                                        <option value="etrs">ETRS</option>
                                    </select>
                                </Field>
                            </Section>
                        )}

                        {octopusCalcMode === 'gs' && (
                            <Section title="DFT Settings" icon={<Atom className="w-4 h-4" style={{ color: '#00d4ff' }} />}>
                                <Field label="Extra States" hint="Unoccupied KS states to include">
                                    <input type="number" value={octopusExtraStates} onChange={e => setOctopusExtraStates(e.target.value)} className={inputClass} />
                                </Field>
                                <Field label="XC Functional">
                                    <select value={xcFunctional} onChange={e => setXcFunctional(e.target.value)} className={selectClass}>
                                        <option value="lda_x+lda_c_pz">LDA — PZ (Perdew-Zunger)</option>
                                        <option value="lda_x+lda_c_vwn">LDA — VWN</option>
                                        <option value="gga_x_pbe+gga_c_pbe">GGA — PBE</option>
                                    </select>
                                </Field>
                                <Field label="SCF Mixing Scheme">
                                    <select value={mixingScheme} onChange={e => setMixingScheme(e.target.value)} className={selectClass}>
                                        <option value="broyden">Broyden (recommended)</option>
                                        <option value="linear">Linear Mixing</option>
                                        <option value="diis">DIIS</option>
                                    </select>
                                </Field>
                                <Field label="Spin Components">
                                    <select value={spinComponents} onChange={e => setSpinComponents(e.target.value)} className={selectClass}>
                                        <option value="unpolarized">Unpolarized</option>
                                        <option value="spin_polarized">Spin Polarized</option>
                                        <option value="non_collinear">Non-Collinear</option>
                                    </select>
                                </Field>
                            </Section>
                        )}
                    </>
                )}

                {/* Run Button */}
                <div className="mt-4 pt-3 flex flex-col gap-2" style={{ borderTop: '1px solid #1a2035' }}>
                    <div className="flex justify-between items-center px-1">
                        <span className="text-xs font-mono" style={{ color: '#8892a4' }}>{engineMode === 'octopus3D' ? 'Octopus-v16 MCP' : 'Local Python Engine'}</span>
                        <div className="flex items-center gap-1.5">
                            {dockerStatus === 'checking' && <Loader2 className="w-3 h-3 animate-spin" style={{ color: '#8892a4' }} />}
                            <div className="w-2 h-2 rounded-full" style={{ background: dockerStatus === 'online' ? '#22c55e' : dockerStatus === 'offline' ? '#ef4444' : '#6b7280' }} />
                            <span className="text-xs font-mono uppercase tracking-wider" style={{ color: dockerStatus === 'online' ? '#22c55e' : dockerStatus === 'offline' ? '#ef4444' : '#6b7280' }}>
                                {dockerStatus}
                            </span>
                        </div>
                    </div>
                    <button onClick={handleRun} disabled={isComputing}
                        className="w-full disabled:opacity-40 disabled:cursor-not-allowed font-semibold rounded-xl px-4 py-3 flex items-center justify-center gap-2 transition-all"
                        style={{
                            background: engineMode === 'octopus3D'
                                ? (isComputing ? 'rgba(0,212,255,0.08)' : 'rgba(0,212,255,0.12)')
                                : 'rgba(255,255,255,0.05)',
                            color: engineMode === 'octopus3D' ? '#00d4ff' : '#8892a4',
                            border: engineMode === 'octopus3D' ? '1px solid rgba(0,212,255,0.35)' : '1px solid #1e2d45',
                        }}>
                        {isComputing ? <Loader2 className="w-5 h-5 animate-spin" /> : <PlayCircle className="w-5 h-5" />}
                        {isComputing ? 'Computing...' : 'Initiate Computation'}
                    </button>
                </div>
            </div >

            {/* ── Right: Log + Results ── */}
            <div className="flex-1 flex flex-col overflow-hidden">
                {/* Status Bar */}
                <div className="flex items-center justify-between px-6 py-3" style={{ borderBottom: '1px solid #1a2035', background: '#0a0e1a' }}>
                    <div className="flex items-center gap-3">
                        <Cpu className="w-5 h-5" style={{ color: '#00d4ff' }} />
                        <h2 className="text-sm font-medium" style={{ color: '#8892a4' }}>Computation Output</h2>
                    </div>
                    <div className="text-xs py-1 px-3 rounded font-mono tracking-widest" style={{
                        background: status === 'SUCCESS' ? 'rgba(34,197,94,0.08)' : status === 'ERROR' ? 'rgba(239,68,68,0.08)' : status === 'RUNNING' ? 'rgba(0,212,255,0.08)' : 'rgba(255,255,255,0.04)',
                        color: status === 'SUCCESS' ? '#22c55e' : status === 'ERROR' ? '#ef4444' : status === 'RUNNING' ? '#00d4ff' : '#4b5563',
                        border: `1px solid ${status === 'SUCCESS' ? 'rgba(34,197,94,0.2)' : status === 'ERROR' ? 'rgba(239,68,68,0.2)' : status === 'RUNNING' ? 'rgba(0,212,255,0.2)' : '#1a2035'}`,
                    }}>
                        {status}
                    </div>
                </div>

                {/* Log Area */}
                <div className="flex-1 overflow-auto p-4 font-mono text-[12px] leading-relaxed" style={{ background: '#060d1a' }}>
                    {
                        logs.map((log, i) => (
                            <div key={i} className={`${log.includes('✗') || log.includes('Error') ? 'text-red-400'
                                : log.includes('✓') || log.includes('SUCCESS') ? 'text-green-400'
                                    : log.includes('[System]') ? 'text-blue-400'
                                        : 'text-gray-400'
                                } mb-0.5`}>{log}</div>
                        ))
                    }
                    {
                        isComputing && (
                            <div className="text-gray-500 animate-pulse flex items-center gap-2 mt-2">
                                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
                                Processing quantum computation...
                            </div>
                        )
                    }
                </div>

                {/* Results Summary + Visualization */}
                {
                    result && (
                        <div className="shrink-0 overflow-auto" style={{ maxHeight: '55%', borderTop: '1px solid #1a2035', background: '#0a0e1a' }}>
                            <div className="p-4">
                                <h3 className="text-xs font-mono mb-3 tracking-widest" style={{ color: '#4b5563' }}>COMPUTATION RESULTS</h3>
                                <div className="grid grid-cols-4 gap-3 mb-2">
                                    <div className="rounded-lg p-3" style={{ background: '#0d1525', border: '1px solid #1a2035' }}>
                                        <div className="text-[10px] mb-1" style={{ color: '#4b5563' }}>Eigenvalue E₊</div>
                                        <div className="text-lg font-semibold text-green-400">
                                            {result.eigenvalues?.[0]?.toFixed(4) ?? '—'}
                                        </div>
                                    </div>
                                    <div className="rounded-lg p-3" style={{ background: '#0d1525', border: '1px solid #1a2035' }}>
                                        <div className="text-[10px] mb-1" style={{ color: '#4b5563' }}>Eigenvalue E₋</div>
                                        <div className="text-lg font-semibold text-orange-400">
                                            {result.eigenvalues?.[1]?.toFixed(4) ?? '—'}
                                        </div>
                                    </div>
                                    <div className="rounded-lg p-3" style={{ background: '#0d1525', border: '1px solid #1a2035' }}>
                                        <div className="text-[10px] mb-1" style={{ color: '#4b5563' }}>Verification</div>
                                        <div className={`text-lg font-semibold ${result.verified ? 'text-green-400' : 'text-red-400'}`}>
                                            {result.verified ? '✓ Passed' : '✗ Failed'}
                                        </div>
                                    </div>
                                    <div className="rounded-lg p-3" style={{ background: '#0d1525', border: '1px solid #1a2035' }}>
                                        <div className="text-[10px] mb-1" style={{ color: '#4b5563' }}>Time</div>
                                        <div className="text-lg font-semibold" style={{ color: '#00d4ff' }}>
                                            {result.computationTime?.toFixed(1) ?? '—'}s
                                        </div>
                                    </div>
                                </div>
                                <ResultsPanel result={result} />
                            </div>
                        </div>
                    )
                }
            </div >
        </div >
    )
}
