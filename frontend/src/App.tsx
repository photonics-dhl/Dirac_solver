import React, { useState, useEffect, Suspense } from 'react';
import { Activity, Cpu, Settings2, PlayCircle, Loader2, Atom, Zap, Grid3x3, FlaskConical } from 'lucide-react';
import { Mol3DViewer, MOLECULE_ATOMS } from './Mol3DViewer';
import { Section } from './components/Section';
import { Field, inputClass, selectClass } from './components/Field';
import { HARTREE_TO_EV, parseScanSpec } from './utils/scanSpec';
import { ErrorBoundary } from './components/ErrorBoundary';
import { RuntimeLog } from './components/RuntimeLog';
import { StatusBadge } from './components/StatusBadge';
import type { RunStatus } from './hooks/useSolverRunner';
import { useOctopusConfig } from './hooks/useOctopusConfig';
import { useMCPHealth } from './hooks/useMCPHealth';
import { useSolverRunner } from './hooks/useSolverRunner';

const ResultsPanel = React.lazy(() => import('./ResultsPanel'));
const GeometryEditor = React.lazy(() => import('./GeometryEditor'));

const ENV_API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/$/, '');
const API_BASE = ENV_API_BASE || '';

export default function App() {
    const { dockerStatus: mcpStatus } = useMCPHealth();

    return (
        <div className="h-screen flex flex-col text-white font-sans" style={{ background: '#0a0e1a' }}>
            {/* ── Top Nav Bar ── */}
            <div className="flex items-center gap-3 px-8 py-3 shrink-0" style={{ borderBottom: '1px solid #1a2035' }}>
                <Activity className="w-6 h-6" style={{ color: '#00d4ff' }} />
                <h1 className="text-xl font-light tracking-tight" style={{ color: '#e2e8f0', letterSpacing: '-0.02em' }}>Dirac Solver</h1>

                {/* MCP Status — right side of nav bar */}
                <div className="ml-auto flex items-center gap-1.5">
                    {mcpStatus === 'checking' && <Loader2 className="w-3 h-3 animate-spin" style={{ color: '#8892a4' }} />}
                    <div className="w-2 h-2 rounded-full" style={{ background: mcpStatus === 'online' ? '#22c55e' : mcpStatus === 'offline' ? '#ef4444' : '#6b7280' }} />
                    <span className="text-xs font-mono uppercase tracking-wider" style={{ color: mcpStatus === 'online' ? '#22c55e' : mcpStatus === 'offline' ? '#ef4444' : '#6b7280' }}>
                        {mcpStatus === 'online' ? 'MCP Online' : mcpStatus === 'offline' ? 'MCP Offline' : 'Connecting...'}
                    </span>
                </div>
            </div>

            {/* ── Main Content ── */}
            <div className="flex-1 overflow-hidden" style={{ height: '100%', overflow: 'auto' }}>
                <DiracSolverView />
            </div>
        </div>
    )
}

// ═══════════════════════════════════════════════════════════════════
// Dirac Solver View — COMSOL-style multi-panel physics config
// ═══════════════════════════════════════════════════════════════════
function DiracSolverView() {
    type CapabilityMatrixRow = {
        category: string;
        support_status: string;
        implementation_priority: string;
        tutorial_count: number;
        canonical_cases?: Array<{ title?: string; url?: string }>;
    };

    type CapabilityMatrixResponse = {
        tutorial_count?: number;
        category_count?: number;
        rows?: CapabilityMatrixRow[];
    };

    type CaseTypeRegistryItem = {
        case_type: string;
        case_count?: number;
        case_ids?: string[];
        matrix_categories?: string[];
        canonical_tutorials?: Array<{
            title?: string;
            url?: string;
            score?: number;
            source_category?: string;
        }>;
    };

    type CaseTypeRegistryResponse = {
        case_types?: CaseTypeRegistryItem[];
        count?: number;
        approved_case_ids?: string[];
        approved_molecules?: string[];
    };

    type HarnessApiResponse = {
        case_id?: string;
        config_hash?: string;
        config?: Record<string, unknown>;
        theory?: Record<string, unknown>;
        computed?: Record<string, unknown>;
        relative_error?: number;
        threshold?: number;
        passed?: boolean;
        harness_constraints?: {
            max_retries?: number;
            timeout_seconds?: number;
            attempts_used?: number;
        };
        solver_summary?: {
            elapsed_seconds?: number;
        };
        escalation?: {
            required?: boolean;
            reason?: string | null;
        };
        event_chain?: Array<Record<string, unknown>>;
        log_refs?: {
            event_log?: string;
            result_json?: string;
        };
        control_loop?: {
            desired_state?: Record<string, unknown>;
            final_observed_state?: Record<string, unknown>;
            quality?: {
                score?: number;
            };
            iterations?: Array<Record<string, unknown>>;
        };
        solver_result?: any;
        detail?: string;
        error?: string;
    };

    type HarnessIterateApiResponse = {
        case_id?: string;
        iterations_requested?: number;
        iterations_completed?: number;
        passed?: boolean;
        best_relative_error?: number;
        history?: HarnessApiResponse[];
        detail?: string;
        error?: string;
    };

    type HarnessBenchmarkReview = {
        case_id?: string;
        final_verdict?: 'PASS' | 'FAIL';
        checks?: Record<string, boolean>;
        delta?: {
            relative_error?: number | null;
            threshold?: number | null;
            margin?: number | null;
        };
        benchmark_review?: {
            final_verdict?: 'PASS' | 'FAIL';
            delta?: {
                relative_error?: number | null;
                threshold?: number | null;
                margin?: number | null;
            };
            next_action?: string;
        };
        next_action?: string;
        repair_type?: string;
        repair_confidence?: number;
    };

    type AgentSuiteCaseCard = {
        scenario_id?: string;
        title?: string;
        status?: string;
        optical_points?: number;
        dipole_points?: number;
        radiation_points?: number;
        eels_points?: number;
        engine?: string;
        scheduler?: {
            job_id?: string;
            job_state?: string;
            queue?: string;
            ncpus?: number;
            mpiprocs?: number;
            selected_node?: string;
            exec_vnode?: string;
        };
        comparison?: {
            metric?: string;
            computed?: number | null;
            reference?: number | null;
            delta?: number | null;
            relative_delta?: number | null;
            tolerance_relative?: number | null;
            within_tolerance?: boolean | null;
        };
    };

    type SuiteTaskId =
        | 'ch4_gs_reference'
        | 'h2o_gs_reference'
        | 'h2o_tddft_absorption'
        | 'h2o_tddft_dipole_response'
        | 'h2o_tddft_radiation_spectrum'
        | 'h2o_tddft_eels_spectrum';

    type AgentSuiteReview = {
        title?: string;
        final_verdict?: string;
        checks?: Record<string, boolean>;
        case_cards?: AgentSuiteCaseCard[];
    };

    type DispatchPhase = {
        phase?: string;
        state?: string;
        at?: string;
        detail?: string;
    };

    type DispatchSummary = {
        status?: string;
        taskId?: string | null;
        reportPath?: string;
        timestamp?: string | null;
        dispatchStatus?: string;
        humanStatus?: string;
        failureReason?: string;
        workflowState?: string;
        workflowEvent?: string;
        workflowRoute?: string;
        phaseStream?: DispatchPhase[];
        physicsResult?: {
            calc_mode?: string;
            molecule_name?: string;
            ground_state_energy_hartree?: number | null;
            homo_energy?: number | null;
            lumo_energy?: number | null;
            absorption_spectrum_points?: number;
            absorption_spectrum?: {
                energy_ev?: number[];
                cross_section?: number[];
            };
            benchmark_delta?: {
                relative_error?: number | null;
                threshold?: number | null;
                within_tolerance?: boolean;
            };
            has_required_fields?: boolean;
            missing_fields?: string[];
        };
    };

    // ── Hooks: config, health, solver ──
    const { config, setters } = useOctopusConfig();
    const { dockerStatus, markRunStarting } = useMCPHealth();
    const {
        isComputing, status, logs, result, resultHistory,
        elapsedSeconds, lastRunSeconds,
        workflowStage,
        run, requestPause,
        setLogs, setResult, setResultHistory,
        setIsComputing, setStatus, setWorkflowStage,
        setRunStartAt, setElapsedSeconds, setLastRunSeconds,
        setActiveRunLabel,
        runInProgressRef: localRunInProgressRef,
    } = useSolverRunner();

    // Derived value (used in JSX; useSolverRunner.buildOctopusConfig computes its own)
    const gridSpacing = parseFloat(config.spatialRange) / parseInt(config.gridPoints);

    const harnessCaseId = 'infinite_well_v1';
    const harnessIterations = '3';
    const [suiteReview, setSuiteReview] = useState<AgentSuiteReview | null>(null);
    const [suiteReportMd, setSuiteReportMd] = useState<string>('');
    const [, setOfficialGsReport] = useState<any | null>(null);
    const [benchmarkReview, setBenchmarkReview] = useState<HarnessBenchmarkReview | null>(null);
    const [dispatchSummary, setDispatchSummary] = useState<DispatchSummary | null>(null);
    const [capabilityMatrix, setCapabilityMatrix] = useState<CapabilityMatrixResponse | null>(null);
    const [caseTypeRegistry, setCaseTypeRegistry] = useState<CaseTypeRegistryResponse | null>(null);
    const [approvedUiMolecules, setApprovedUiMolecules] = useState<Set<string>>(new Set(['CH4', 'N_atom']));
    const activeAbortControllerRef = React.useRef<AbortController | null>(null);

    useEffect(() => {
        let cancelled = false;
        const fetchMatrix = async () => {
            try {
                const resp = await fetch(`${API_BASE}/api/harness/case-registry`);
                if (!resp.ok) return;
                const data: any = await resp.json();
                const rows = Array.isArray(data?.items)
                    ? data.items.map((item: any) => ({
                        category: String(item?.category || item?.case_type || 'unknown'),
                        support_status: String(item?.support_status || 'unknown'),
                        implementation_priority: String(item?.priority || 'P1'),
                        tutorial_count: Number(item?.count || 0),
                    }))
                    : [];
                if (!cancelled) {
                    setCapabilityMatrix({
                        tutorial_count: Number(data?.count || rows.reduce((s: number, r: any) => s + (r.tutorial_count || 0), 0)),
                        category_count: rows.length,
                        rows,
                    });
                }
            } catch {
                // Capability panel is auxiliary; keep solver path resilient.
            }
        };
        fetchMatrix();
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        let cancelled = false;
        const fetchCaseTypes = async () => {
            try {
                const resp = await fetch(`${API_BASE}/api/harness/case-registry`);
                if (!resp.ok) return;
                const data: any = await resp.json();
                const caseTypes: CaseTypeRegistryItem[] = Array.isArray(data?.items)
                    ? data.items.map((item: any) => ({
                        case_type: String(item?.case_type || item?.id || 'unknown'),
                        case_count: Number(item?.count || 0),
                        case_ids: Array.isArray(item?.case_ids) ? item.case_ids : [],
                        matrix_categories: Array.isArray(item?.matrix_categories) ? item.matrix_categories : [],
                        canonical_tutorials: Array.isArray(item?.canonical_tutorials) ? item.canonical_tutorials : [],
                    }))
                    : [];
                if (!cancelled) {
                    setCaseTypeRegistry({
                        case_types: caseTypes,
                        count: Number(data?.count || caseTypes.length),
                        approved_case_ids: Array.isArray(data?.approved_case_ids) ? data.approved_case_ids : [],
                        approved_molecules: Array.isArray(data?.approved_molecules) ? data.approved_molecules : [],
                    });
                    if (Array.isArray(data?.approved_molecules)) {
                        setApprovedUiMolecules(new Set(data.approved_molecules.map((id: any) => String(id).trim()).filter(Boolean)));
                    }
                }
            } catch {
                // Optional metadata only; do not block solver actions.
            }
        };
        fetchCaseTypes();
        return () => {
            cancelled = true;
        };
    }, []);

    const hydrateResultFromDispatch = React.useCallback((summary: DispatchSummary) => {
        const physics = summary.physicsResult;
        if (!physics) return;
        const totalEnergyHa = typeof physics.ground_state_energy_hartree === 'number' ? physics.ground_state_energy_hartree : null;
        const benchmarkDelta = physics.benchmark_delta || {};
        const absorption = physics.absorption_spectrum || {};
        const relativeError = typeof benchmarkDelta.relative_error === 'number' ? benchmarkDelta.relative_error : null;
        const threshold = typeof benchmarkDelta.threshold === 'number' ? benchmarkDelta.threshold : null;
        const passed = typeof benchmarkDelta.within_tolerance === 'boolean'
            ? benchmarkDelta.within_tolerance
            : (relativeError != null && threshold != null ? relativeError <= threshold : false);

        const lumoRaw = typeof physics.lumo_energy === 'number' ? physics.lumo_energy : null;
        const dispatchResult = {
            config: {
                source: 'dispatch_latest',
                reportPath: summary.reportPath,
            },
            problemType: 'molecular',
            equationType: 'Schrodinger',
            hamiltonian: [],
            eigenvalues: [],
            wavefunctions: [],
            probabilityDensity: [],
            verified: Boolean(physics.has_required_fields),
            computationTime: 0,
            molecular: {
                calcMode: (physics.calc_mode || 'gs') as 'gs' | 'td',
                moleculeName: physics.molecule_name || 'H2',
                total_energy_hartree: totalEnergyHa ?? undefined,
                homo_energy: typeof physics.homo_energy === 'number' ? physics.homo_energy : undefined,
                lumo_energy: (lumoRaw !== null && lumoRaw !== 0) ? lumoRaw : undefined,
                converged: passed || Boolean((physics as any).converged),
                optical_spectrum: {
                    energy_ev: Array.isArray(absorption.energy_ev) ? absorption.energy_ev : [],
                    cross_section: Array.isArray(absorption.cross_section) ? absorption.cross_section : [],
                    warning: physics.has_required_fields ? undefined : `Missing: ${(physics.missing_fields || []).join(', ')}`,
                },
            },
            harness: {
                caseId: harnessCaseId,
                configHash: summary.taskId || 'dispatch_latest',
                relativeError,
                threshold,
                passed,
            },
        };

        setResult(dispatchResult);
        const historyKey = `${summary.taskId || 'dispatch'}:${physics.calc_mode || 'gs'}`;
        setResultHistory(prev => ({ ...prev, [historyKey]: dispatchResult }));
    }, [harnessCaseId]);

    const fetchLatestDispatch = React.useCallback(async () => {
        try {
            if (localRunInProgressRef.current) {
                return;
            }
            const resp = await fetch(`${API_BASE}/api/automation/dispatch/latest`);
            if (!resp.ok) {
                return;
            }
            const data: DispatchSummary = await resp.json();
            if (localRunInProgressRef.current) {
                return;
            }
            setDispatchSummary(data);
            const currentResultSource = String((result as any)?.config?.source || '');
            const canHydrateFromDispatch = !result || currentResultSource === 'dispatch_latest';
            if (!localRunInProgressRef.current && !isComputing && data.physicsResult && canHydrateFromDispatch) {
                hydrateResultFromDispatch(data);
            }
        } catch {
            // Keep solver UI independent from dispatch telemetry availability.
        }
    }, [hydrateResultFromDispatch, isComputing, result]);

    useEffect(() => {
        fetchLatestDispatch();
        const timer = setInterval(fetchLatestDispatch, 4000);
        return () => clearInterval(timer);
    }, [fetchLatestDispatch]);

    // MCP health + elapsed timer handled by useMCPHealth/useSolverRunner
    // effectivePicture/gridSpacing computed inside buildOctopusConfig (useSolverRunner)

    const handleRun = () => {
        if (config.engineMode === 'octopus3D' && config.octopusCalcMode === 'gs' && config.gsEnableScan) {
            runDftTddftAgentSuite();
            return;
        }
        markRunStarting();
        run(config);
    };

    const adaptHarnessResult = (data: HarnessApiResponse, fallbackCaseId: string) => {
        const solverResult = data.solver_result || {};
        const elapsedSeconds = Number(data?.solver_summary?.elapsed_seconds ?? solverResult.computationTime ?? 0);
        return {
            ...solverResult,
            verified: Boolean(data?.passed),
            computationTime: Number.isFinite(elapsedSeconds) ? elapsedSeconds : 0,
            harness: {
                caseId: data?.case_id || fallbackCaseId,
                configHash: data?.config_hash || '',
                relativeError: typeof data?.relative_error === 'number' ? data.relative_error : null,
                threshold: typeof data?.threshold === 'number' ? data.threshold : null,
                passed: Boolean(data?.passed),
                escalation: {
                    required: Boolean(data?.escalation?.required),
                    reason: data?.escalation?.reason || null,
                },
                constraints: {
                    maxRetries: data?.harness_constraints?.max_retries,
                    timeoutSeconds: data?.harness_constraints?.timeout_seconds,
                    attemptsUsed: data?.harness_constraints?.attempts_used,
                },
                logRefs: {
                    eventLog: data?.log_refs?.event_log,
                    resultJson: data?.log_refs?.result_json,
                },
                eventChain: Array.isArray(data?.event_chain) ? data.event_chain : [],
                controlLoop: {
                    qualityScore: typeof data?.control_loop?.quality?.score === 'number' ? data.control_loop.quality.score : undefined,
                    iterations: Array.isArray(data?.control_loop?.iterations) ? data.control_loop.iterations.length : undefined,
                },
            },
        };
    };

    const runHarnessCase = async () => {
        const runStartTs = Date.now();
        const selectedCaseId = harnessCaseId || 'infinite_well_v1';
        const controller = new AbortController();
        activeAbortControllerRef.current = controller;
        setWorkflowStage('execute');
        setActiveRunLabel('harness_case');
        setBenchmarkReview(null);
        setIsComputing(true);
        setStatus('RUNNING');
        setResult(null);
        setRunStartAt(runStartTs);
        setElapsedSeconds(0);
        setLastRunSeconds(null);
        setLogs([
            `[System] Starting benchmark harness run: ${selectedCaseId}...`,
        ]);

        try {
            const response = await fetch(`${API_BASE}/api/harness/run-case`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ case_id: selectedCaseId }),
                signal: controller.signal,
            });

            const data: HarnessApiResponse = await response.json();
            if (!response.ok) {
                throw new Error(String(data?.error || data?.detail || 'Harness run failed'));
            }

            const adaptedResult = adaptHarnessResult(data, selectedCaseId);

            setResult(adaptedResult);
            setResultHistory(prev => {
                const historyKey = data?.config_hash
                    ? `harness_${data.config_hash}`
                    : `harness_${Date.now()}`;
                return {
                    ...prev,
                    harness_infinite_well_v1: adaptedResult,
                    [historyKey]: adaptedResult,
                };
            });

            const relErrPct = typeof data?.relative_error === 'number' ? (data.relative_error * 100).toFixed(3) : 'N/A';
            const thrPct = typeof data?.threshold === 'number' ? (data.threshold * 100).toFixed(2) : 'N/A';
            const passed = Boolean(data?.passed);
            const qualityScore = data?.control_loop?.quality?.score;
            let gateVerdict: 'PASS' | 'FAIL' = passed ? 'PASS' : 'FAIL';

            try {
                const reviewResp = await fetch(`${API_BASE}/api/harness/review-case-delta`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ case_id: selectedCaseId, run_result: data }),
                    signal: controller.signal,
                });
                if (reviewResp.ok) {
                    const reviewData: HarnessBenchmarkReview = await reviewResp.json();
                    setBenchmarkReview(reviewData);
                    gateVerdict = (reviewData?.final_verdict === 'PASS') ? 'PASS' : 'FAIL';

                    if (gateVerdict === 'FAIL') {
                        const iterateResp = await fetch(`${API_BASE}/api/harness/review-iterate-case`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                case_id: selectedCaseId,
                                max_iterations: Math.max(1, Math.min(parseInt(harnessIterations || '3', 10) || 3, 6)),
                                threshold: typeof data?.threshold === 'number' ? data.threshold : undefined,
                            }),
                            signal: controller.signal,
                        });
                        if (iterateResp.ok) {
                            const iterateReview: HarnessBenchmarkReview & { iterations_completed?: number } = await iterateResp.json();
                            setBenchmarkReview(iterateReview);
                            gateVerdict = iterateReview?.final_verdict === 'PASS' ? 'PASS' : 'FAIL';
                            setLogs((prev) => [
                                ...prev,
                                `[Reviewer Gate] Iterative review completed: ${iterateReview.iterations_completed ?? 'N/A'} rounds`,
                                `[Reviewer Gate] Final verdict after iteration: ${gateVerdict}`,
                            ]);
                        }
                    }
                }
            } catch {
                // Harness main result remains valid even when review endpoint is unavailable.
            }

            setStatus(gateVerdict === 'PASS' ? 'SUCCESS' : 'ERROR');
            setLogs(prev => [
                ...prev,
                `✓ Harness complete: ${data?.case_id || selectedCaseId}`,
                `  Relative error: ${relErrPct}% (threshold ${thrPct}%)`,
                `  Verdict: ${passed ? 'PASS' : 'FAIL'}${data?.escalation?.required ? ' | escalation required' : ''}`,
                `  Reviewer gate: ${gateVerdict}`,
                `  Attempts: ${data?.harness_constraints?.attempts_used ?? '-'} / ${data?.harness_constraints?.max_retries ?? '-'}`,
                `  Quality score: ${typeof qualityScore === 'number' ? qualityScore.toFixed(4) : 'N/A'}`,
            ]);
        } catch (e: any) {
            if (e?.name === 'AbortError') {
                setStatus('PAUSED');
                setLogs(prev => [...prev, '[System] Harness execution paused']);
                return;
            }
            setStatus('ERROR');
            setLogs(prev => [...prev, `✗ Harness Error: ${e.message || 'Unknown error'}`]);
        } finally {
            if (activeAbortControllerRef.current === controller) {
                activeAbortControllerRef.current = null;
            }
            setIsComputing(false);
            setWorkflowStage('review');
            setLastRunSeconds((Date.now() - runStartTs) / 1000);
        }
    };

    const runSkillsDrivenAutoWorkflow = async () => {
        const runStartTs = Date.now();
        const selectedCaseId = harnessCaseId || 'infinite_well_v1';
        const nIterations = Math.max(1, Math.min(parseInt(harnessIterations || '3', 10) || 3, 6));
        const controller = new AbortController();
        activeAbortControllerRef.current = controller;

        setWorkflowStage('execute');
        setActiveRunLabel('multi_agent_workflow');
        setBenchmarkReview(null);
        setIsComputing(true);
        setStatus('RUNNING');
        setResult(null);
        setRunStartAt(runStartTs);
        setElapsedSeconds(0);
        setLastRunSeconds(null);
        setLogs([
            `[System] Multi-agent workflow started for case ${selectedCaseId}`,
            `[Planner Skill] Stage-1 simple model validation via Harness`,
        ]);

        try {
            const iterateResp = await fetch(`${API_BASE}/api/harness/iterate-case`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    case_id: selectedCaseId,
                    max_iterations: nIterations,
                }),
                signal: controller.signal,
            });
            const iterateData: HarnessIterateApiResponse = await iterateResp.json();
            if (!iterateResp.ok) {
                throw new Error(String(iterateData?.error || iterateData?.detail || 'Harness iterate failed'));
            }

            const history = Array.isArray(iterateData.history) ? iterateData.history : [];
            const finalHarness = history.length > 0 ? history[history.length - 1] : null;
            const simpleModelPassed = Boolean(finalHarness?.passed);

            setLogs(prev => [
                ...prev,
                `[Reviewer Skill] Harness iterations complete: ${iterateData.iterations_completed ?? history.length}/${iterateData.iterations_requested ?? nIterations}`,
                `[Reviewer Skill] Simple model verdict: ${simpleModelPassed ? 'PASS' : 'FAIL'}`,
            ]);

            if (!simpleModelPassed || !finalHarness) {
                throw new Error('Simple model validation did not pass; Octopus first-principles test blocked.');
            }

            const octopusConfig = {
                engineMode: 'octopus3D',
                calcMode: 'gs',
                octopusCalcMode: 'gs',
                caseType: config.caseType,
                octopusDimensions: '3D',
                octopusPeriodic: 'off',
                octopusSpacing: 0.3,
                octopusRadius: 5.0,
                octopusLengthUnit: 'angstrom',
                octopusUnitsOutput: 'eV_Angstrom',
                octopusBoxShape: 'sphere',
                octopusMolecule: 'H2',
                molecule: 'H2',
                dimensionality: '3D',
                equationType: 'Schrodinger',
                potentialType: 'Harmonic',
                problemType: 'boundstate',
                fastPath: false,
                octopusNcpus: 64,
                octopusMpiprocs: 64,
            };

            setLogs(prev => [
                ...prev,
                `[Executor Skill] Stage-2 running Octopus first-principles case: H2 (GS)`,
            ]);

            const octoResp = await fetch(`${API_BASE}/api/physics/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(octopusConfig),
                signal: controller.signal,
            });
            const octoData = await octoResp.json();
            if (!octoResp.ok) {
                throw new Error(String(octoData?.error || 'Octopus first-principles run failed'));
            }

            const finalResult = {
                ...octoData,
                computationTime: Number(octoData?.computationTime ?? 0),
                harness: adaptHarnessResult(finalHarness, selectedCaseId).harness,
                workflow: {
                    mode: 'skills_multi_agent',
                    simpleModelCase: selectedCaseId,
                    harnessIterations: iterateData.iterations_completed ?? history.length,
                    octopusCase: 'H2_gs',
                    objective: typeof iterateData.best_relative_error === 'number' ? iterateData.best_relative_error : null,
                },
            };

            setResult(finalResult);
            setResultHistory(prev => {
                const h = finalHarness.config_hash || `${Date.now()}`;
                return {
                    ...prev,
                    [`workflow_${h}`]: finalResult,
                };
            });

            setStatus('SUCCESS');
            setLogs(prev => [
                ...prev,
                `[Reviewer Skill] Octopus first-principles test completed and visualized`,
                `✓ Workflow done: Harness -> Octopus -> UI`,
            ]);
        } catch (e: any) {
            if (e?.name === 'AbortError') {
                setStatus('PAUSED');
                setLogs(prev => [...prev, '[System] Multi-agent workflow paused']);
                return;
            }
            setStatus('ERROR');
            setLogs(prev => [...prev, `✗ Workflow Error: ${e.message || 'Unknown error'}`]);
        } finally {
            if (activeAbortControllerRef.current === controller) {
                activeAbortControllerRef.current = null;
            }
            setIsComputing(false);
            setWorkflowStage('review');
            setLastRunSeconds((Date.now() - runStartTs) / 1000);
        }
    };

    // Kept for backward-compatible API workflows; not exposed in the current setup panel.
    void runHarnessCase;
    void runSkillsDrivenAutoWorkflow;

    const getSuiteTasksFromCalculationMode = (): SuiteTaskId[] => {
        if (config.octopusCalcMode === 'gs') {
            const selectedMol = String(config.octopusMolecule || '').trim();
            if (selectedMol === 'CH4') {
                return ['ch4_gs_reference'];
            }
            return ['h2o_gs_reference'];
        }
        if (config.octopusCalcMode === 'td') {
            if (config.feProbeEnabled) {
                return ['h2o_tddft_eels_spectrum'];
            }
            if (config.tdExcitationType === 'gaussian') {
                return ['h2o_tddft_dipole_response'];
            }
            if (config.tdExcitationType === 'delta') {
                return ['h2o_tddft_absorption'];
            }
            return ['h2o_tddft_dipole_response'];
        }
        // Advanced modes currently do not have dedicated suite cases.
        return ['h2o_gs_reference'];
    };

    const runDftTddftAgentSuite = async () => {
        if (config.octopusCalcMode === 'gs') {
            const selectedMol = (config.octopusMolecule || '').trim();
            const isMethaneTutorial = selectedMol === 'CH4';
            const isNAtomOfficial = selectedMol === 'N_atom';
            const gsReportStyle = isNAtomOfficial ? 'n_atom_error' : 'total_energy_only';
            const runStartTs = Date.now();
            const controller = new AbortController();
            activeAbortControllerRef.current = controller;

            setWorkflowStage('execute');
            setActiveRunLabel('gs_scan');
            setBenchmarkReview(null);
            setIsComputing(true);
            setStatus('RUNNING');
            setRunStartAt(runStartTs);
            setElapsedSeconds(0);
            setLastRunSeconds(null);
            setSuiteReview(null);
            setSuiteReportMd('');
            setOfficialGsReport(null);

            try {
                const spacings = parseScanSpec(config.gsScanSpec);
                if (!spacings.length) {
                    throw new Error('GS scan spec resolved to empty spacing list');
                }
                const refSpacing = parseFloat(config.gsReferenceSpacing);
                if (!Number.isFinite(refSpacing)) {
                    throw new Error('Reference spacing is invalid');
                }

                const requestedNcpus = Math.max(1, parseInt(config.octopusNcpus, 10) || 32);
                const requestedMpiprocs = Math.max(1, parseInt(config.octopusMpiprocs, 10) || 32);

                const points: any[] = [];
                for (const spacing of spacings) {
                    let moleculePayload: any = config.octopusMolecule;
                    let octopusMoleculePayload: any = config.octopusMolecule;
                    if (isNAtomOfficial) {
                        moleculePayload = {
                            name: 'N_atom',
                            atoms: [{ symbol: 'N', x: 0, y: 0, z: 0 }],
                        };
                        octopusMoleculePayload = 'N_atom';
                    } else if (isMethaneTutorial) {
                        moleculePayload = 'CH4';
                        octopusMoleculePayload = 'CH4';
                    } else if (config.geomMode === 'custom' && config.confirmedAtoms && config.confirmedAtoms.length > 0) {
                        moleculePayload = { name: config.confirmedLabel || 'Custom', atoms: config.confirmedAtoms };
                        octopusMoleculePayload = config.confirmedLabel || 'Custom';
                    }

                    const payload: any = {
                        engineMode: 'octopus3D',
                        calcMode: 'gs',
                        octopusCalcMode: 'gs',
                        caseType: 'dft_gs_3d',
                        octopusDimensions: config.octopusDimensions,
                        speciesMode: 'pseudo',
                        pseudopotentialSet: 'standard',
                        octopusLengthUnit: 'angstrom',
                        octopusUnitsOutput: 'eV_Angstrom',
                        octopusSpacing: spacing,
                        octopusRadius: parseFloat(config.octopusRadius),
                        octopusBoxShape: config.octopusBoxShape,
                        octopusExtraStates: Math.max(0, parseInt(config.octopusExtraStates, 10) || 0),
                        xcFunctional: config.xcOverride.trim() || config.xcPreset,
                        spinComponents: isNAtomOfficial ? 'spin_polarized' : config.spinComponents,
                        fastPath: false,
                        octopusNcpus: requestedNcpus,
                        octopusMpiprocs: requestedMpiprocs,
                        molecule: moleculePayload,
                        octopusMolecule: octopusMoleculePayload,
                    };
                    if (config.octopusEigenSolver.trim()) {
                        payload.octopusEigenSolver = config.octopusEigenSolver.trim();
                    }

                    const resp = await fetch(`${API_BASE}/api/physics/run`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        signal: controller.signal,
                        body: JSON.stringify(payload),
                    });
                    const rawText = await resp.text();
                    let runData: any = null;
                    try {
                        runData = rawText ? JSON.parse(rawText) : null;
                    } catch {
                        runData = null;
                    }
                    if (!resp.ok) {
                        throw new Error(`run failed @ spacing=${spacing}: ${String(runData?.error || rawText || 'unknown')}`);
                    }

                    const molecular = runData?.molecular || {};
                    const totalHartree = runData?.total_energy ?? molecular?.total_energy_hartree;
                    const eigenvalues = Array.isArray(runData?.eigenvalues) ? runData.eigenvalues.map((v: any) => Number(v)) : [];
                    const sEigen = eigenvalues.length >= 1 ? eigenvalues[0] : null;
                    const pEigen = eigenvalues.length >= 4
                        ? (eigenvalues[1] + eigenvalues[2] + eigenvalues[3]) / 3
                        : (eigenvalues.length >= 2 ? eigenvalues[1] : null);
                    const scheduler = runData?.scheduler || {};
                    points.push({
                        spacing_angstrom: spacing,
                        total_energy_hartree: Number.isFinite(Number(totalHartree)) ? Number(totalHartree) : null,
                        s_eigen_hartree: Number.isFinite(Number(sEigen)) ? Number(sEigen) : null,
                        p_eigen_hartree: Number.isFinite(Number(pEigen)) ? Number(pEigen) : null,
                        converged: Boolean(runData?.converged ?? molecular?.converged),
                        scf_iterations: Number(runData?.scf_iterations ?? molecular?.scf_iterations ?? 0),
                        job_id: scheduler?.job_id || '-',
                    });
                }

                const refPoint = points.find((p) => Math.abs(Number(p.spacing_angstrom) - refSpacing) < 1e-9);
                if (!refPoint) {
                    throw new Error(`Reference spacing ${refSpacing} not found in scan list`);
                }
                for (const p of points) {
                    p.error_total_energy_ev = (p.total_energy_hartree - refPoint.total_energy_hartree) * HARTREE_TO_EV;
                    if (gsReportStyle === 'n_atom_error') {
                        p.error_s_eigen_ev = (p.s_eigen_hartree - refPoint.s_eigen_hartree) * HARTREE_TO_EV;
                        p.error_p_eigen_ev = (p.p_eigen_hartree - refPoint.p_eigen_hartree) * HARTREE_TO_EV;
                    }
                }

                let convergenceBand: any = null;
                if (gsReportStyle === 'total_energy_only') {
                    let firstSpacingWithinBand: number | null = null;
                    let tailBand = Number.NaN;
                    for (let i = 0; i < points.length; i += 1) {
                        const tail = points.slice(i).map((p) => Number(p.total_energy_hartree)).filter((v) => Number.isFinite(v));
                        if (!tail.length) continue;
                        const band = (Math.max(...tail) - Math.min(...tail)) * HARTREE_TO_EV;
                        if (band <= 0.1) {
                            firstSpacingWithinBand = Number(points[i].spacing_angstrom);
                            tailBand = band;
                            break;
                        }
                    }
                    if (!Number.isFinite(tailBand)) {
                        const all = points.map((p) => Number(p.total_energy_hartree)).filter((v) => Number.isFinite(v));
                        tailBand = all.length ? (Math.max(...all) - Math.min(...all)) * HARTREE_TO_EV : Number.NaN;
                    }
                    convergenceBand = {
                        tolerance_ev: 0.1,
                        first_spacing_within_band_angstrom: firstSpacingWithinBand,
                        tail_band_ev: tailBand,
                        status: firstSpacingWithinBand == null ? 'not_reached' : 'ok',
                    };
                }

                const report = {
                    generated_at: new Date().toISOString(),
                    molecule: isNAtomOfficial ? 'N_atom' : (isMethaneTutorial ? 'CH4' : config.octopusMolecule),
                    report_style: gsReportStyle,
                    reference_url: config.gsReferenceUrl,
                    reference_spacing_angstrom: refSpacing,
                    spacings,
                    convergence_band: convergenceBand,
                    points,
                };

                const reportStyle = String(report?.report_style || gsReportStyle);
                const allConverged = points.length > 0
                    && points.every((p: any) => Boolean(p?.converged))
                    && (reportStyle !== 'total_energy_only' || String(report?.convergence_band?.status || '') === 'ok');
                setOfficialGsReport(report);
                setStatus(allConverged ? 'SUCCESS' : 'ERROR');

                const mdLines: string[] = [
                    `# Official GS Convergence (${String(report?.molecule || 'N_atom')})`,
                    '',
                    `- final_verdict: ${allConverged ? 'PASS' : 'FAIL'}`,
                    `- points: ${points.length}`,
                    `- reference_spacing: ${report?.reference_spacing_angstrom ?? 0.14} Angstrom`,
                    '',
                ];
                if (reportStyle === 'n_atom_error') {
                    mdLines.push('| Spacing (A) | Total err (eV) | s err (eV) | p err (eV) | Converged | Job ID |');
                    mdLines.push('|---:|---:|---:|---:|:---:|---|');
                    mdLines.push(...points.map((p: any) => `| ${Number(p?.spacing_angstrom ?? 0).toFixed(2)} | ${p?.error_total_energy_ev == null ? 'N/A' : Number(p.error_total_energy_ev).toFixed(6)} | ${p?.error_s_eigen_ev == null ? 'N/A' : Number(p.error_s_eigen_ev).toFixed(6)} | ${p?.error_p_eigen_ev == null ? 'N/A' : Number(p.error_p_eigen_ev).toFixed(6)} | ${p?.converged ? 'Y' : 'N'} | ${String(p?.job_id || '-')} |`));
                } else {
                    mdLines.push('| Spacing (A) | Total Energy (Ha) | Total Energy (eV) | Total err (eV) | Converged | Job ID |');
                    mdLines.push('|---:|---:|---:|---:|:---:|---|');
                    mdLines.push(...points.map((p: any) => {
                        const ha = p?.total_energy_hartree == null ? null : Number(p.total_energy_hartree);
                        const ev = ha == null ? null : (ha * 27.211386245988);
                        return `| ${Number(p?.spacing_angstrom ?? 0).toFixed(2)} | ${ha == null ? 'N/A' : ha.toFixed(8)} | ${ev == null ? 'N/A' : ev.toFixed(6)} | ${p?.error_total_energy_ev == null ? 'N/A' : Number(p.error_total_energy_ev).toFixed(6)} | ${p?.converged ? 'Y' : 'N'} | ${String(p?.job_id || '-')} |`;
                    }));
                }
                setSuiteReportMd(mdLines.join('\n'));
                setLogs((prev) => [
                    ...prev,
                    `[System] GS convergence finished (molecule=${selectedMol || 'unknown'}, style=${reportStyle}).`,
                    `[Reviewer Skill] Verdict: ${allConverged ? 'PASS' : 'FAIL'} | points=${points.length}`,
                    `[Scan] spec=${config.gsScanSpec}`,
                    `[Reference] spacing=${config.gsReferenceSpacing} A | url=${config.gsReferenceUrl}`,
                ]);
            } catch (e: any) {
                if (e?.name === 'AbortError') {
                    setStatus('PAUSED');
                    setLogs((prev) => [...prev, '[System] GS convergence scan paused']);
                    return;
                }
                setStatus('ERROR');
                setLogs((prev) => [...prev, `✗ GS Convergence Scan Error: ${e.message || 'Unknown error'}`]);
            } finally {
                if (activeAbortControllerRef.current === controller) {
                    activeAbortControllerRef.current = null;
                }
                setIsComputing(false);
                setWorkflowStage('review');
                setLastRunSeconds((Date.now() - runStartTs) / 1000);
            }
            return;
        }

        const runStartTs = Date.now();
        const tdSteps = Math.max(120, Math.min(parseInt(config.octopusTdSteps || '260', 10) || 260, 100000));
        const tdDt = Math.max(0.01, Math.min(parseFloat(config.octopusTdTimeStep || '0.04') || 0.04, 0.2));
        const selectedMolecule = (config.octopusMolecule || '').trim();
        const molecule = selectedMolecule || 'H2O';
        const taskCatalog: Array<{ id: SuiteTaskId; title: string }> = [
            { id: 'ch4_gs_reference', title: 'Methane GS reference' },
            { id: 'h2o_gs_reference', title: 'GS reference' },
            { id: 'h2o_tddft_absorption', title: 'Absorption cross section' },
            { id: 'h2o_tddft_dipole_response', title: 'TD dipole response' },
            { id: 'h2o_tddft_radiation_spectrum', title: 'Radiation spectrum' },
            { id: 'h2o_tddft_eels_spectrum', title: 'EELS spectrum' },
        ];
        const selectedTaskIds = getSuiteTasksFromCalculationMode();
        const selectedTaskSet = new Set(selectedTaskIds.filter((id) => taskCatalog.some((t) => t.id === id)));
        const controller = new AbortController();
        activeAbortControllerRef.current = controller;

        setWorkflowStage('execute');
        setActiveRunLabel('dft_tddft_suite');
        setBenchmarkReview(null);
        setIsComputing(true);
        setStatus('RUNNING');
        setRunStartAt(runStartTs);
        setElapsedSeconds(0);
        setLastRunSeconds(null);
        setSuiteReview(null);
        setSuiteReportMd('');
        setLogs([
            `[System] Production DFT/TDDFT agent suite started`,
            `[Planner Skill] Target molecule=${molecule}, calc_mode=${config.octopusCalcMode}, td_steps=${tdSteps}, dt=${tdDt}`,
            `[Planner Skill] Selected tasks: ${taskCatalog.filter((t) => selectedTaskSet.has(t.id)).map((t) => t.title).join(' + ')}`,
            `[Planner Skill] Execution profile: fastPath=false (64-core HPC policy)`,
        ]);

        try {
            const maxLoops = 6;
            const spacingBase = Math.max(0.12, Math.min(parseFloat(config.octopusSpacing || '0.3') || 0.3, 1.0));
            const radiusBase = Math.max(2.0, Math.min(parseFloat(config.octopusRadius || '5.0') || 5.0, 20.0));
            const statesBase = Math.max(1, Math.min(parseInt(config.octopusExtraStates || '4', 10) || 4, 64));
            const tuningProfiles = [
                { spacing: spacingBase, radius: radiusBase, extraStates: statesBase },
                { spacing: Math.max(0.22, spacingBase - 0.05), radius: Math.min(8.0, radiusBase + 0.5), extraStates: Math.min(12, statesBase + 2) },
                { spacing: Math.max(0.20, spacingBase - 0.08), radius: Math.min(8.5, radiusBase + 1.0), extraStates: Math.min(14, statesBase + 4) },
                { spacing: Math.max(0.18, spacingBase - 0.10), radius: Math.min(9.0, radiusBase + 1.5), extraStates: Math.min(16, statesBase + 6) },
            ];

            let tolerancePassed = false;
            let latestReview: AgentSuiteReview | null = null;
            let latestReportMd = '';

            for (let loop = 1; loop <= maxLoops; loop += 1) {
                const profile = tuningProfiles[Math.min(loop - 1, tuningProfiles.length - 1)];
                const applyOverrides = loop > 1;
                setLogs((prev) => [
                    ...prev,
                    `[Auto Loop] round=${loop}/${maxLoops} | fastPath=false | overrides=${applyOverrides ? `spacing=${profile.spacing}, radius=${profile.radius}, extra_states=${profile.extraStates}` : 'backend-default'}`,
                ]);

                const suiteBody: Record<string, any> = {
                    molecule,
                    tdSteps,
                    tdTimeStep: tdDt,
                    strict: false,
                    fastPath: false,
                    taskIds: Array.from(selectedTaskSet),
                    octopusPeriodic: config.periodicDimensions === '0' ? 'off' : 'on',
                    octopusDimensions: config.octopusDimensions,
                    octopusBoxShape: config.octopusBoxShape,
                    xcFunctional: (config.xcOverride.trim() || config.xcPreset || 'gga_x_pbe+gga_c_pbe').trim(),
                    speciesMode: config.speciesMode || 'pseudo',
                    pseudopotentialSet: config.pseudopotentialSet || 'standard',
                    octopusNcpus: Math.max(1, parseInt(config.octopusNcpus, 10) || 64),
                    octopusMpiprocs: Math.max(1, parseInt(config.octopusMpiprocs, 10) || 64),
                };

                // Keep round-1 close to proven backend defaults; only tune discretization on retries.
                if (applyOverrides) {
                    suiteBody.octopusSpacing = profile.spacing;
                    suiteBody.octopusRadius = profile.radius;
                    suiteBody.octopusExtraStates = profile.extraStates;
                }

                const suiteResp = await fetch(`${API_BASE}/api/agents/run-dft-tddft-suite`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    signal: controller.signal,
                    body: JSON.stringify(suiteBody),
                });

                const suiteData = await suiteResp.json();
                if (!suiteResp.ok) {
                    throw new Error(String(suiteData?.error || 'suite execution failed'));
                }

                const review: AgentSuiteReview = suiteData?.report?.ui_review || {
                    title: `DFT/TDDFT Agent Review (${molecule})`,
                    final_verdict: String(suiteData?.suite_verdict || 'UNKNOWN'),
                    checks: suiteData?.report?.reviewer?.checks || {},
                    case_cards: [],
                };
                latestReview = review;
                latestReportMd = String(suiteData?.report_md || '');
                setSuiteReview(review);
                setSuiteReportMd(latestReportMd);

                const caseRows = review.case_cards || [];
                const tableHeader = '[Reviewer Table] | scenario | metric | computed | expected | delta | rel_delta | within_tol |';
                setLogs((prev) => [
                    ...prev,
                    ...caseRows.map((c) => {
                        const cp = c.optical_points ?? 0;
                        const dp = c.dipole_points ?? 0;
                        const rp = c.radiation_points ?? 0;
                        const ep = c.eels_points ?? 0;
                        const scheduler = c.scheduler || {};
                        const node = scheduler.selected_node || '-';
                        const cpu = scheduler.ncpus ?? '-';
                        const mpi = scheduler.mpiprocs ?? '-';
                        const queue = scheduler.queue || '-';
                        const job = scheduler.job_id || '-';
                        const state = scheduler.job_state || '-';
                        const rel = c.comparison?.relative_delta;
                        const tol = c.comparison?.tolerance_relative;
                        const compareNote = rel == null ? '' : ` | rel_delta=${rel} | tol=${tol ?? '-'} | within_tol=${String(c.comparison?.within_tolerance ?? '-')}`;
                        return `[Reviewer Skill] ${c.scenario_id}: ${c.status} | cross_section_points=${cp} | dipole_points=${dp} | radiation_points=${rp} | eels_points=${ep} | node=${node} | ncpus=${cpu} | mpiprocs=${mpi} | queue=${queue} | job_state=${state} | job_id=${job}${compareNote}`;
                    }),
                    tableHeader,
                    ...caseRows.map((c) => {
                        const metric = c.comparison?.metric || '-';
                        const computed = c.comparison?.computed ?? '-';
                        const expected = c.comparison?.reference ?? '-';
                        const delta = c.comparison?.delta ?? '-';
                        const rel = c.comparison?.relative_delta ?? '-';
                        const within = c.comparison?.within_tolerance == null ? '-' : String(c.comparison?.within_tolerance);
                        return `[Reviewer Table] | ${c.scenario_id || '-'} | ${metric} | ${computed} | ${expected} | ${delta} | ${rel} | ${within} |`;
                    }),
                    `[Reviewer Skill] Final verdict: ${review.final_verdict || 'UNKNOWN'}`,
                ].filter(Boolean));

                tolerancePassed = Boolean((review.checks || {}).all_within_reference_tolerance)
                    && String(review.final_verdict || '').toUpperCase() === 'PASS';
                if (tolerancePassed) {
                    setLogs((prev) => [...prev, `[Auto Loop] tolerance gate passed at round ${loop}.`]);
                    break;
                }

                if (loop < maxLoops) {
                    setLogs((prev) => [...prev, `[Auto Loop] tolerance gate not passed; continue to round ${loop + 1}.`]);
                }
            }

            setSuiteReview(latestReview);
            setSuiteReportMd(latestReportMd);
            setStatus(tolerancePassed ? 'SUCCESS' : 'ERROR');
        } catch (e: any) {
            if (e?.name === 'AbortError') {
                setStatus('PAUSED');
                setLogs((prev) => [...prev, '[System] DFT/TDDFT suite paused']);
                return;
            }
            setStatus('ERROR');
            setLogs((prev) => [...prev, `✗ DFT/TDDFT Suite Error: ${e.message || 'Unknown error'}`]);
        } finally {
            if (activeAbortControllerRef.current === controller) {
                activeAbortControllerRef.current = null;
            }
            setIsComputing(false);
            setWorkflowStage('review');
            setLastRunSeconds((Date.now() - runStartTs) / 1000);
        }
    };

    const displayResultSeconds = lastRunSeconds ?? result?.computationTime;


    return (
        <div className="h-full">
            {/* ── Left: Parameter Panels ── */}
            <div className="h-full w-full overflow-auto p-4" style={{ borderRight: '1px solid #1a2035' }}>
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        <Settings2 className="w-5 h-5" style={{ color: '#00d4ff' }} />
                        <h2 className="text-lg font-medium" style={{ color: '#e2e8f0' }}>Physics Configuration</h2>
                    </div>
                </div>

                <div className="rounded-xl p-3 mb-3" style={{ background: '#0d1525', border: '1px solid #1a2035' }}>
                    <div className="text-[11px] mb-2" style={{ color: '#94a3b8' }}>Workflow Stage</div>
                    <div className="grid grid-cols-3 gap-2 text-[11px]">
                        {[
                            { id: 'setup', label: '1. Setup' },
                            { id: 'execute', label: '2. Execute' },
                            { id: 'review', label: '3. Review' },
                        ].map((step) => {
                            const isActive = workflowStage === step.id;
                            return (
                                <div
                                    key={step.id}
                                    className="rounded-md px-2 py-1.5 text-center"
                                    style={{
                                        background: isActive ? 'rgba(0,212,255,0.12)' : 'rgba(255,255,255,0.03)',
                                        border: isActive ? '1px solid rgba(0,212,255,0.35)' : '1px solid #1f2937',
                                        color: isActive ? '#00d4ff' : '#64748b',
                                        fontWeight: isActive ? 600 : 500,
                                    }}
                                >
                                    {step.label}
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Engine Mode Toggle */}
                <div className="flex rounded-lg p-1 mb-4" style={{ background: '#0d1525', border: '1px solid #1a2035' }}>
                    <button onClick={() => setters.setEngineMode('octopus3D')}
                        className="flex-1 py-1.5 text-xs font-medium rounded-md transition-colors"
                        style={config.engineMode === 'octopus3D'
                            ? { background: 'rgba(0,212,255,0.12)', color: '#00d4ff', outline: '1px solid rgba(0,212,255,0.35)' }
                            : { color: '#8892a4' }}>
                        Octopus3D
                    </button>
                    <button onClick={() => setters.setEngineMode('vasp')}
                        className="flex-1 py-1.5 text-xs font-medium rounded-md transition-colors"
                        style={config.engineMode === 'vasp'
                            ? { background: 'rgba(168,85,247,0.12)', color: '#a855f7', outline: '1px solid rgba(168,85,247,0.35)' }
                            : { color: '#8892a4' }}>
                        VASP
                    </button>
                </div>

                {/* Quick Presets — validated cases (Octopus only) */}
                {config.engineMode === 'octopus3D' && (
                    <div className="flex flex-wrap gap-1.5 mb-4">
                        {([
                            // ── Atoms ──
                            { label: 'H (PP PBE)', mol: 'H', space: '0.18', rad: '10.0', spin: 'unpolarized', xc: 'gga_x_pbe+gga_c_pbe', species: 'pseudo', ppSet: 'standard', cmode: 'gs' as const },
                            { label: 'He (PP LDA)', mol: 'He', space: '0.15', rad: '10.0', spin: 'unpolarized', xc: 'lda_x+lda_c_pz', species: 'pseudo', ppSet: 'standard', cmode: 'gs' as const },
                            { label: 'N (PP LDA)', mol: 'N_atom', space: '0.18', rad: '10.0', spin: 'polarized', xc: 'lda_x+lda_c_pz', species: 'pseudo', ppSet: 'standard', cmode: 'gs' as const },
                            { label: 'Na (builtin)', mol: 'Na', space: '0.22', rad: '10.0', spin: 'unpolarized', xc: 'lda_x+lda_c_pz', species: 'builtin_standard', ppSet: 'standard', cmode: 'gs' as const },
                            // ── Diatomics ──
                            { label: 'H₂ (PP PBE)', mol: 'H2', space: '0.10', rad: '8.0', spin: 'unpolarized', xc: 'gga_x_pbe+gga_c_pbe', species: 'pseudo', ppSet: 'standard', cmode: 'gs' as const },
                            { label: 'LiH (builtin)', mol: 'LiH', space: '0.22', rad: '7.0', spin: 'unpolarized', xc: 'lda_x+lda_c_pz', species: 'builtin_standard', ppSet: 'standard', cmode: 'gs' as const },
                            // ── Polyatomics ──
                            { label: 'CH₄ (builtin)', mol: 'CH4', space: '0.18', rad: '7.0', spin: 'unpolarized', xc: 'lda_x+lda_c_pz', species: 'builtin_standard', ppSet: 'standard', cmode: 'gs' as const },
                            { label: 'NH₃ (PP PBE)', mol: 'NH3', space: '0.21', rad: '3.0', spin: 'unpolarized', xc: 'gga_x_pbe+gga_c_pbe', species: 'pseudo', ppSet: 'standard', cmode: 'gs' as const },
                            { label: 'H₂O GS', mol: 'H2O', space: '0.21', rad: '3.0', spin: 'unpolarized', xc: 'gga_x_pbe+gga_c_pbe', species: 'pseudo', ppSet: 'standard', cmode: 'gs' as const },
                            { label: 'H₂O TDDFT', mol: 'H2O', space: '0.21', rad: '5.0', spin: 'unpolarized', xc: 'lda_x+lda_c_pz', species: 'builtin_standard', ppSet: 'standard', cmode: 'td' as const },
                            { label: 'H₂O Casida', mol: 'H2O', space: '0.21', rad: '5.0', spin: 'unpolarized', xc: 'lda_x+lda_c_pz', species: 'builtin_standard', ppSet: 'standard', cmode: 'casida' as const },
                            // ── H₂O Advanced TDDFT ──
                            { label: 'H₂O HHG', mol: 'H2O', space: '0.21', rad: '6.0', spin: 'unpolarized', xc: 'lda_x+lda_c_pz', species: 'builtin_standard', ppSet: 'standard', cmode: 'td' as const },
                            { label: 'H₂O CW', mol: 'H2O', space: '0.21', rad: '5.0', spin: 'unpolarized', xc: 'lda_x+lda_c_pz', species: 'builtin_standard', ppSet: 'standard', cmode: 'td' as const },
                            { label: 'H₂O Pump', mol: 'H2O', space: '0.21', rad: '5.0', spin: 'unpolarized', xc: 'lda_x+lda_c_pz', species: 'builtin_standard', ppSet: 'standard', cmode: 'td' as const },
                            // ── Other molecules ──
                            { label: 'C₂H₄ (builtin)', mol: 'C2H4', space: '0.22', rad: '5.0', spin: 'unpolarized', xc: 'lda_x+lda_c_pz', species: 'builtin_standard', ppSet: 'standard', cmode: 'gs' as const },
                        ] as const).map(p => (
                            <button
                                key={p.label}
                                onClick={() => {
                                    setResult(null);
                                    setLogs([`[System] Preset "${p.label}" selected. Click "Initiate Computation" to run.`]);
                                    setters.setOctopusMolecule(p.mol);
                                    setters.setOctopusSpacing(p.space);
                                    setters.setOctopusRadius(p.rad);
                                    setters.setSpinComponents(p.spin);
                                    setters.setXcPreset(p.xc);
                                    setters.setXcCategory(p.xc.startsWith('gga') ? 'gga' : p.xc.startsWith('mgga') ? 'mgga' : p.xc.startsWith('hyb') ? 'hybrid' : 'lda');
                                    setters.setXcOverride('');
                                    setters.setSpeciesMode(p.species);
                                    setters.setPseudopotentialSet(p.ppSet);
                                    setters.setOctopusCalcMode(p.cmode);
                                    setters.setGeomMode('preset');
                                    setters.setConfirmedAtoms(null);
                                    setters.setConfirmedLabel('');
                                    if (p.cmode === 'td') {
                                        if (p.label === 'H₂O HHG') {
                                            // Strong-field sin pulse for HHG / nonlinear response
                                            setters.setOctopusSpacing('0.35');
                                            setters.setOctopusRadius('5.0');
                                            setters.setOctopusTdSteps('50000');
                                            setters.setOctopusTdTimeStep('0.3');
                                            setters.setTdExcitationType('sin');
                                            setters.setTdFieldAmplitude('0.005');
                                            setters.setTdSinFrequency('0.057');   // 800nm Ti:Sapphire laser (~1.55 eV)
                                        } else if (p.label === 'H₂O CW') {
                                            // Continuous wave: Floquet-like periodic driving
                                            setters.setOctopusSpacing('0.35');
                                            setters.setOctopusRadius('5.0');
                                            setters.setOctopusTdSteps('50000');
                                            setters.setOctopusTdTimeStep('0.3');
                                            setters.setTdExcitationType('continuous_wave');
                                            setters.setTdFieldAmplitude('0.005');
                                            setters.setTdSinFrequency('0.057');  // 800nm
                                        } else if (p.label === 'H₂O Pump') {
                                            // Gaussian pump pulse: ultrafast excitation
                                            setters.setOctopusSpacing('0.35');
                                            setters.setOctopusRadius('5.0');
                                            setters.setOctopusTdSteps('50000');
                                            setters.setOctopusTdTimeStep('0.3');
                                            setters.setTdExcitationType('gaussian');
                                            setters.setTdFieldAmplitude('0.01');
                                            setters.setTdGaussianT0('500');
                                            setters.setTdGaussianSigma('100');
                                        } else {
                                            // Default TDDFT: delta-kick for linear absorption
                                            setters.setOctopusTdSteps('25000');
                                            setters.setOctopusTdTimeStep('0.02');
                                            setters.setTdExcitationType('delta');
                                            setters.setTdFieldAmplitude('0.01');
                                        }
                                    }
                                    if (p.cmode === 'casida') {
                                        setters.setOctopusExtraStates('13');
                                        setters.setCasidaKohnShamStates('1-16');
                                    }
                                }}
                                disabled={isComputing}
                                className="px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors disabled:opacity-40"
                                style={{
                                    background: p.cmode === 'casida' ? 'rgba(167,139,250,0.10)' :
                                                (p.cmode === 'td' && (p.label as string).includes('HHG')) ? 'rgba(251,146,60,0.12)' :
                                                (p.cmode === 'td' && (p.label as string).includes('CW')) ? 'rgba(96,165,250,0.12)' :
                                                (p.cmode === 'td' && (p.label as string).includes('Pump')) ? 'rgba(244,114,182,0.12)' :
                                                p.cmode === 'td' ? 'rgba(52,211,153,0.10)' :
                                                'rgba(0,212,255,0.08)',
                                    color: p.cmode === 'casida' ? '#c4b5fd' :
                                           (p.cmode === 'td' && (p.label as string).includes('HHG')) ? '#fb923c' :
                                           (p.cmode === 'td' && (p.label as string).includes('CW')) ? '#60a5fa' :
                                           (p.cmode === 'td' && (p.label as string).includes('Pump')) ? '#f472b6' :
                                           p.cmode === 'td' ? '#6ee7b7' :
                                           '#7dd3fc',
                                    border: `1px solid ${p.cmode === 'casida' ? 'rgba(167,139,250,0.25)' :
                                                      (p.cmode === 'td' && (p.label as string).includes('HHG')) ? 'rgba(251,146,60,0.3)' :
                                                      (p.cmode === 'td' && (p.label as string).includes('CW')) ? 'rgba(96,165,250,0.3)' :
                                                      (p.cmode === 'td' && (p.label as string).includes('Pump')) ? 'rgba(244,114,182,0.3)' :
                                                      p.cmode === 'td' ? 'rgba(52,211,153,0.25)' :
                                                      'rgba(0,212,255,0.2)'}`,
                                }}
                            >
                                {p.label}
                            </button>
                        ))}
                    </div>
                )}

                {config.engineMode === 'vasp' ? (
                    <>
                        {/* ── VASP System Configuration ── */}
                        <Section title="VASP System Configuration" icon={<Grid3x3 className="w-4 h-4 text-purple-400" />}>
                            <Field label="Molecule / Atom">
                                <select value={config.octopusMolecule} onChange={e => {
                                    setters.setOctopusMolecule(e.target.value);
                                    setters.setGeomMode('preset');
                                    setters.setConfirmedAtoms(null);
                                    setters.setConfirmedLabel('');
                                }} className={selectClass}>
                                    <optgroup label="Atoms">
                                        <option value="H">H — Hydrogen</option>
                                        <option value="O">O — Oxygen</option>
                                    </optgroup>
                                    <optgroup label="Molecules">
                                        <option value="H2O">H₂O — Water</option>
                                        <option value="CH4">CH₄ — Methane</option>
                                    </optgroup>
                                </select>
                            </Field>
                            <Field label="Box Size (Å)" hint="Simulation cell edge length">
                                <input type="number" value={config.vaspBox} onChange={e => setters.setVaspBox(e.target.value)} step="1.0" min="4.0" className={inputClass} />
                            </Field>
                        </Section>

                        {/* ── VASP SCF Control ── */}
                        <Section title="VASP SCF Control" icon={<Settings2 className="w-4 h-4 text-purple-400" />}>
                            <Field label="ENCUT (eV)" hint="Plane-wave cutoff energy. Default 400 eV.">
                                <input type="number" value={config.vaspEncuit} onChange={e => setters.setVaspEncuit(e.target.value)} step="50" min="100" className={inputClass} />
                            </Field>
                            <Field label="EDIFF" hint="SCF convergence criterion. Default 1e-6.">
                                <input type="text" value={config.vaspEdiff} onChange={e => setters.setVaspEdiff(e.target.value)} className={inputClass} />
                            </Field>
                            <Field label="NELMIN" hint="Minimum SCF iterations. Default 5.">
                                <input type="number" value={config.vaspNelmin} onChange={e => setters.setVaspNelmin(e.target.value)} step="1" min="1" className={inputClass} />
                            </Field>
                            <Field label="ISMEAR" hint="Smearing method: 0=Gaussian, 1=Methfessel-Paxton, -1=Fermi">
                                <select value={config.vaspIsmear} onChange={e => setters.setVaspIsmear(e.target.value)} className={selectClass}>
                                    <option value="0">0 — Gaussian</option>
                                    <option value="1">1 — Methfessel-Paxton</option>
                                    <option value="-1">-1 — Fermi</option>
                                </select>
                            </Field>
                            <Field label="SIGMA (eV)" hint="Smearing width. Default 0.01 eV.">
                                <input type="text" value={config.vaspSigma} onChange={e => setters.setVaspSigma(e.target.value)} className={inputClass} />
                            </Field>
                        </Section>

                        {/* ── VASP Electronic Control ── */}
                        <Section title="VASP Electronic Control" icon={<Zap className="w-4 h-4 text-purple-400" />}>
                            <Field label="NELECT" hint="Total electron count. Leave empty for neutral. Set N-1 for ΔSCF cation.">
                                <input type="text" value={config.vaspNelect} onChange={e => setters.setVaspNelect(e.target.value)} placeholder="auto (neutral)" className={inputClass} />
                            </Field>
                            <Field label="NBANDS" hint="Number of bands. Leave empty for VASP default.">
                                <input type="text" value={config.vaspNbands} onChange={e => setters.setVaspNbands(e.target.value)} placeholder="auto" className={inputClass} />
                            </Field>
                            <Field label="K-Points">
                                <select value={config.vaspKpointsType} onChange={e => setters.setVaspKpointsType(e.target.value)} className={selectClass}>
                                    <option value="gamma">Gamma-only (molecules)</option>
                                    <option value="monkhorst">Monkhorst-Pack (periodic)</option>
                                </select>
                            </Field>
                            <Field label="Precision">
                                <select value={config.vaspPrec} onChange={e => setters.setVaspPrec(e.target.value)} className={selectClass}>
                                    <option value="Normal">Normal</option>
                                    <option value="Accurate">Accurate</option>
                                </select>
                            </Field>
                        </Section>

                        {/* ── Exchange-Correlation ── */}
                        <Section title="Exchange-Correlation" icon={<Atom className="w-4 h-4 text-purple-400" />}>
                            <Field label="XC Functional">
                                <select value={config.xcOverride || config.xcPreset} onChange={e => { setters.setXcOverride(e.target.value); setters.setXcPreset(e.target.value); }} className={selectClass}>
                                    <option value="gga_x_pbe+gga_c_pbe">PBE (GGA)</option>
                                    <option value="lda_x+lda_c_pz">LDA (Ceperley-Alder)</option>
                                    <option value="hartree_fock">Hartree-Fock (Exact Exchange)</option>
                                </select>
                            </Field>
                            <Field label="Spin">
                                <select value={config.spinComponents} onChange={e => setters.setSpinComponents(e.target.value)} className={selectClass}>
                                    <option value="unpolarized">Unpolarized</option>
                                    <option value="polarized">Spin-Polarized</option>
                                </select>
                            </Field>
                        </Section>

                        {/* ── Molecule Preview ── */}
                        {config.octopusMolecule && MOLECULE_ATOMS[config.octopusMolecule] && (
                            <div className="rounded-lg p-3" style={{ background: '#0d1525', border: '1px solid #1a2035' }}>
                                <div className="text-xs font-medium mb-2" style={{ color: '#8892a4' }}>Molecule Preview</div>
                                <Mol3DViewer
                                    boxRadius={parseFloat(config.vaspBox) || 10}
                                    atoms={MOLECULE_ATOMS[config.octopusMolecule]}
                                    title={config.octopusMolecule}
                                />
                            </div>
                        )}
                    </>
                ) : config.engineMode === 'local1D' ? (
                    <>
                        {/* A. Physical Constants */}
                        <Section title="Physical Constants" icon={<Atom className="w-4 h-4 text-purple-400" />}>
                            <Field label="Unit System">
                                <select value={config.unitSystem} onChange={e => setters.setUnitSystem(e.target.value)} className={selectClass}>
                                    <option value="natural">Natural Units (ℏ=c=1)</option>
                                    <option value="SI">SI Units</option>
                                    <option value="gaussian">Gaussian Units</option>
                                </select>
                            </Field>
                            <div className="grid grid-cols-2 gap-2">
                                <Field label={`Particle Mass${config.unitSystem === 'natural' ? '' : ' (MeV/c²)'}`}>
                                    <input type="number" value={config.particleMass} onChange={e => setters.setParticleMass(e.target.value)}
                                        step="0.001" className={inputClass} />
                                </Field>
                                <Field label="Charge (e)">
                                    <input type="number" value={config.particleCharge} onChange={e => setters.setParticleCharge(e.target.value)}
                                        className={inputClass} />
                                </Field>
                            </div>
                            <Field label={`Electron Energy${config.unitSystem === 'natural' ? '' : ' (MeV)'}`} hint="Total energy of the incident particle">
                                <input type="number" value={config.electronEnergy} onChange={e => setters.setElectronEnergy(e.target.value)}
                                    step="0.1" className={inputClass} />
                            </Field>
                            <div className="text-[10px] text-gray-600 bg-[#18181b] rounded-lg p-2 mt-1">
                                α = e²/(4πℏc) ≈ 1/137.036 &nbsp;|&nbsp; λ_C = ℏ/(mc) ≈ {(1 / parseFloat(config.particleMass || '0.511')).toFixed(4)}
                            </div>
                        </Section>

                        {/* B. Geometry & Grid */}
                        <Section title="Geometry & Grid" icon={<Grid3x3 className="w-4 h-4 text-green-400" />}>
                            <Field label="Dimensionality">
                                <select value={config.dimensionality} onChange={e => setters.setDimensionality(e.target.value)} className={selectClass}>
                                    <option value="1D">1D — Linear</option>
                                    <option value="2D">2D — Planar</option>
                                    <option value="3D">3D — Volumetric</option>
                                </select>
                            </Field>
                            <div className="grid grid-cols-2 gap-2">
                                <Field label="Spatial Range L" hint="Domain: [-L/2, L/2]">
                                    <input type="number" value={config.spatialRange} onChange={e => setters.setSpatialRange(e.target.value)}
                                        step="0.5" className={inputClass} />
                                </Field>
                                <Field label="Grid Points N">
                                    <input type="number" value={config.gridPoints} onChange={e => setters.setGridPoints(e.target.value)}
                                        min="10" step="10" className={inputClass} />
                                </Field>
                            </div>
                            <div className="text-[10px] text-gray-500 bg-[#18181b] rounded-lg p-2">
                                δx = L/N = {isFinite(gridSpacing) ? gridSpacing.toFixed(6) : '—'} &nbsp;|&nbsp;
                                Total cells: {parseInt(config.gridPoints) || 0}{config.dimensionality !== '1D' && <span>^{config.dimensionality === '2D' ? '2' : '3'}</span>}
                            </div>
                            <Field label="Boundary Condition">
                                <select value={config.boundaryCondition} onChange={e => setters.setBoundaryCondition(e.target.value)} className={selectClass}>
                                    <option value="dirichlet">Dirichlet (ψ=0 at boundary)</option>
                                    <option value="periodic">Periodic (ψ(0) = ψ(L))</option>
                                    <option value="absorbing">Absorbing (PML)</option>
                                </select>
                            </Field>
                        </Section>

                        {/* C. Potential Field */}
                        <Section title="Potential Field V(r)" icon={<Zap className="w-4 h-4 text-yellow-400" />}>
                            <div className="flex gap-2 mb-2">
                                <button onClick={() => setters.setPotentialDataMode('analytical')}
                                    className={`flex-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${config.potentialDataMode === 'analytical' ? 'bg-yellow-600/20 text-yellow-300 border border-yellow-600' : 'bg-[#1a1a1e] text-gray-500 border border-gray-800'
                                        }`}>Analytical</button>
                                <button onClick={() => setters.setPotentialDataMode('data')}
                                    className={`flex-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${config.potentialDataMode === 'data' ? 'bg-yellow-600/20 text-yellow-300 border border-yellow-600' : 'bg-[#1a1a1e] text-gray-500 border border-gray-800'
                                        }`}>Data Import</button>
                            </div>
                            {config.potentialDataMode === 'analytical' ? (
                                <>
                                    <Field label="Potential Type">
                                        <select value={config.potentialType} onChange={e => setters.setPotentialType(e.target.value)} className={selectClass}>
                                            <option value="FreeSpace">Free Space (V=0)</option>
                                            <option value="InfiniteWell">Infinite Square Well</option>
                                            <option value="FiniteWell">Finite Square Well</option>
                                            <option value="Coulomb">Coulomb (-Ze²/r)</option>
                                            <option value="Harmonic">Harmonic Oscillator (½mω²x²)</option>
                                            <option value="Step">Step Potential</option>
                                            <option value="Custom">Custom Expression</option>
                                        </select>
                                    </Field>
                                    {(config.potentialType === 'FiniteWell' || config.potentialType === 'InfiniteWell') && (
                                        <div className="grid grid-cols-2 gap-2">
                                            <Field label="Well Width">
                                                <input type="number" value={config.wellWidth} onChange={e => setters.setWellWidth(e.target.value)}
                                                    step="0.1" className={inputClass} />
                                            </Field>
                                            <Field label="Depth V₀">
                                                <input type="number" value={config.potentialStrength} onChange={e => setters.setPotentialStrength(e.target.value)}
                                                    step="0.1" className={inputClass} />
                                            </Field>
                                        </div>
                                    )}
                                    {config.potentialType === 'Coulomb' && (
                                        <Field label="Nuclear Charge Z">
                                            <input type="number" value={config.potentialStrength} onChange={e => setters.setPotentialStrength(e.target.value)}
                                                step="1" className={inputClass} />
                                        </Field>
                                    )}
                                    {config.potentialType === 'Custom' && (
                                        <Field label="V(x) Expression" hint="Use x,y,z variables. e.g., -1/sqrt(x^2+1)">
                                            <input type="text" value={config.customExpression} onChange={e => setters.setCustomExpression(e.target.value)}
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
                                <select value={config.equationType} onChange={e => setters.setEquationType(e.target.value)} className={selectClass}>
                                    <option value="Schrodinger">Schrödinger Equation</option>
                                    <option value="Dirac">Dirac Equation</option>
                                    <option value="KleinGordon">Klein-Gordon Equation</option>
                                </select>
                            </Field>
                            <Field label="Problem Type">
                                <select value={config.problemType} onChange={e => setters.setProblemType(e.target.value)} className={selectClass}>
                                    <option value="boundstate">Bound State (Eigenvalue)</option>
                                    <option value="timeevolution">Time Evolution</option>
                                    <option value="scattering">Scattering</option>
                                </select>
                            </Field>
                            <Field label="Quantum Picture" hint={`Auto: ${config.problemType === 'scattering' ? 'Interaction' : 'Schrödinger'} config.picture`}>
                                <select value={config.picture} onChange={e => setters.setPicture(e.target.value)} className={selectClass}>
                                    <option value="auto">Auto (recommended)</option>
                                    <option value="schrodinger">Schrödinger Picture</option>
                                    <option value="interaction">Interaction Picture</option>
                                </select>
                            </Field>
                            <div className="text-[10px] text-cyan-800 bg-cyan-950/30 border border-cyan-900/50 rounded-lg p-2">
                                {config.equationType === 'Dirac' && '(iγᵘ∂ᵘ - m)ψ = 0 — 4-component spinor, relativistic'}
                                {config.equationType === 'Schrodinger' && 'iℏ∂ψ/∂t = Hψ — non-relativistic wave equation'}
                                {config.equationType === 'KleinGordon' && '(∂ᵘ∂ᵘ + m²)φ = 0 — spin-0 relativistic'}
                            </div>
                        </Section>

                        {/* E. Time Evolution Config */}
                        {config.problemType === 'timeevolution' && (
                            <Section title="Time Evolution Config" icon={<FlaskConical className="w-4 h-4 text-pink-400" />}>
                                <div className="grid grid-cols-2 gap-2">
                                    <Field label="Total Time">
                                        <input type="number" value={config.totalTime} onChange={e => setters.setTotalTime(e.target.value)}
                                            step="1" className={inputClass} />
                                    </Field>
                                    <Field label="Time Steps">
                                        <input type="number" value={config.numTimeSteps} onChange={e => setters.setNumTimeSteps(e.target.value)}
                                            step="10" className={inputClass} />
                                    </Field>
                                </div>
                                <div className="text-[10px] text-pink-900/70 mb-1 font-medium">Initial Gaussian Wavepacket ψ₀(x)</div>
                                <div className="grid grid-cols-3 gap-2">
                                    <Field label="Center x₀" hint="Fraction of range">
                                        <input type="number" value={config.gaussianCenter} onChange={e => setters.setGaussianCenter(e.target.value)}
                                            step="0.1" className={inputClass} />
                                    </Field>
                                    <Field label="Width σ" hint="Fraction of range">
                                        <input type="number" value={config.gaussianWidth} onChange={e => setters.setGaussianWidth(e.target.value)}
                                            step="0.05" min="0.01" className={inputClass} />
                                    </Field>
                                    <Field label="Momentum k₀">
                                        <input type="number" value={config.gaussianMomentum} onChange={e => setters.setGaussianMomentum(e.target.value)}
                                            step="1" className={inputClass} />
                                    </Field>
                                </div>
                            </Section>
                        )}

                        {/* F. Scattering Config */}
                        {config.problemType === 'scattering' && (
                            <Section title="Scattering Config" icon={<Zap className="w-4 h-4 text-orange-400" />}>
                                <div className="grid grid-cols-3 gap-2">
                                    <Field label="E min">
                                        <input type="number" value={config.scatteringEMin} onChange={e => setters.setScatteringEMin(e.target.value)}
                                            step="0.5" className={inputClass} />
                                    </Field>
                                    <Field label="E max">
                                        <input type="number" value={config.scatteringEMax} onChange={e => setters.setScatteringEMax(e.target.value)}
                                            step="1" className={inputClass} />
                                    </Field>
                                    <Field label="Steps">
                                        <input type="number" value={config.scatteringESteps} onChange={e => setters.setScatteringESteps(e.target.value)}
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
                                <select value={config.octopusDimensions} onChange={e => setters.setOctopusDimensions(e.target.value)} className={selectClass}>
                                    <option value="1D">1D — Model System</option>
                                    <option value="2D">2D — Planar</option>
                                    <option value="3D">3D — Molecular / Crystal</option>
                                </select>
                            </Field>
                            <Field label="Calculation Mode">
                                <select value={config.octopusCalcMode} onChange={e => setters.setOctopusCalcMode(e.target.value as any)} className={selectClass}>
                                    <optgroup label="Standard">
                                        <option value="gs">Ground State (GS)</option>
                                        <option value="td">Time-Dependent (TD)</option>
                                        <option value="unocc">Unoccupied States</option>
                                    </optgroup>
                                    <optgroup label="Advanced">
                                        <option value="opt">Geometry Optimization</option>
                                        <option value="casida">Casida (LR-TDDFT)</option>
<option value="em">EM / Linear Response</option>
                                        <option value="vib">Vibrational Modes</option>
                                    </optgroup>
                                </select>
                            </Field>

                            {config.octopusDimensions !== '1D' ? (
                                <Field label="Molecule / Crystal">
                                    {/* Preset / Custom mode selector */}
                                    <div style={{ display: 'flex', border: '1px solid #1f2937', borderRadius: 6, overflow: 'hidden', marginBottom: 6 }}>
                                        {(['preset', 'custom'] as const).map(m => (
                                            <button key={m} onClick={() => {
                                                setters.setGeomMode(m);
                                                if (m === 'preset') { setters.setConfirmedAtoms(null); setters.setConfirmedLabel(''); }
                                            }} style={{
                                                flex: 1, padding: '4px 0', fontSize: 10, cursor: 'pointer', border: 'none',
                                                background: config.geomMode === m ? 'rgba(0,212,255,0.12)' : 'transparent',
                                                color: config.geomMode === m ? '#00d4ff' : '#4b5563',
                                            }}>
                                                {m === 'preset' ? '预设分子' : '自定义几何'}
                                            </button>
                                        ))}
                                    </div>

                                    {config.geomMode === 'preset' ? (<>
                                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                                    <select value={config.octopusMolecule} onChange={e => {
                                        setters.setOctopusMolecule(e.target.value);
                                        // Auto-set periodic dims and lattice constants for crystals
                                        if (['Si', 'Al2O3'].includes(e.target.value)) {
                                            setters.setPeriodicDimensions('3');
                                        } else {
                                            setters.setPeriodicDimensions('0');
                                        }
                                        // Update lattice constant display to match crystal defaults
                                        const _latticeDefaults: Record<string, [string,string,string]> = {
                                            Si:    ['10.263', '10.263', '10.263'],  // FCC conventional a
                                            Al2O3: ['5.128',  '4.440',  '13.900'], // primitive cell a₁, a₂, c
                                        };
                                        const _ld = _latticeDefaults[e.target.value];
                                        if (_ld) { setters.setLatticeA(_ld[0]); setters.setLatticeB(_ld[1]); setters.setLatticeC(_ld[2]); }
                                        else { setters.setLatticeA('10.263'); setters.setLatticeB('10.263'); setters.setLatticeC('10.263'); }
                                    }} className={selectClass} style={{ flex: 1 }}>
                                        <optgroup label="Atoms">
                                            <option value="H">H — Hydrogen</option>
                                            <option value="He">He — Helium</option>
                                            <option value="Li">Li — Lithium</option>
                                            <option value="N_atom">N — Nitrogen atom</option>
                                            <option value="Na">Na — Sodium</option>
                                        </optgroup>
                                        <optgroup label="Diatomics">
                                            <option value="H2">H₂ — Hydrogen</option>
                                            <option value="LiH">LiH — Lithium Hydride</option>
                                            <option value="CO">CO — Carbon Monoxide</option>
                                            <option value="N2">N₂ — Nitrogen</option>
                                        </optgroup>
                                        <optgroup label="Polyatomics">
                                            <option value="H2O">H₂O — Water</option>
                                            <option value="NH3">NH₃ — Ammonia</option>
                                            <option value="CH4">CH₄ — Methane</option>
                                            <option value="C2H4">C₂H₄ — Ethylene</option>
                                            <option value="Benzene">C₆H₆ — Benzene</option>
                                        </optgroup>
                                        <optgroup label="Periodic Crystals">
                                            <option value="Si">Si — Silicon (FCC diamond)</option>
                                            <option value="Al2O3">Al₂O₃ — Sapphire (corundum)</option>
                                        </optgroup>
                                    </select>
                                    {/* 3D preview toggle button */}
                                    <button
                                        onClick={() => setters.setShowGeomPreview(!config.showGeomPreview)}
                                        title="3D 几何构型预览"
                                        style={{
                                            padding: '6px 10px', fontSize: 11, cursor: 'pointer',
                                            border: 'none', borderRadius: 7, whiteSpace: 'nowrap',
                                            background: config.showGeomPreview ? 'rgba(0,212,255,0.12)' : 'rgba(255,255,255,0.05)',
                                            outline: config.showGeomPreview ? '1px solid rgba(0,212,255,0.4)' : '1px solid #1f2937',
                                            color: config.showGeomPreview ? '#00d4ff' : '#8892a4',
                                        }}
                                    >
                                        3D ◈
                                    </button>
                                    </div>
                                    {/* 3D preview panel */}
                                    {config.showGeomPreview && (() => {
                                        const previewAtoms = MOLECULE_ATOMS[config.octopusMolecule];
                                        const boxR = parseFloat(config.octopusRadius) || 5;
                                        return previewAtoms ? (
                                            <div style={{ marginTop: 8 }}>
                                                <Mol3DViewer
                                                    atoms={previewAtoms}
                                                    boxRadius={boxR}
                                                    width={380}
                                                    height={260}
                                                    showLegend
                                                    showTable
                                                />
                                            </div>
                                        ) : null;
                                    })()}
                                    </>) : (
                                        /* Custom geometry editor */
                                        <>
                                        <Suspense fallback={<div className="p-4 text-gray-500 text-xs">Loading editor...</div>}>
                                            <GeometryEditor
                                                onChange={setters.setCustomAtoms}
                                                boxRadius={parseFloat(config.octopusRadius) || 5}
                                                initAtoms={MOLECULE_ATOMS[config.octopusMolecule]}
                                                initLabel={config.octopusMolecule}
                                            />
                                        </Suspense>
                                        {/* ── Confirm button ── */}
                                        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
                                            <button
                                                disabled={config.customAtoms.length === 0}
                                                onClick={() => {
                                                    setters.setConfirmedAtoms([...config.customAtoms]);
                                                    const cnt: Record<string,number> = {};
                                                    config.customAtoms.forEach(a => { cnt[a.symbol] = (cnt[a.symbol] || 0) + 1; });
                                                    const f = Object.entries(cnt).sort().map(([s,n]) => n===1?s:`${s}${n}`).join('');
                                                    setters.setConfirmedLabel(f || 'Custom');
                                                }}
                                                style={{
                                                    width: '100%', padding: '7px 0', fontSize: 11,
                                                    cursor: config.customAtoms.length === 0 ? 'not-allowed' : 'pointer',
                                                    border: 'none', borderRadius: 6,
                                                    background: config.customAtoms.length === 0
                                                        ? 'rgba(255,255,255,0.04)'
                                                        : 'rgba(0,212,255,0.12)',
                                                    outline: config.customAtoms.length === 0
                                                        ? '1px solid #1f2937'
                                                        : '1px solid rgba(0,212,255,0.4)',
                                                    color: config.customAtoms.length === 0 ? '#374151' : '#00d4ff',
                                                    fontWeight: 600, letterSpacing: '0.04em',
                                                    transition: 'all 0.15s',
                                                }}
                                            >
                                                ✓ 确认坐标用于计算
                                                {config.customAtoms.length > 0 && ` (${config.customAtoms.length} 原子)`}
                                            </button>
                                            {config.confirmedAtoms && config.confirmedAtoms.length > 0
                                                ? (
                                                    <>
                                                    <div style={{ fontSize: 9, color: '#22c55e', padding: '3px 8px',
                                                        background: 'rgba(34,197,94,0.06)', border: '1px solid rgba(34,197,94,0.2)',
                                                        borderRadius: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                                                        <span>✓</span>
                                                        <span>已确认：<b style={{ fontFamily: 'monospace' }}>{config.confirmedLabel}</b> · {config.confirmedAtoms.length} 原子 — 将用于 Octopus 输入文件</span>
                                                    </div>
                                                    {(() => {
                                                        const rSet = parseFloat(config.octopusRadius) || 5;
                                                        const maxDist = Math.max(...config.confirmedAtoms.map(a =>
                                                            Math.sqrt(a.x**2 + a.y**2 + a.z**2)));
                                                        const minR = Math.round((maxDist + 5.0) * 10) / 10;
                                                        if (maxDist > rSet) {
                                                            return (
                                                                <div style={{ fontSize: 9, color: '#f97316', padding: '3px 8px',
                                                                    background: 'rgba(249,115,22,0.06)', border: '1px solid rgba(249,115,22,0.3)',
                                                                    borderRadius: 4 }}>
                                                                    ⚠ 原子最远距原点 <b>{maxDist.toFixed(1)} Angstrom</b>，超出当前 Radius={rSet} Angstrom。
                                                                    服务端将自动扩展至 <b>{minR} Angstrom</b>（建议在"Box Radius"中设置该值以避免意外）。
                                                                </div>
                                                            );
                                                        }
                                                        return null;
                                                    })()}
                                                    </>
                                                ) : (
                                                    <div style={{ fontSize: 9, color: '#f59e0b', padding: '3px 8px',
                                                        background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)',
                                                        borderRadius: 4 }}>
                                                        ⚠ 尚未确认 — 计算将使用预设分子坐标
                                                    </div>
                                                )
                                            }
                                        </div>
                                        </>
                                    )}
                                    {config.octopusDimensions === '2D' && config.geomMode === 'preset' && (
                                        <div className="text-[10px] text-yellow-600 bg-yellow-950/30 border border-yellow-900/50 rounded-lg p-2 mt-1">
                                            2D mode: bond axes projected onto xy-plane.
                                        </div>
                                    )}
                                    {['Si', 'Al2O3'].includes(config.octopusMolecule) && (
                                        <div className="text-[10px] mt-1 p-2 rounded-lg" style={{ color: '#00d4ff', background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.2)' }}>
                                            Periodic crystal — PeriodicDimensions defaults to 3 (bulk). Override below for
                                            slab (2) or waveguide (1) simulations. LatticeVectors auto-loaded.
                                        </div>
                                    )}
                                </Field>
                            ) : (
                                <Section title="Model Potential" icon={<Zap className="w-4 h-4 text-yellow-400" />}>
                                    <select value={config.potentialType} onChange={e => setters.setPotentialType(e.target.value)} className={selectClass}>
                                        <option value="Harmonic">Harmonic Oscillator</option>
                                        <option value="InfiniteWell">Infinite Square Well</option>
                                        <option value="Custom">Custom Formula</option>
                                    </select>
                                </Section>
                            )}
                        </Section>

                        {/* ── Periodic System Settings ── */}
                        <Section title="Periodic System Settings" icon={<Grid3x3 className="w-4 h-4 text-purple-400" />} defaultOpen={config.periodicDimensions !== '0'}>
                            <Field label="Periodic Dimensions" hint="0 = isolated; 1/2/3 = periodic along x/xy/xyz">
                                <select value={config.periodicDimensions} onChange={e => setters.setPeriodicDimensions(e.target.value as any)} className={selectClass}>
                                    <option value="0">0 — Isolated (Dirichlet BC)</option>
                                    <option value="1">1 — Chain/wire (x periodic)</option>
                                    <option value="2">2 — Slab/surface (xy periodic)</option>
                                    <option value="3">3 — Bulk crystal (xyz periodic)</option>
                                </select>
                            </Field>
                            {config.periodicDimensions !== '0' && (
                                <>
                                    <div className="text-[10px] mb-1" style={{ color: '#8892a4' }}>Lattice constants (Angstrom)</div>
                                    <div className="grid gap-2" style={{ gridTemplateColumns: config.periodicDimensions === '1' ? '1fr' : config.periodicDimensions === '2' ? '1fr 1fr' : '1fr 1fr 1fr' }}>
                                        <Field label="a">
                                            <input type="number" value={config.latticeA} onChange={e => setters.setLatticeA(e.target.value)} step="0.1" className={inputClass} />
                                        </Field>
                                        {config.periodicDimensions !== '1' && (
                                            <Field label="b">
                                                <input type="number" value={config.latticeB} onChange={e => setters.setLatticeB(e.target.value)} step="0.1" className={inputClass} />
                                            </Field>
                                        )}
                                        {config.periodicDimensions === '3' && (
                                            <Field label="c">
                                                <input type="number" value={config.latticeC} onChange={e => setters.setLatticeC(e.target.value)} step="0.1" className={inputClass} />
                                            </Field>
                                        )}
                                    </div>
                                    <Field label="K-Points Grid" hint="Monkhorst-Pack, e.g. 4 4 4">
                                        <input type="text" value={config.kpointsGrid} onChange={e => setters.setKpointsGrid(e.target.value)}
                                            placeholder="2 2 2" className={inputClass} />
                                    </Field>
                                </>
                            )}
                        </Section>

                        <Section title="Mesh & Box Settings" icon={<Grid3x3 className="w-4 h-4 text-green-400" />}>
                            <div className="grid grid-cols-2 gap-2">
                                <Field label="Grid Spacing (Angstrom)" hint="Smaller = more accurate, more RAM">
                                    <input type="number" value={config.octopusSpacing} onChange={e => setters.setOctopusSpacing(e.target.value)} step="0.05" min="0.1" className={inputClass} />
                                </Field>
                                <Field label="Box Radius (Angstrom)">
                                    <input type="number" value={config.octopusRadius} onChange={e => setters.setOctopusRadius(e.target.value)} step="0.5" className={inputClass} />
                                </Field>
                            </div>
                            <Field label="Box Shape">
                                <select value={config.octopusBoxShape} onChange={e => setters.setOctopusBoxShape(e.target.value)} className={selectClass}>
                                    <option value="sphere">Sphere (default)</option>
                                    <option value="cylinder">Cylinder</option>
                                    <option value="parallelepiped">Parallelepiped</option>
                                    <option value="minimum">Minimum box (per-atom spheres)</option>
                                </select>
                            </Field>
                            <Field label="FD Derivatives Order" hint="4 = default; 6/8 for high-accuracy but slower">
                                <select value={config.derivativesOrder} onChange={e => setters.setDerivativesOrder(e.target.value as any)} className={selectClass}>
                                    <option value="4">4th order (default)</option>
                                    <option value="6">6th order (high accuracy)</option>
                                    <option value="8">8th order (very high accuracy)</option>
                                </select>
                            </Field>
                            <Field label="Non-Uniform Mesh (Curvilinear)" hint="Concentrates grid points near nuclei">
                                <select value={config.curvMethod} onChange={e => setters.setCurvMethod(e.target.value as any)} className={selectClass}>
                                    <option value="uniform">Uniform (default)</option>
                                    <option value="gygi">Gygi — non-uniform near atoms</option>
                                </select>
                            </Field>
                            {config.curvMethod === 'gygi' && (
                                <Field label="Gygi α" hint="Point concentration (0.1–1.0, typical 0.5)">
                                    <input type="number" value={config.curvGygiAlpha} onChange={e => setters.setCurvGygiAlpha(e.target.value)}
                                        step="0.1" min="0.1" max="1.0" className={inputClass} />
                                </Field>
                            )}
                            <label className="flex items-center gap-2 cursor-pointer" style={{ color: '#8892a4', fontSize: '12px' }}>
                                <input type="checkbox" checked={config.doubleGrid} onChange={e => setters.setDoubleGrid(e.target.checked)}
                                    style={{ accentColor: '#00d4ff' }} />
                                Double Grid (better pseudopotential accuracy)
                            </label>
                        </Section>

                        <Section title="HPC Runtime Resources" icon={<Cpu className="w-4 h-4 text-cyan-400" />}>
                            <div className="grid grid-cols-2 gap-2">
                                <Field label="Requested ncpus" hint="Default 64 for production benchmark runs">
                                    <input
                                        type="number"
                                        value={config.octopusNcpus}
                                        onChange={e => setters.setOctopusNcpus(e.target.value)}
                                        min="1"
                                        step="1"
                                        className={inputClass}
                                    />
                                </Field>
                                <Field label="Requested mpiprocs" hint="Will be clamped to ncpus in backend guardrails">
                                    <input
                                        type="number"
                                        value={config.octopusMpiprocs}
                                        onChange={e => setters.setOctopusMpiprocs(e.target.value)}
                                        min="1"
                                        step="1"
                                        className={inputClass}
                                    />
                                </Field>
                            </div>
                        </Section>

                        {config.octopusCalcMode === 'td' && (
                            <Section title="TD Propagation" icon={<Zap className="w-4 h-4 text-yellow-400" />}>
                                <div className="grid grid-cols-2 gap-2">
                                    <Field label="Max Steps">
                                        <input type="number" value={config.octopusTdSteps} onChange={e => setters.setOctopusTdSteps(e.target.value)} className={inputClass} />
                                    </Field>
                                    <Field label="Time Step (a.u.)">
                                        <input type="number" value={config.octopusTdTimeStep} onChange={e => setters.setOctopusTdTimeStep(e.target.value)} step="0.01" className={inputClass} />
                                    </Field>
                                </div>
                                <Field label="Propagator">
                                    <select value={config.octopusPropagator} onChange={e => setters.setOctopusPropagator(e.target.value)} className={selectClass}>
                                        <option value="aetrs">AETRS (Recommended)</option>
                                        <option value="exp0">Exponential (Order 0)</option>
                                        <option value="etrs">ETRS</option>
                                    </select>
                                </Field>
                                <Field label="Excitation Type" hint="类型: delta冲击/高斯脉冲/正弦/连续波">
                                    <select value={config.tdExcitationType} onChange={e => setters.setTdExcitationType(e.target.value as any)} className={selectClass}>
                                        <option value="delta">Delta kick (broadband)</option>
                                        <option value="gaussian">Gaussian pulse</option>
                                        <option value="sin">Sine wave (monochromatic)</option>
                                        <option value="continuous_wave">Continuous wave (CW)</option>
                                    </select>
                                </Field>
                                <div className="grid grid-cols-2 gap-2">
                                    <Field label="Polarization" hint="1=x  2=y  3=z">
                                        <select value={config.tdPolarization} onChange={e => setters.setTdPolarization(e.target.value as any)} className={selectClass}>
                                            <option value="1">x-axis</option>
                                            <option value="2">y-axis</option>
                                            <option value="3">z-axis</option>
                                        </select>
                                    </Field>
                                    <Field label="Amplitude (a.u.)">
                                        <input type="number" value={config.tdFieldAmplitude} onChange={e => setters.setTdFieldAmplitude(e.target.value)} step="0.001" className={inputClass} />
                                    </Field>
                                </div>
                                {config.tdExcitationType === 'gaussian' && (
                                    <div className="grid grid-cols-2 gap-2">
                                        <Field label="Pulse center t₀ (a.u.)" hint="Peak time of Gaussian envelope">
                                            <input type="number" value={config.tdGaussianT0} onChange={e => setters.setTdGaussianT0(e.target.value)} step="1" className={inputClass} />
                                        </Field>
                                        <Field label="Pulse width σ (a.u.)" hint="Standard deviation of Gaussian">
                                            <input type="number" value={config.tdGaussianSigma} onChange={e => setters.setTdGaussianSigma(e.target.value)} step="0.5" className={inputClass} />
                                        </Field>
                                    </div>
                                )}
                                {(config.tdExcitationType === 'sin' || config.tdExcitationType === 'continuous_wave') && (
                                    <Field label="Frequency ω (a.u.)" hint="0.057 a.u. ≈ 1.55 eV (visible)">
                                        <input type="number" value={config.tdSinFrequency} onChange={e => setters.setTdSinFrequency(e.target.value)} step="0.001" className={inputClass} />
                                    </Field>
                                )}
                                {/* ── Free Electron Probe (Self-Consistent) ── */}
                                <div className="mt-3 pt-3" style={{ borderTop: '1px solid #1a2035' }}>
                                    <label className="flex items-center gap-2 cursor-pointer mb-2" style={{ color: '#8892a4', fontSize: '12px' }}>
                                        <input type="checkbox" checked={config.feProbeEnabled} onChange={e => setters.setFeProbeEnabled(e.target.checked)}
                                            style={{ accentColor: '#00d4ff' }} />
                                        <span style={{ color: config.feProbeEnabled ? '#00d4ff' : '#8892a4', fontWeight: 500 }}>启用自由电子探针 (Free Electron Probe)</span>
                                    </label>
                                    {config.feProbeEnabled && (
                                        <div className="rounded-lg p-3 space-y-2" style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.15)' }}>
                                            <div className="text-[10px] mb-2" style={{ color: '#5a8fa8' }}>
                                                经典点电荷沿指定轴平直传播，库仑势作为 TD 外场叠加。<br />
                                                非相对论近似，适用于 v/c &lt; 0.9。
                                            </div>
                                            {/* Row 1: velocity + propagation direction */}
                                            <div className="grid grid-cols-2 gap-2">
                                                <Field label="速度 v/c" hint="0.01–0.99 (光速分数)">
                                                    <input type="number" value={config.feProbeVelocity} onChange={e => setters.setFeProbeVelocity(e.target.value)}
                                                        step="0.05" min="0.01" max="0.99" className={inputClass} />
                                                </Field>
                                                <Field label="传播方向轴" hint="电子束平移方向">
                                                    <select value={config.feProbeDirection} onChange={e => setters.setFeProbeDirection(e.target.value as 'x'|'y'|'z')} className={selectClass}>
                                                        <option value="x">X — 沿波导方向</option>
                                                        <option value="y">Y — 横向</option>
                                                        <option value="z">Z — 纵向</option>
                                                    </select>
                                                </Field>
                                            </div>
                                            {/* Row 2: geometric center XYZ */}
                                            <div style={{ fontSize: 9, color: '#374151', marginBottom: 2 }}>几何中心 (Angstrom) — 电子束起始截面位置</div>
                                            <div className="grid grid-cols-3 gap-2">
                                                <Field label="中心 X" hint="Angstrom">
                                                    <input type="number" value={config.feProbeCx} onChange={e => setters.setFeProbeCx(e.target.value)}
                                                        step="0.5" className={inputClass} />
                                                </Field>
                                                <Field label="中心 Y" hint="Angstrom">
                                                    <input type="number" value={config.feProbeCy} onChange={e => setters.setFeProbeCy(e.target.value)}
                                                        step="0.5" className={inputClass} />
                                                </Field>
                                                <Field label="中心 Z" hint="Angstrom">
                                                    <input type="number" value={config.feProbeCz} onChange={e => setters.setFeProbeCz(e.target.value)}
                                                        step="0.5" className={inputClass} />
                                                </Field>
                                            </div>
                                            {/* Row 3: beam count + charge */}
                                            <div className="grid grid-cols-2 gap-2">
                                                <Field label="电子束数目" hint="并行探针数量">
                                                    <input type="number" value={config.feProbeBeamCount} onChange={e => setters.setFeProbeBeamCount(e.target.value)}
                                                        step="1" min="1" max="16" className={inputClass} />
                                                </Field>
                                                <Field label="探针电荷 (e)" hint="-1 = 电子, +1 = 正电子">
                                                    <input type="number" value={config.feProbeCharge} onChange={e => setters.setFeProbeCharge(e.target.value)}
                                                        step="1" className={inputClass} />
                                                </Field>
                                            </div>
                                            <div className="text-[10px] px-2 py-1 rounded font-mono" style={{ color: '#f59e0b', background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)' }}>
                                                ⚠ 此模式需结合 Gaussian/CW 背景光场使用，独立 delta 模式下效果有限
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </Section>
                        )}

                        {(config.octopusCalcMode === 'gs' || config.octopusCalcMode === 'opt' || config.octopusCalcMode === 'em' || config.octopusCalcMode === 'casida') && (
                            <Section title="DFT Settings" icon={<Atom className="w-4 h-4" style={{ color: '#00d4ff' }} />}>
                                {config.octopusCalcMode === 'gs' && (
                                    <>
                                        <Field label="Detected GS Postprocess Style" hint="Derived from Molecule/Crystal selection; no second source of truth.">
                                            <div className="rounded-lg px-3 py-2 text-sm" style={{ background: '#0a1220', border: '1px solid #1e2d45', color: '#cbd5e1' }}>
                                                {config.gsConvergenceProfile === 'n_atom_official'
                                                    ? 'N_atom error-style (total/s/p error)'
                                                    : (config.gsConvergenceProfile === 'ch4_tutorial'
                                                        ? 'CH4 total-energy style (tail-band check)'
                                                        : 'General total-energy style')}
                                            </div>
                                        </Field>
                                        <label className="flex items-center gap-2 cursor-pointer" style={{ color: '#94a3b8', fontSize: '12px' }}>
                                            <input
                                                type="checkbox"
                                                checked={config.gsEnableScan}
                                                onChange={(e) => setters.setGsEnableScan(e.target.checked)}
                                                style={{ accentColor: '#00d4ff' }}
                                            />
                                            Enable GS parameter scan (optional)
                                        </label>
                                        {config.gsEnableScan && (
                                            <>
                                                <Field label="Spacing Scan Spec" hint="Examples: 0.26,0.24,0.22 | range(0.14,0.02,0.26) | linspace(0.14,0.26,7) | linspace(0.14,0.02,0.26)">
                                                    <input type="text" value={config.gsScanSpec} onChange={e => setters.setGsScanSpec(e.target.value)} className={inputClass} />
                                                </Field>
                                                <div className="grid grid-cols-2 gap-2">
                                                    <Field label="Reference Spacing (A)">
                                                        <input type="number" value={config.gsReferenceSpacing} onChange={e => setters.setGsReferenceSpacing(e.target.value)} step="0.01" className={inputClass} />
                                                    </Field>
                                                    <Field label="Reference URL">
                                                        <input type="text" value={config.gsReferenceUrl} onChange={e => setters.setGsReferenceUrl(e.target.value)} className={inputClass} />
                                                    </Field>
                                                </div>
                                            </>
                                        )}
                                    </>
                                )}
                                <Field label="Extra States" hint="Unoccupied KS states to include">
                                    <input type="number" value={config.octopusExtraStates} onChange={e => setters.setOctopusExtraStates(e.target.value)} className={inputClass} />
                                </Field>
                                <Field label="Eigen Solver" hint="Optional, e.g. chebyshev_filter">
                                    <input type="text" value={config.octopusEigenSolver} onChange={e => setters.setOctopusEigenSolver(e.target.value)} placeholder="auto" className={inputClass} />
                                </Field>
                                <Field label="Propagator" hint="Exposed in GS/DFT setup to avoid hidden defaults">
                                    <select value={config.octopusPropagator} onChange={e => setters.setOctopusPropagator(e.target.value)} className={selectClass}>
                                        <option value="aetrs">AETRS (Recommended)</option>
                                        <option value="exp0">Exponential (Order 0)</option>
                                        <option value="etrs">ETRS</option>
                                    </select>
                                </Field>
                                {/* Tiered XC Functional Selector */}
                                <Field label="XC Category">
                                    <select value={config.xcCategory} onChange={e => {
                                        setters.setXcCategory(e.target.value);
                                        // Reset preset to first option in new category
                                        const defaults: Record<string,string> = {
                                            lda: 'lda_x+lda_c_pz',
                                            gga: 'gga_x_pbe+gga_c_pbe',
                                            mgga: 'mgga_x_scan+mgga_c_scan',
                                            hybrid: 'hyb_gga_xc_b3lyp',
                                            exact: 'hartree_fock',
                                        };
                                        setters.setXcPreset(defaults[e.target.value] || 'lda_x+lda_c_pz');
                                        setters.setXcOverride('');
                                    }} className={selectClass}>
                                        <option value="lda">LDA — Local Density</option>
                                        <option value="gga">GGA — Generalized Gradient</option>
                                        <option value="mgga">Meta-GGA — 3rd rung</option>
                                        <option value="hybrid">Hybrid — HF exchange mix</option>
                                        <option value="exact">Exact Exchange / OEP</option>
                                    </select>
                                </Field>
                                <Field label="XC Preset">
                                    <select value={config.xcPreset} onChange={e => { setters.setXcPreset(e.target.value); setters.setXcOverride(''); }} className={selectClass}>
                                        {config.xcCategory === 'lda' && (<>
                                            <option value="lda_x+lda_c_pz">PZ81 (Perdew-Zunger) — default</option>
                                            <option value="lda_x+lda_c_pw">PW92 (Perdew-Wang)</option>
                                            <option value="lda_x+lda_c_vwn">VWN5 (Vosko-Wilk-Nusair)</option>
                                            <option value="lda_x">X-only LDA</option>
                                        </>)}
                                        {config.xcCategory === 'gga' && (<>
                                            <option value="gga_x_pbe+gga_c_pbe">PBE (Perdew-Burke-Ernzerhof)</option>
                                            <option value="gga_x_b88+gga_c_lyp">BLYP (Becke-Lee-Yang-Parr)</option>
                                            <option value="gga_x_pbe_sol+gga_c_pbe_sol">PBEsol (solids/surfaces)</option>
                                            <option value="gga_x_rpbe+gga_c_pbe">RPBE (chemisorption)</option>
                                        </>)}
                                        {config.xcCategory === 'mgga' && (<>
                                            <option value="mgga_x_scan+mgga_c_scan">SCAN (state-of-art meta-GGA)</option>
                                            <option value="mgga_x_tpss+mgga_c_tpss">TPSS (transition metals)</option>
                                            <option value="mgga_x_m06l+mgga_c_m06l">M06-L (main-group)</option>
                                        </>)}
                                        {config.xcCategory === 'hybrid' && (<>
                                            <option value="hyb_gga_xc_b3lyp">B3LYP (most used in chem)</option>
                                            <option value="hyb_gga_xc_pbeh">PBE0/PBEH (25% HF)</option>
                                            <option value="hyb_gga_xc_hse06">HSE06 (range-sep, solids)</option>
                                        </>)}
                                        {config.xcCategory === 'exact' && (<>
                                            <option value="hartree_fock">Hartree-Fock (HF)</option>
                                            <option value="oep_kli">KLI approximation</option>
                                            <option value="oep_slater">Slater approximation</option>
                                        </>)}
                                    </select>
                                </Field>
                                <Field label="Override (libxc string)" hint="Leave blank to use preset above">
                                    <input type="text" value={config.xcOverride} onChange={e => setters.setXcOverride(e.target.value)}
                                        placeholder="e.g. gga_x_pbe+gga_c_pbe" className={inputClass} />
                                </Field>
                                {(config.xcOverride.trim() || config.xcPreset) && (
                                    <div className="text-[10px] px-2 py-1 rounded font-mono" style={{ color: '#00d4ff', background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.15)' }}>
                                        Active: {config.xcOverride.trim() || config.xcPreset}
                                    </div>
                                )}
                                <Field label="SCF Mixing Scheme">
                                    <select value={config.mixingScheme} onChange={e => setters.setMixingScheme(e.target.value)} className={selectClass}>
                                        <option value="broyden">Broyden (recommended)</option>
                                        <option value="linear">Linear Mixing</option>
                                        <option value="diis">DIIS</option>
                                    </select>
                                </Field>
                                <Field label="Spin Components">
                                    <select value={config.spinComponents} onChange={e => setters.setSpinComponents(e.target.value)} className={selectClass}>
                                        <option value="unpolarized">Unpolarized</option>
                                        <option value="spin_polarized">Spin Polarized</option>
                                        <option value="non_collinear">Non-Collinear (SOC)</option>
                                    </select>
                                </Field>
                            </Section>
                        )}

                        {config.octopusCalcMode === 'casida' && (
                            <Section title="Casida LR-TDDFT" icon={<Zap className="w-4 h-4" style={{ color: '#a78bfa' }} />}>
                                <Field label="KS State Range" hint="CasidaKohnShamStates range, e.g. 1-16">
                                    <input type="text" value={config.casidaKohnShamStates} onChange={e => setters.setCasidaKohnShamStates(e.target.value)} placeholder="1-8" className={inputClass} />
                                </Field>
                                <Field label="Extra States" hint="Unoccupied KS states for Casida">
                                    <input type="number" value={config.octopusExtraStates} onChange={e => setters.setOctopusExtraStates(e.target.value)} className={inputClass} />
                                </Field>
                            </Section>
                        )}
                    </>
                )}

                {workflowStage === 'setup' && config.octopusCalcMode === 'td' && (
                    <div className="mt-4 rounded-lg p-2" style={{ background: '#0d1525', border: '1px solid #1a2035' }}>
                        <div className="text-[11px] mb-2" style={{ color: '#94a3b8' }}>
                            Setup Actions (Octopus Reviewer)
                        </div>
                        {capabilityMatrix?.rows && capabilityMatrix.rows.length > 0 && (
                            <div className="mb-2 rounded-lg p-2" style={{ background: 'rgba(56,189,248,0.08)', border: '1px solid rgba(56,189,248,0.30)' }}>
                                <div className="text-[11px]" style={{ color: '#7dd3fc' }}>
                                    Capability Matrix: {capabilityMatrix.tutorial_count ?? 0} tutorials / {capabilityMatrix.category_count ?? capabilityMatrix.rows.length} categories
                                </div>
                                <div className="text-[11px] mt-1" style={{ color: '#cbd5e1' }}>
                                    P0 categories: {
                                        capabilityMatrix.rows
                                            .filter((r) => r.implementation_priority === 'P0')
                                            .map((r) => `${r.category}(${r.support_status})`)
                                            .join(', ') || 'none'
                                    }
                                </div>
                                {(() => {
                                    const selected = (caseTypeRegistry?.case_types || []).find((ct) => ct.case_type === config.caseType);
                                    if (!selected) return null;
                                    const tutorials = (selected.canonical_tutorials || []).slice(0, 3);
                                    return (
                                        <div className="text-[10px] mt-1" style={{ color: '#94a3b8' }}>
                                            Canonical tutorials: {
                                                tutorials.length > 0
                                                    ? tutorials
                                                        .map((t) => t.title || t.url || 'untitled')
                                                        .join(' | ')
                                                    : 'none'
                                            }
                                        </div>
                                    );
                                })()}
                            </div>
                        )}
                        <div className="mt-2 rounded-lg p-2" style={{ background: 'rgba(249,115,22,0.08)', border: '1px solid rgba(251,146,60,0.35)' }}>
                            <div className="text-[11px] mb-2" style={{ color: '#fdba74' }}>
                                Reviewer tasks now follow Calculation Mode automatically.
                            </div>
                            <div className="text-[11px]" style={{ color: '#cbd5e1' }}>
                                Current mode: <span style={{ color: '#fed7aa' }}>{config.octopusCalcMode.toUpperCase()}</span>
                            </div>
                            <div className="text-[11px] mt-1" style={{ color: '#cbd5e1' }}>
                                Auto suite: {
                                    getSuiteTasksFromCalculationMode()
                                        .map((id) => ({
                                            ch4_gs_reference: 'Methane GS reference',
                                            h2o_gs_reference: 'GS reference',
                                            h2o_tddft_absorption: 'Absorption cross section',
                                            h2o_tddft_dipole_response: 'TD dipole response',
                                            h2o_tddft_radiation_spectrum: 'Radiation spectrum',
                                            h2o_tddft_eels_spectrum: 'EELS spectrum',
                                        } as Record<SuiteTaskId, string>)[id])
                                        .join(' + ')
                                }
                            </div>
                            <div className="text-[10px] mt-1" style={{ color: '#94a3b8' }}>
                                Approved molecules: {Array.from(approvedUiMolecules).join(', ') || 'none'}
                            </div>

                            <button
                                onClick={runDftTddftAgentSuite}
                                disabled={isComputing}
                                className="w-full mt-2 disabled:opacity-40 disabled:cursor-not-allowed font-semibold rounded-xl px-4 py-2.5 flex items-center justify-center gap-2 transition-all"
                                style={{
                                    background: 'rgba(249,115,22,0.14)',
                                    color: '#fb923c',
                                    border: '1px solid rgba(251,146,60,0.4)',
                                }}
                            >
                                {isComputing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
                                {isComputing
                                    ? 'Running Mode-Aligned Reviewer Suite...'
                                    : 'Run Mode-Aligned Reviewer Suite'}
                            </button>
                        </div>
                    </div>
                )}

                {/* Main Controls */}
                <div className="mt-4 pt-3 flex flex-col gap-2" style={{ borderTop: '1px solid #1a2035' }}>
                    <div className="flex justify-between items-center px-1">
                        <span className="text-xs font-mono" style={{ color: '#8892a4' }}>{config.engineMode === 'octopus3D' ? 'Octopus-v16 MCP' : config.engineMode === 'vasp' ? 'VASP PAW-PBE' : 'Local Python Engine'}</span>
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
                            background: config.engineMode === 'octopus3D'
                                ? (isComputing ? 'rgba(0,212,255,0.08)' : 'rgba(0,212,255,0.12)')
                                : config.engineMode === 'vasp'
                                ? (isComputing ? 'rgba(168,85,247,0.08)' : 'rgba(168,85,247,0.12)')
                                : 'rgba(255,255,255,0.05)',
                            color: config.engineMode === 'octopus3D' ? '#00d4ff' : config.engineMode === 'vasp' ? '#a855f7' : '#8892a4',
                            border: config.engineMode === 'octopus3D' ? '1px solid rgba(0,212,255,0.35)' : config.engineMode === 'vasp' ? '1px solid rgba(168,85,247,0.35)' : '1px solid #1e2d45',
                        }}>
                        {isComputing ? <Loader2 className="w-5 h-5 animate-spin" /> : <PlayCircle className="w-5 h-5" />}
                        {isComputing ? 'Computing...' : 'Initiate Computation'}
                    </button>
                    <button
                        onClick={requestPause}
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

                {suiteReview && (
                    <div className="mt-2 rounded-lg p-2" style={{ background: '#111827', border: '1px solid #273244' }}>
                        <div className="text-[11px] mb-1" style={{ color: '#93c5fd' }}>
                            {suiteReview.title || 'DFT/TDDFT Agent Review'}
                        </div>
                        <div className="text-[11px] mb-1" style={{ color: suiteReview.final_verdict === 'PASS' ? '#22c55e' : '#ef4444' }}>
                            Verdict: {suiteReview.final_verdict || 'UNKNOWN'}
                        </div>
                        <div className="grid gap-1 text-[10px]" style={{ color: '#cbd5e1' }}>
                            {Object.entries(suiteReview.checks || {}).map(([k, v]) => (
                                <div key={k}>{k}: {String(Boolean(v))}</div>
                            ))}
                        </div>
                        {(suiteReview.case_cards || []).length > 0 && (
                            <div className="mt-2 grid gap-1 text-[10px]" style={{ color: '#94a3b8' }}>
                                {(suiteReview.case_cards || []).map((card) => (
                                    <div key={card.scenario_id || card.title}>
                                        {(card.scenario_id || card.title || 'case')}: {card.status || 'UNKNOWN'} | cross={card.optical_points ?? 0} | dipole={card.dipole_points ?? 0} | metric={card.comparison?.metric || '-'} | computed={card.comparison?.computed ?? '-'} | expected={card.comparison?.reference ?? '-'} | delta={card.comparison?.delta ?? '-'} | node={card.scheduler?.selected_node || '-'} | ncpus={card.scheduler?.ncpus ?? '-'} | queue={card.scheduler?.queue || '-'} | job={card.scheduler?.job_id || '-'}
                                    </div>
                                ))}
                            </div>
                        )}
                        {suiteReportMd && (
                            <div className="mt-2 text-[10px]" style={{ color: '#60a5fa' }}>
                                Report: {suiteReportMd}
                            </div>
                        )}
                    </div>
                )}

                {benchmarkReview && (
                    <div className="mt-2 rounded-lg p-2" style={{ background: '#111827', border: '1px solid #273244' }}>
                        <div className="text-[11px] mb-1" style={{ color: '#cbd5e1' }}>
                            Benchmark Delta Review: {benchmarkReview.case_id || harnessCaseId}
                        </div>
                        <div className="text-[11px] mb-1" style={{ color: benchmarkReview.final_verdict === 'PASS' ? '#22c55e' : '#ef4444' }}>
                            Verdict: {benchmarkReview.final_verdict || 'UNKNOWN'}
                        </div>
                        {benchmarkReview.delta && (
                            <div className="text-[10px] mb-1" style={{ color: '#94a3b8' }}>
                                rel_error={typeof benchmarkReview.delta.relative_error === 'number' ? benchmarkReview.delta.relative_error.toExponential(3) : 'N/A'} |
                                threshold={typeof benchmarkReview.delta.threshold === 'number' ? benchmarkReview.delta.threshold.toExponential(3) : 'N/A'} |
                                margin={typeof benchmarkReview.delta.margin === 'number' ? benchmarkReview.delta.margin.toExponential(3) : 'N/A'}
                            </div>
                        )}
                        <div className="grid gap-1 text-[10px]" style={{ color: '#cbd5e1' }}>
                            {Object.entries(benchmarkReview.checks || {}).map(([k, v]) => (
                                <div key={k}>{k}: {String(Boolean(v))}</div>
                            ))}
                        </div>
                        {benchmarkReview.next_action && (
                            <div className="text-[10px] mt-1" style={{ color: '#60a5fa' }}>
                                Next: {benchmarkReview.next_action}
                            </div>
                        )}
                        {benchmarkReview.repair_type && (
                            <div className="text-[10px] mt-1" style={{ color: '#f59e0b' }}>
                                Repair: {benchmarkReview.repair_type}
                                {typeof benchmarkReview.repair_confidence === 'number' ? ` (${Math.round(benchmarkReview.repair_confidence * 100)}%)` : ''}
                            </div>
                        )}
                        {benchmarkReview.benchmark_review && (
                            <div className="text-[10px] mt-1" style={{ color: '#93c5fd' }}>
                                benchmark_review: {JSON.stringify(benchmarkReview.benchmark_review)}
                            </div>
                        )}
                    </div>
                )}

                <StatusBadge status={status as RunStatus} elapsedSeconds={elapsedSeconds} isComputing={isComputing} />

                {dispatchSummary && Array.isArray(dispatchSummary.phaseStream) && dispatchSummary.phaseStream.length > 0 && (
                    <div className="mt-3 rounded-lg p-3" style={{ border: '1px solid #1a2035', background: '#0a1220' }}>
                        <div className="text-[11px] uppercase tracking-widest mb-2" style={{ color: '#64748b' }}>
                            Dispatch Phase Stream
                        </div>
                        <div className="flex flex-wrap gap-2 mb-2">
                            {dispatchSummary.phaseStream.map((item, idx) => {
                                const phase = String(item?.phase || `P${idx + 1}`);
                                const state = String(item?.state || 'unknown').toLowerCase();
                                const tone = state === 'completed' || state === 'dispatched'
                                    ? { bg: 'rgba(34,197,94,0.12)', fg: '#22c55e', bd: 'rgba(34,197,94,0.35)' }
                                    : state === 'failed' || state === 'blocked'
                                        ? { bg: 'rgba(239,68,68,0.12)', fg: '#ef4444', bd: 'rgba(239,68,68,0.35)' }
                                        : state === 'queued'
                                            ? { bg: 'rgba(245,158,11,0.12)', fg: '#f59e0b', bd: 'rgba(245,158,11,0.35)' }
                                            : { bg: 'rgba(148,163,184,0.12)', fg: '#94a3b8', bd: 'rgba(148,163,184,0.35)' };
                                return (
                                    <div key={`${phase}_${idx}`} className="text-[10px] px-2 py-1 rounded-md font-mono" style={{
                                        background: tone.bg,
                                        color: tone.fg,
                                        border: `1px solid ${tone.bd}`,
                                    }}>
                                        {phase}: {state.toUpperCase()}
                                    </div>
                                );
                            })}
                        </div>
                        <div className="text-[10px]" style={{ color: '#94a3b8' }}>
                            dispatch={dispatchSummary.dispatchStatus || 'unknown'} | human={dispatchSummary.humanStatus || '-'} | route={dispatchSummary.workflowRoute || '-'} | state={dispatchSummary.workflowState || '-'}
                        </div>
                        {dispatchSummary.physicsResult && (
                            <div className="mt-2 rounded-md p-2" style={{ background: '#0d1525', border: '1px solid #1a2035' }}>
                                <div className="text-[10px]" style={{ color: '#cbd5e1' }}>
                                    molecule={dispatchSummary.physicsResult.molecule_name || 'H2'} | mode={dispatchSummary.physicsResult.calc_mode || '-'}
                                </div>
                                <div className="text-[10px] mt-1" style={{ color: '#93c5fd' }}>
                                    E0={typeof dispatchSummary.physicsResult.ground_state_energy_hartree === 'number'
                                        ? dispatchSummary.physicsResult.ground_state_energy_hartree.toFixed(8)
                                        : 'N/A'} Ha | spectrum_points={dispatchSummary.physicsResult.absorption_spectrum_points ?? 0}
                                </div>
                                <div className="text-[10px] mt-1" style={{ color: '#86efac' }}>
                                    delta={typeof dispatchSummary.physicsResult.benchmark_delta?.relative_error === 'number'
                                        ? dispatchSummary.physicsResult.benchmark_delta?.relative_error.toExponential(3)
                                        : 'N/A'}
                                    {' '}| threshold={typeof dispatchSummary.physicsResult.benchmark_delta?.threshold === 'number'
                                        ? dispatchSummary.physicsResult.benchmark_delta?.threshold.toExponential(3)
                                        : 'N/A'}
                                    {' '}| within_tol={String(Boolean(dispatchSummary.physicsResult.benchmark_delta?.within_tolerance))}
                                </div>
                                {!dispatchSummary.physicsResult.has_required_fields && (
                                    <div className="text-[10px] mt-1" style={{ color: '#fca5a5' }}>
                                        physics_blocked: {(dispatchSummary.physicsResult.missing_fields || []).join(', ') || 'unknown'}
                                    </div>
                                )}
                            </div>
                        )}
                        {dispatchSummary.reportPath && (
                            <div className="text-[10px] mt-1" style={{ color: '#60a5fa' }}>
                                report: {dispatchSummary.reportPath}
                            </div>
                        )}
                    </div>
                )}

                <RuntimeLog logs={logs} isComputing={isComputing} />

                {result && !isComputing && (
                    <div className="mt-3 rounded-lg overflow-hidden" style={{ border: '1px solid #1a2035', background: '#0a0e1a' }}>
                        <div className="p-4">
                            <h3 className="text-xs font-mono mb-3 tracking-widest" style={{ color: '#4b5563' }}>COMPUTATION RESULTS</h3>
                            <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 mb-2">
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
                                        {displayResultSeconds != null ? displayResultSeconds.toFixed(1) : '—'}s
                                    </div>
                                </div>
                            </div>
                            <ErrorBoundary>
                                <Suspense fallback={<div className="p-4 text-gray-500 text-xs">Loading results...</div>}>
                                    <ResultsPanel result={result} resultHistory={resultHistory} runDurationSeconds={displayResultSeconds} />
                                </Suspense>
                            </ErrorBoundary>
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}
