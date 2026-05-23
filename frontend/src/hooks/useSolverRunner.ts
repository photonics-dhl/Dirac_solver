import { useState, useRef, useCallback } from 'react';
import type { OctopusConfig } from './useOctopusConfig';
import { adaptVaspResult } from '../utils/vaspAdapter';

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/$/, '') || '';

export type RunStatus = 'IDLE' | 'RUNNING' | 'SUCCESS' | 'ERROR' | 'PAUSED';
export type WorkflowStage = 'setup' | 'execute' | 'review';

export function useSolverRunner() {
    const [isComputing, setIsComputing] = useState(false);
    const [status, setStatus] = useState<RunStatus>('IDLE');
    const [logs, setLogs] = useState<string[]>(['[System] Solver initialized. Configure parameters and run.']);
    const [result, setResult] = useState<any | null>(null);
    const [resultHistory, setResultHistory] = useState<Record<string, any>>({});
    const [runStartAt, setRunStartAt] = useState<number | null>(null);
    const [elapsedSeconds, setElapsedSeconds] = useState(0);
    const [lastRunSeconds, setLastRunSeconds] = useState<number | null>(null);
    const [workflowStage, setWorkflowStage] = useState<WorkflowStage>('setup');
    const [activeRunLabel, setActiveRunLabel] = useState<string>('idle');

    const eventSourceRef = useRef<EventSource | null>(null);
    const runInProgressRef = useRef(false);
    const timerRef = useRef<number | null>(null);

    const clearTimers = useCallback(() => {
        if (timerRef.current !== null) {
            window.clearInterval(timerRef.current);
            timerRef.current = null;
        }
    }, []);

    const requestPause = useCallback(() => {
        if (!isComputing) return;
        if (eventSourceRef.current) {
            try { eventSourceRef.current.close(); } catch { /* ignore */ }
            eventSourceRef.current = null;
        }
        setIsComputing(false);
        setStatus('PAUSED');
        setWorkflowStage('review');
        setLastRunSeconds((Date.now() - (runStartAt ?? Date.now())) / 1000);
        runInProgressRef.current = false;
        clearTimers();
        setLogs(prev => [...prev, `[System] Pause requested by operator for ${activeRunLabel}`]);
    }, [isComputing, runStartAt, activeRunLabel, clearTimers]);

    const buildOctopusConfig = useCallback((config: OctopusConfig): Record<string, unknown> => {
        const gridSpacing = parseFloat(config.spatialRange) / parseInt(config.gridPoints);
        const effectivePicture = config.picture === 'auto'
            ? (config.problemType === 'scattering' ? 'interaction' : 'schrodinger')
            : config.picture;

        const requestedNcpus = Math.max(1, parseInt(config.octopusNcpus, 10) || 64);
        const requestedMpiprocs = Math.min(
            requestedNcpus,
            Math.max(1, parseInt(config.octopusMpiprocs, 10) || requestedNcpus),
        );

        const payload: Record<string, unknown> = {
            unitSystem: config.unitSystem,
            mass: parseFloat(config.particleMass),
            charge: parseFloat(config.particleCharge),
            energy: parseFloat(config.electronEnergy),
            dimensionality: config.dimensionality,
            spatialRange: parseFloat(config.spatialRange),
            gridPoints: parseInt(config.gridPoints),
            gridSpacing,
            boundaryCondition: config.boundaryCondition,
            potentialType: config.potentialType,
            potentialStrength: parseFloat(config.potentialStrength),
            wellWidth: parseFloat(config.wellWidth),
            customExpression: config.potentialType === 'Custom' ? config.customExpression : undefined,
            potentialDataMode: config.potentialDataMode,
            equationType: config.equationType,
            problemType: config.problemType,
            picture: effectivePicture,
            numTimeSteps: parseInt(config.numTimeSteps),
            totalTime: parseFloat(config.totalTime),
            gaussianCenter: parseFloat(config.gaussianCenter),
            gaussianWidth: parseFloat(config.gaussianWidth),
            gaussianMomentum: parseFloat(config.gaussianMomentum),
            scatteringEnergyMin: parseFloat(config.scatteringEMin),
            scatteringEnergyMax: parseFloat(config.scatteringEMax),
            scatteringEnergySteps: parseInt(config.scatteringESteps),
            engineMode: config.engineMode,
            octopusDimensions: config.octopusDimensions,
            calcMode: config.octopusCalcMode,
            caseType: config.caseType,
            octopusSpacing: parseFloat(config.octopusSpacing),
            octopusRadius: parseFloat(config.octopusRadius),
            octopusBoxShape: config.octopusBoxShape,
            octopusLengthUnit: 'angstrom',
            octopusUnitsOutput: 'eV_Angstrom',
            octopusMolecule: config.geomMode === 'custom' && config.confirmedAtoms && config.confirmedAtoms.length > 0
                ? (config.confirmedLabel || 'Custom')
                : config.octopusMolecule,
            molecule: config.geomMode === 'custom' && config.confirmedAtoms && config.confirmedAtoms.length > 0
                ? { name: config.confirmedLabel || 'Custom', atoms: config.confirmedAtoms }
                : config.octopusMolecule,
            ...(config.geomMode === 'custom' && config.confirmedAtoms && config.confirmedAtoms.length > 0
                ? { customAtoms: config.confirmedAtoms } : {}),
            octopusTdSteps: parseInt(config.octopusTdSteps),
            octopusTdTimeStep: parseFloat(config.octopusTdTimeStep),
            octopusPropagator: config.octopusPropagator,
            octopusEigenSolver: config.octopusEigenSolver.trim() || undefined,
            octopusNcpus: requestedNcpus,
            octopusMpiprocs: requestedMpiprocs,
            tdExcitationType: config.tdExcitationType,
            tdPolarization: parseInt(config.tdPolarization),
            tdFieldAmplitude: parseFloat(config.tdFieldAmplitude),
            tdGaussianSigma: parseFloat(config.tdGaussianSigma),
            tdGaussianT0: parseFloat(config.tdGaussianT0),
            tdSinFrequency: parseFloat(config.tdSinFrequency),
            feProbeEnabled: config.feProbeEnabled,
            feProbeVelocity: parseFloat(config.feProbeVelocity),
            feProbeDirection: config.feProbeDirection,
            feProbeCenterX: parseFloat(config.feProbeCx),
            feProbeCenterY: parseFloat(config.feProbeCy),
            feProbeCenterZ: parseFloat(config.feProbeCz),
            feProbeBeamCount: parseInt(config.feProbeBeamCount),
            feProbeCharge: parseFloat(config.feProbeCharge),
            octopusExtraStates: parseInt(config.octopusExtraStates),
            casidaKohnShamStates: config.casidaKohnShamStates,
            xcFunctional: config.xcOverride.trim() || config.xcPreset,
            speciesMode: config.speciesMode,
            pseudopotentialSet: config.pseudopotentialSet,
            mixingScheme: config.mixingScheme,
            spinComponents: config.spinComponents,
            periodicDimensions: config.periodicDimensions,
            kpointsGrid: config.kpointsGrid,
            latticeA: parseFloat(config.latticeA),
            latticeB: parseFloat(config.latticeB),
            latticeC: parseFloat(config.latticeC),
            derivativesOrder: parseInt(config.derivativesOrder),
            curvMethod: config.curvMethod,
            curvGygiAlpha: parseFloat(config.curvGygiAlpha),
            doubleGrid: config.doubleGrid,
        };

        return payload;
    }, []);

    const run = useCallback(async (config: OctopusConfig, _onSuiteNeeded?: () => void) => {
        runInProgressRef.current = true;

        const runStartTs = Date.now();
        setWorkflowStage('execute');
        setActiveRunLabel('physics_run');
        setIsComputing(true);
        setStatus('RUNNING');
        setResult(null);
        setRunStartAt(runStartTs);
        setElapsedSeconds(0);
        setLastRunSeconds(null);

        const engineLabel = config.engineMode === 'octopus3D' ? 'Octopus' : config.engineMode === 'vasp' ? 'VASP' : config.equationType;
        const dimLabel = config.engineMode === 'octopus3D' ? '' : `(${config.dimensionality})`;
        setLogs([`[System] Starting ${engineLabel} solver${dimLabel}...`]);

        timerRef.current = window.setInterval(() => {
            setElapsedSeconds((Date.now() - runStartTs) / 1000);
        }, 200);

        // ── VASP path ──
        if (config.engineMode === 'vasp') {
            const vaspCfg: Record<string, unknown> = {
                octopusMolecule: config.geomMode === 'custom' && config.confirmedAtoms && config.confirmedAtoms.length > 0
                    ? (config.confirmedLabel || 'Custom') : config.octopusMolecule,
                molecule: config.geomMode === 'custom' && config.confirmedAtoms && config.confirmedAtoms.length > 0
                    ? { name: config.confirmedLabel || 'Custom', atoms: config.confirmedAtoms }
                    : config.octopusMolecule,
                ...(config.geomMode === 'custom' && config.confirmedAtoms && config.confirmedAtoms.length > 0
                    ? { customAtoms: config.confirmedAtoms } : {}),
                xcFunctional: config.xcOverride.trim() || config.xcPreset,
                spinComponents: config.spinComponents,
                encut: parseInt(config.vaspEncuit, 10) || 400,
                ediff: parseFloat(config.vaspEdiff) || 1e-6,
                nelmin: parseInt(config.vaspNelmin, 10) || 5,
                ismear: parseInt(config.vaspIsmear, 10) || 0,
                sigma: parseFloat(config.vaspSigma) || 0.01,
                kpointsType: config.vaspKpointsType,
                vaspBox: parseFloat(config.vaspBox) || 10.0,
                prec: config.vaspPrec,
            };
            if (config.vaspNelect.trim()) vaspCfg.nelect = parseFloat(config.vaspNelect);
            if (config.vaspNbands.trim()) vaspCfg.nbands = parseInt(config.vaspNbands, 10);

            setLogs(prev => [...prev, `[VASP] POST /solve_vasp → molecule=${vaspCfg.octopusMolecule}`]);
            try {
                const resp = await fetch(`${API_BASE}/solve_vasp`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(vaspCfg),
                });
                const vaspData = await resp.json();
                if (vaspData.status === 'error') {
                    throw new Error(vaspData.message || 'VASP calculation failed');
                }
                const adapted = adaptVaspResult(vaspData, vaspCfg);
                setStatus('SUCCESS');
                setResult(adapted);
                setResultHistory(prev => ({ ...prev, vasp: adapted }));
                const energy = typeof vaspData.total_energy_ev === 'number' ? vaspData.total_energy_ev.toFixed(4) : 'N/A';
                setLogs(prev => [...prev, `✓ VASP complete — Etot = ${energy} eV`, `  SCF iterations: ${vaspData.scf_iterations ?? 'N/A'}`]);
            } catch (err: unknown) {
                const msg = err instanceof Error ? err.message : String(err);
                setStatus('ERROR');
                setLogs(prev => [...prev, `✗ VASP Error: ${msg}`]);
            } finally {
                setIsComputing(false);
                setWorkflowStage('review');
                setLastRunSeconds((Date.now() - runStartTs) / 1000);
                clearTimers();
                runInProgressRef.current = false;
            }
            return;
        }

        // ── Octopus SSE path ──
        const payload = buildOctopusConfig(config);

        // N_atom special handling
        if (config.engineMode === 'octopus3D' && config.octopusCalcMode === 'gs'
            && config.geomMode !== 'custom'
            && String(config.octopusMolecule).trim() === 'N_atom') {
            Object.assign(payload, {
                speciesMode: 'pseudo',
                pseudopotentialSet: 'standard',
                octopusLengthUnit: 'angstrom',
                octopusUnitsOutput: 'eV_Angstrom',
                spinComponents: 'spin_polarized',
                octopusExtraStates: 1,
                fastPath: false,
                molecule: { name: 'N_atom', atoms: [{ symbol: 'N', x: 0, y: 0, z: 0 }] },
                octopusMolecule: 'N_atom',
            });
        }

        const fastPathEnv = String(import.meta.env.VITE_OCTOPUS_INTERACTIVE_FASTPATH ?? 'false');
        if (config.engineMode === 'octopus3D' && fastPathEnv.toLowerCase() !== 'false') {
            (payload as Record<string, unknown>).fastPath = true;
        }

        const query = encodeURIComponent(JSON.stringify(payload));
        const eventSource = new EventSource(`${API_BASE}/api/physics/stream?config=${query}`);
        eventSourceRef.current = eventSource;

        let resultReceived = false;
        const connectTimeoutMs = Math.max(5000, Number(import.meta.env.VITE_SOLVE_CONNECT_TIMEOUT_MS || 20000));
        const stallTimeoutMs = Math.max(10000, Number(import.meta.env.VITE_SOLVE_STALL_TIMEOUT_MS || 5 * 60 * 1000));
        const hardTimeoutMs = Math.max(0, Number(import.meta.env.VITE_SOLVE_HARD_TIMEOUT_MS || 25 * 60 * 1000));

        let sawProgress = false;
        let connectTimeoutId: number | null = null;
        let stallTimeoutId: number | null = null;
        let hardTimeoutId: number | null = null;

        const doCleanup = () => {
            if (connectTimeoutId !== null) { window.clearTimeout(connectTimeoutId); connectTimeoutId = null; }
            if (stallTimeoutId !== null) { window.clearTimeout(stallTimeoutId); stallTimeoutId = null; }
            if (hardTimeoutId !== null) { window.clearTimeout(hardTimeoutId); hardTimeoutId = null; }
        };

        const armStallTimeout = () => {
            if (stallTimeoutId !== null) window.clearTimeout(stallTimeoutId);
            stallTimeoutId = window.setTimeout(() => {
                if (resultReceived) return;
                setStatus('ERROR');
                setLogs(prev => [...prev, `✗ No progress update for ${Math.round(stallTimeoutMs / 1000)}s (stream stalled)`]);
                eventSource.close();
                setIsComputing(false);
                setWorkflowStage('review');
                setLastRunSeconds((Date.now() - runStartTs) / 1000);
                runInProgressRef.current = false;
                clearTimers();
                doCleanup();
            }, stallTimeoutMs);
        };

        const markProgress = () => {
            sawProgress = true;
            if (connectTimeoutId !== null) { window.clearTimeout(connectTimeoutId); connectTimeoutId = null; }
            armStallTimeout();
        };

        connectTimeoutId = window.setTimeout(() => {
            if (resultReceived || sawProgress) return;
            setStatus('ERROR');
            setLogs(prev => [...prev, `✗ Timeout: no stream activity within ${Math.round(connectTimeoutMs / 1000)}s`]);
            eventSource.close();
            setIsComputing(false);
            setWorkflowStage('review');
            setLastRunSeconds((Date.now() - runStartTs) / 1000);
            runInProgressRef.current = false;
            clearTimers();
            doCleanup();
        }, connectTimeoutMs);

        if (hardTimeoutMs > 0) {
            hardTimeoutId = window.setTimeout(() => {
                if (resultReceived) return;
                setStatus('ERROR');
                setLogs(prev => [...prev, `✗ Timeout: exceeded hard limit ${Math.round(hardTimeoutMs / 1000)}s`]);
                eventSource.close();
                setIsComputing(false);
                setLastRunSeconds((Date.now() - runStartTs) / 1000);
                runInProgressRef.current = false;
                clearTimers();
                doCleanup();
            }, hardTimeoutMs);
        }

        eventSource.onopen = () => markProgress();

        eventSource.addEventListener('log', (e: Event) => {
            try {
                const msg = JSON.parse((e as MessageEvent).data);
                markProgress();
                setLogs(prev => prev[prev.length - 1] === msg ? prev : [...prev, msg]);
            } catch { markProgress(); }
        });

        eventSource.addEventListener('heartbeat', () => markProgress());

        eventSource.addEventListener('result', (e: Event) => {
            resultReceived = true;
            try {
                const resData = JSON.parse((e as MessageEvent).data);
                setStatus('SUCCESS');
                setResult(resData);
                const historyKey = resData.molecular?.calcMode || resData.problemType || 'gs';
                setResultHistory(prev => ({ ...prev, [historyKey]: resData }));
                setLogs(prev => [
                    ...prev,
                    `✓ Computation complete via ${resData.engine || 'Octopus-v16'}.`,
                    `  Results: ${resData.eigenvalues?.length || 0} eigenvalues found.`,
                ]);
            } catch {
                setStatus('ERROR');
                setLogs(prev => [...prev, '✗ Error processing final result']);
            } finally {
                doCleanup();
                eventSource.close();
                if (eventSourceRef.current === eventSource) eventSourceRef.current = null;
                clearTimers();
                setIsComputing(false);
                setWorkflowStage('review');
                setLastRunSeconds((Date.now() - runStartTs) / 1000);
                runInProgressRef.current = false;
            }
        });

        eventSource.addEventListener('pipeline_error', (e: Event) => {
            doCleanup();
            setStatus('ERROR');
            try {
                const errData = JSON.parse((e as MessageEvent).data);
                setLogs(prev => [...prev, `✗ Pipeline Error: ${errData.message || 'Unknown error'}`]);
            } catch {
                setLogs(prev => [...prev, '✗ Pipeline Error: (unparseable)']);
            }
            eventSource.close();
            if (eventSourceRef.current === eventSource) eventSourceRef.current = null;
            clearTimers();
            setIsComputing(false);
            setWorkflowStage('review');
            setLastRunSeconds((Date.now() - runStartTs) / 1000);
            runInProgressRef.current = false;
        });

        eventSource.onerror = () => {
            if (resultReceived || eventSource.readyState === EventSource.CLOSED) {
                doCleanup();
                eventSource.close();
                if (eventSourceRef.current === eventSource) eventSourceRef.current = null;
                return;
            }
            doCleanup();
            setStatus('ERROR');
            setLogs(prev => [...prev, '✗ Streaming Error: Connection lost or server crashed']);
            eventSource.close();
            if (eventSourceRef.current === eventSource) eventSourceRef.current = null;
            clearTimers();
            setIsComputing(false);
            setWorkflowStage('review');
            setLastRunSeconds((Date.now() - runStartTs) / 1000);
            runInProgressRef.current = false;
        };
    }, [buildOctopusConfig, clearTimers]);

    return {
        isComputing, status, logs, result, resultHistory,
        runStartAt, elapsedSeconds, lastRunSeconds,
        workflowStage, activeRunLabel,
        run, requestPause,
        setLogs, setResult, setResultHistory,
        setIsComputing, setStatus, setWorkflowStage,
        setRunStartAt, setElapsedSeconds, setLastRunSeconds,
        setActiveRunLabel,
        runInProgressRef,
    } as const;
}
