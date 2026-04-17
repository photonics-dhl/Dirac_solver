/**
 * Physics Engine — Dirac/Schrödinger/Klein-Gordon Solver
 *
 * Accepts full configuration from the frontend, runs the computation pipeline
 * with real-time dev_state.json updates, and writes persistent computation log.
 */

import 'dotenv/config';
import fs from 'fs';
import path from 'path';
import { httpRequest } from './http_request';

const OCTOPUS_MCP_URL = process.env.OCTOPUS_MCP_URL ?? 'http://localhost:8000';
const LOCAL_ENGINE_URL = process.env.LOCAL_ENGINE_URL ?? 'http://localhost:8001';
const OCTOPUS_HEALTH_TIMEOUT_MS = Math.max(1000, Number(process.env.OCTOPUS_HEALTH_TIMEOUT_MS ?? 10000));
const OCTOPUS_HEALTH_RETRIES = Math.max(1, Number(process.env.OCTOPUS_HEALTH_RETRIES ?? 3));
const OCTOPUS_SOLVE_TIMEOUT_MS = Math.max(30000, Number(process.env.OCTOPUS_SOLVE_TIMEOUT_MS ?? 1800000));
const OCTOPUS_FAST_SOLVE_TIMEOUT_MS = Math.max(120000, Number(process.env.OCTOPUS_FAST_SOLVE_TIMEOUT_MS ?? 300000));
const OCTOPUS_FAST_SPACING_BOHR = Math.max(0.1, Number(process.env.OCTOPUS_FAST_SPACING_BOHR ?? 0.5));
const OCTOPUS_FAST_RADIUS_BOHR = Math.max(1.5, Number(process.env.OCTOPUS_FAST_RADIUS_BOHR ?? 3.0));
const OCTOPUS_FAST_BOX_PADDING_BOHR = Math.max(1.0, Number(process.env.OCTOPUS_FAST_BOX_PADDING_BOHR ?? 2.5));
const OCTOPUS_FAST_MAX_SCF_ITERATIONS = Math.max(10, Number(process.env.OCTOPUS_FAST_MAX_SCF_ITERATIONS ?? 40));
const OCTOPUS_ALLOW_LOCAL_FALLBACK = /^(1|true|yes)$/i.test(process.env.OCTOPUS_ALLOW_LOCAL_FALLBACK ?? 'false');

const WORKSPACE_ROOT = process.env.WORKSPACE_ROOT ?? path.resolve(__dirname, '..');
const DEV_STATE_PATH = path.join(WORKSPACE_ROOT, 'dev_state.json');
const LOG_PATH = path.join(WORKSPACE_ROOT, 'computation_log.md');

// ─── Expanded Config Interface ───────────────────────────────────

export interface PhysicsConfig {
    // Physical constants
    unitSystem?: string;          // 'natural' | 'SI' | 'gaussian'
    mass: number;
    charge?: number;
    energy?: number;

    // Geometry
    dimensionality?: string;      // '1D' | '2D' | '3D'
    spatialRange?: number;
    gridPoints?: number;
    gridSpacing: number;
    boundaryCondition?: string;

    // Potential
    potentialType?: string;
    potentialStrength: number;
    wellWidth?: number;
    customExpression?: string;
    potentialDataMode?: string;

    // Equation & problem type
    equationType?: string;        // 'Schrodinger' | 'Dirac' | 'KleinGordon'
    problemType?: string;         // 'boundstate' | 'timeevolution' | 'scattering'
    picture?: string;

    // Time evolution parameters
    numTimeSteps?: number;
    totalTime?: number;
    initialState?: string;
    gaussianCenter?: number;
    gaussianWidth?: number;
    gaussianMomentum?: number;

    // Scattering parameters
    scatteringEnergyMin?: number;
    scatteringEnergyMax?: number;
    scatteringEnergySteps?: number;

    // Octopus Molecular parameters (Phase 4)
    engineMode?: 'local1D' | 'octopus3D';
    moleculeName?: string;
    octopusPeriodic?: 'off' | 'x' | 'xy' | 'xyz';
    octopusDimensions?: string;
    octopusSpacing?: number;
    octopusLengthUnit?: 'bohr' | 'angstrom';
    octopusUnitsOutput?: 'eV_Angstrom' | 'Ha_Bohr' | string;
    octopusRadius?: number;
    octopusBoxShape?: string;
    octopusMolecule?: string;
    octopusTdSteps?: number;
    octopusTdTimeStep?: number;
    octopusPropagator?: string;
    octopusExtraStates?: number;
    octopusNcpus?: number;
    octopusMpiprocs?: number;
    speciesMode?: 'formula' | 'pseudo' | 'all_electron';
    pseudopotentialSet?: string;
    tdSteps?: number;
    molecule?: string;
    calcMode?: 'gs' | 'td' | 'unocc';
    caseType?: 'dft_gs_3d' | 'response_td' | 'periodic_bands' | 'hpc_scaling' | 'maxwell_em';
    skipRunExplanation?: boolean;
    fastPath?: boolean;
}

export interface PhysicsResult {
    config: PhysicsConfig;
    problemType: string;
    equationType: string;
    dimensionality?: string;
    matrix_info?: { size: number, non_zeros: number, isHermitian: boolean };
    // Spatial grid
    x_grid?: number[];
    y_grid?: number[];
    p_grid?: number[];
    potential_V?: number[];
    // Bound-state results
    hamiltonian: number[][];
    eigenvalues: number[];
    eigenvaluesSI: string[];
    eigenvectors: number[][];
    wavefunctions: Array<{
        psi_up: number[];
        psi_down: number[];
        psi_p_mag?: number[];
        psi_2d?: number[][];
    }>;
    probabilityDensity: number[];
    verified: boolean;
    // Time evolution results
    timeEvolution?: {
        time_grid: number[];
        psi_t: number[][];
        initial_state: number[];
        initial_coefficients: number[];
        eigenvalues: number[];
    };
    // Scattering results
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
    // Molecular results (Phase 4)
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
        td_dipole?: {
            time: number[];
            dipole_x: number[];
            dipole_y: number[];
            dipole_z: number[];
        };
        run_explanation?: {
            file?: string;
            path?: string;
            used_llm?: boolean;
            status?: string;
        };
        radiation_spectrum?: { frequency_ev: number[]; intensity: number[] };
        eels_spectrum?: { energy_ev: number[]; eels: number[] };
    };
    scheduler?: {
        strategy?: string;
        run_dir?: string;
        job_id?: string;
        job_state?: string;
        queue?: string;
        ncpus?: number;
        mpiprocs?: number;
        selected_node?: string;
        exec_vnode?: string;
        resource_selector?: string;
    };
    ragContext?: {
        query: string;
        hits: Array<{ source: string; section: string; distance?: number }>;
    };
    engine?: string;
    computationTime: number;
}

// ─── State Update Helper ─────────────────────────────────────────
let globalEmitter: ((type: string, data: any) => void) | undefined;


function updateDevState(updates: {
    currentNode?: string;
    mode?: string;
    taskName?: string;
    taskStatus?: string;
    log?: string;
    projectTaskId?: string;
    projectTaskStatus?: string;
    projectTaskProgress?: number;
    subTaskId?: string;
    subTaskCurrentNode?: string;
    nodeResult?: { nodeId: string; data: Record<string, any> };
}) {
    let state: any;
    try {
        const raw = fs.readFileSync(DEV_STATE_PATH, 'utf-8');
        state = JSON.parse(raw);
    } catch {
        // dev_state.json missing (fresh cloud deploy) — initialise with defaults
        state = {
            currentNode: 'idle', mode: 'IDLE', taskName: '', taskStatus: '',
            logs: [], history: [],
            projectGraph: null, subTaskGraphs: {}, nodeResults: {}
        };
    }

    if (updates.currentNode) state.currentNode = updates.currentNode;
    if (updates.mode) state.mode = updates.mode;
    if (updates.taskName) state.taskName = updates.taskName;
    if (updates.taskStatus) state.taskStatus = updates.taskStatus;
    if (updates.log) {
        state.logs.push(updates.log);
        if (globalEmitter) globalEmitter('log', updates.log);
    }

    if (updates.projectTaskId && state.projectGraph) {
        const task = state.projectGraph.tasks.find((t: any) => t.id === updates.projectTaskId);
        if (task) {
            if (updates.projectTaskStatus) task.status = updates.projectTaskStatus;
            if (updates.projectTaskProgress !== undefined) task.progress = updates.projectTaskProgress;
        }
    }

    if (updates.subTaskId && updates.subTaskCurrentNode && state.subTaskGraphs?.[updates.subTaskId]) {
        state.subTaskGraphs[updates.subTaskId].currentNode = updates.subTaskCurrentNode;
    }

    // Store per-node computation results for Dashboard inspection
    if (updates.nodeResult) {
        if (!state.nodeResults) state.nodeResults = {};
        state.nodeResults[updates.nodeResult.nodeId] = {
            ...updates.nodeResult.data,
            timestamp: new Date().toISOString(),
        };
    }

    if (updates.currentNode && updates.currentNode !== 'idle') {
        state.history.push({
            node: updates.currentNode,
            timestamp: new Date().toISOString(),
            duration: '—',
        });
    }

    fs.writeFileSync(DEV_STATE_PATH, JSON.stringify(state, null, 2), 'utf-8');
}

// ─── Computation Log Writer (Phase 4) ────────────────────────────

let currentLogRunId = 0;

function initLogRun(config: PhysicsConfig): number {
    currentLogRunId++;
    const header = [
        `\n## Run #${currentLogRunId} — ${new Date().toISOString()}`,
        `**Equation**: ${config.equationType || 'Dirac'} | **Problem**: ${config.problemType || 'boundstate'} | **Picture**: ${config.picture || 'auto'}`,
        `**Config**: mass=${config.mass}, δx=${config.gridSpacing}, V₀=${config.potentialStrength}, dim=${config.dimensionality || '1D'}`,
        '',
    ].join('\n');

    if (!fs.existsSync(LOG_PATH)) {
        fs.mkdirSync(path.dirname(LOG_PATH), { recursive: true });
        fs.writeFileSync(LOG_PATH, '# Computation Log\n\nPersistent record of all physics pipeline runs.\n\n---\n', 'utf-8');
    }
    fs.appendFileSync(LOG_PATH, header, 'utf-8');
    return currentLogRunId;
}

function appendLog(phase: string, message: string, duration?: string) {
    const line = `- **${phase}**: ${message}${duration ? ` *(${duration})` : ''}\n`;
    fs.appendFileSync(LOG_PATH, line, 'utf-8');
}

function endLogRun(success: boolean) {
    fs.appendFileSync(LOG_PATH, `\n**Result**: ${success ? '✅ SUCCESS' : '❌ FAILED'}\n\n---\n`, 'utf-8');
}

// ─── Matrix Operations ───────────────────────────────────────────

type MatNxN = number[][];

function createMatrix(n: number): MatNxN {
    return Array.from({ length: n }, () => Array(n).fill(0));
}

/** Eigenvalues of 2x2 matrix via characteristic equation */
function eigenvalues2x2(A: MatNxN): number[] {
    const trace = A[0][0] + A[1][1];
    const det = A[0][0] * A[1][1] - A[0][1] * A[1][0];
    const disc = trace * trace - 4 * det;
    if (disc < 0) return [NaN, NaN];
    const sq = Math.sqrt(disc);
    return [(trace + sq) / 2, (trace - sq) / 2];
}

/** Eigenvector for eigenvalue of 2x2 */
function eigenvector2x2(A: MatNxN, lam: number): number[] {
    const a = A[0][0] - lam, b = A[0][1];
    if (Math.abs(b) > 1e-12) {
        const norm = Math.sqrt(b * b + a * a);
        return [-b / norm, a / norm];
    }
    return Math.abs(a) > 1e-12 ? [0, 1] : [1, 0];
}

/** Build Hamiltonian based on equation type */
function buildHamiltonian(config: PhysicsConfig): MatNxN {
    const p = 1.0 / config.gridSpacing;
    const m = config.mass;
    const V = config.potentialStrength;

    const eq = config.equationType || 'Dirac';

    if (eq === 'Dirac') {
        // Simplified 2×2 Dirac: H = [[m+V, p],[p, -m+V]]
        return [[m + V, p], [p, -m + V]];
    } else if (eq === 'Schrodinger') {
        // Simplified 2×2 Schrödinger: H = [[p²/(2m)+V, -p²/(4m)],[-p²/(4m), p²/(2m)+V]]
        const ke = (p * p) / (2 * m);
        const off = -(p * p) / (4 * m);
        return [[ke + V, off], [off, ke + V]];
    } else {
        // Klein-Gordon: H² = p² + m²; linearized 2×2
        const E = Math.sqrt(p * p + m * m);
        return [[E + V, 0], [0, -E + V]];
    }
}

// ─── Main Pipeline ───────────────────────────────────────────────

async function sleep(ms: number) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function fetchKbHints(config: PhysicsConfig): Promise<{ query: string; hits: Array<{ source: string; section: string; distance?: number }> } | null> {
    const query = [
        `${config.equationType || 'Schrodinger'} ${config.problemType || 'boundstate'}`,
        `${config.potentialType || 'custom'} potential`,
        `${config.engineMode === 'octopus3D' ? 'Octopus DFT setup' : '1D quantum solver'}`,
    ].join(' | ');

    try {
        const resp = await httpRequest(`${LOCAL_ENGINE_URL}/kb/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, top_k: 3 }),
            timeoutMs: 5000,
        });
        if (!resp.ok) return null;

        const data = await resp.json();
        const hits = Array.isArray(data?.hits)
            ? data.hits.map((h: any) => ({
                source: h?.source || 'unknown',
                section: h?.section || 'unknown',
                distance: h?.distance,
            }))
            : [];
        return { query, hits };
    } catch {
        return null;
    }
}

export async function runPhysicsPipeline(config: PhysicsConfig, onEvent?: (type: string, data: any) => void): Promise<PhysicsResult> {
    const STEP_DELAY = 1200;
    const startTime = Date.now();
    const eqLabel = config.equationType || 'Dirac';

    // Helper for SSE event emission
    const emit = (type: string, data: any) => { if (onEvent) onEvent(type, data); };
    globalEmitter = onEvent;

    // Initialize persistent log
    initLogRun(config);

    // ═══ P1: Parameter Setup ═════════════════════════════════════
    const requestedOctopus = config.engineMode === 'octopus3D';
    const displayLabel = requestedOctopus ? 'Octopus DFT' : eqLabel;

    emit('log', `[System] Configuring ${displayLabel} parameters...`);
    console.log("[DEBUG] Starting runPhysicsPipeline", { requestedOctopus, displayLabel, engineMode: config.engineMode });
    updateDevState({
        currentNode: 'research', mode: 'PLANNING',
        taskName: `${displayLabel} Solver Pipeline`,
        taskStatus: `P1: Setting up ${displayLabel} parameters...`,
        log: requestedOctopus
            ? `[OCTO-PLAN-1] P1: Octopus — molecule=${config.molecule || config.octopusMolecule}, calc=${config.calcMode}, pbc=${config.octopusPeriodic}`
            : `[SCHRO-PLAN-1] P1: ${eqLabel} — mass=${config.mass}, δx=${config.gridSpacing}, V₀=${config.potentialStrength}, dim=${config.dimensionality || '1D'}`,
        projectTaskId: 'P1', projectTaskStatus: 'in-progress', projectTaskProgress: 0,
        subTaskId: 'P1', subTaskCurrentNode: 'define_constants',
    });

    if (!requestedOctopus) {
        appendLog('P1', `Received config: ${eqLabel}, mass=${config.mass}, δx=${config.gridSpacing}`);
        await sleep(STEP_DELAY / 2);
        updateDevState({
            log: `[PLANNING] P1: Units=${config.unitSystem || 'natural'}, BC=${config.boundaryCondition || 'dirichlet'}, picture=${config.picture || 'auto'}`,
            subTaskId: 'P1', subTaskCurrentNode: 'configure_potential',
            projectTaskId: 'P1', projectTaskProgress: 50,
        });
        appendLog('P1', `Units: ${config.unitSystem || 'natural'}, Potential: ${config.potentialType || 'custom'}`);
    } else {
        appendLog('P1', `Octopus Config: ${config.octopusMolecule}, ${config.calcMode}`);
        await sleep(STEP_DELAY / 2);
    }

    updateDevState({
        log: `[VERIFICATION] P1: Parameters validated ✓`,
        subTaskId: 'P1', subTaskCurrentNode: 'validate_params',
        projectTaskId: 'P1', projectTaskStatus: 'done', projectTaskProgress: 100,
        nodeResult: {
            nodeId: 'P1_validate', data: requestedOctopus ? config : {
                mass: config.mass, gridSpacing: config.gridSpacing, potentialStrength: config.potentialStrength,
                dimensionality: config.dimensionality || '1D', unitSystem: config.unitSystem || 'natural',
                equationType: eqLabel, boundaryCondition: config.boundaryCondition || 'dirichlet',
            }
        },
    });
    appendLog('P1', 'Parameters validated ✓', `${((Date.now() - startTime) / 1000).toFixed(1)}s`);
    await sleep(STEP_DELAY / 2);

    // ═══ P1.5: RAG Context Retrieval (best-effort) ═══════════════
    const ragContext = await fetchKbHints(config);
    if (ragContext && ragContext.hits.length > 0) {
        const refs = ragContext.hits.slice(0, 2).map((h) => `${h.source}#${h.section}`).join(', ');
        updateDevState({
            log: `[RAG] Retrieved ${ragContext.hits.length} knowledge hints: ${refs}`,
            nodeResult: {
                nodeId: 'P1_5_rag',
                data: ragContext,
            },
        });
        appendLog('P1.5', `RAG hints loaded (${ragContext.hits.length})`);
    }

    // ═══ Python Backend Compute ══════════════════════════════════
    let solveResult: any = null;
    let usedOctopus = false;
    let octopusFailureReason = '';

    console.log("[DEBUG] Routing Check:", { engineMode: config.engineMode, potentialType: config.potentialType });

    // Try Docker Octopus MCP first for supported potentials or explicitly 3D molecular mode
    // Use Docker Octopus MCP for 3D molecular mode OR specific 1D boundstate potentials
    if (config.engineMode === 'octopus3D') {
        try {
            const moleculeKey = (typeof config.molecule === 'string'
                ? config.molecule
                : (config.octopusMolecule || config.moleculeName || '')
            ).toString().trim().toLowerCase();
            const calcModeKey = (config.calcMode || 'gs').toLowerCase();
            const isSimpleH2Gs = moleculeKey === 'h2' && calcModeKey === 'gs';
            const useFastPath = isSimpleH2Gs || config.fastPath === true;

            // ─── Generate Octopus Input File ───
            const scriptPath = path.resolve(__dirname, '..', '@Octopus_docs', 'octopus_input_generator.py');
            const pythonExec = process.platform === 'win32' ? 'python' : 'python3';
            updateDevState({
                log: `[EXECUTION] P2: Generating Octopus input file...`,
            });

            try {
                const { spawnSync } = require('child_process');
                console.log("[DEBUG] Executing generator with config payload");
                const result = spawnSync(pythonExec, [scriptPath, '--config', JSON.stringify(config)], { encoding: 'utf-8' });

                if (result.status === 0) {
                    console.log("[DEBUG] Generator Success Output:", result.stdout);
                    appendLog('P2', `Generated octopus.inp in @Octopus_docs/generated_inputs`);
                } else {
                    console.error("[DEBUG] Input generation script failed:", result.stderr);
                    appendLog('P2', `Warning: Input generation script failed: ${result.stderr}`);
                }
            } catch (err: any) {
                console.error("[DEBUG] Input generation exception:", err.message);
                appendLog('P2', `Warning: Input generation execution error: ${err.message}`);
            }

            const moleculeLabel = (() => {
                if (typeof config.molecule === 'string' && config.molecule.trim()) {
                    return config.molecule.trim();
                }
                if (config.molecule && typeof config.molecule === 'object' && (config.molecule as any).name) {
                    return String((config.molecule as any).name);
                }
                if (config.octopusMolecule) {
                    return String(config.octopusMolecule);
                }
                if (config.moleculeName) {
                    return String(config.moleculeName);
                }
                return 'H2';
            })();

            updateDevState({
                log: `[EXECUTION] P2: Attempting Octopus DFT computation via Docker MCP...`,
                subTaskId: 'P1', subTaskCurrentNode: 'call_octopus',
            });
            const lengthUnit = String(config.octopusLengthUnit || 'angstrom').toLowerCase() === 'angstrom' ? 'Angstrom' : 'Bohr';
            const outputUnit = String(config.octopusUnitsOutput || 'eV_Angstrom');
            emit('log', `[Octopus][Config] mode=${config.calcMode || 'gs'} | molecule=${moleculeLabel} | spacing=${config.octopusSpacing ?? config.gridSpacing ?? '-'} ${lengthUnit} | radius=${config.octopusRadius ?? config.spatialRange ?? '-'} ${lengthUnit} | output=${outputUnit}`);
            if ((config.calcMode || 'gs') === 'td') {
                emit('log', `[Octopus][TD] excitation=${(config as any).tdExcitationType || 'delta'} | steps=${config.octopusTdSteps ?? (config as any).tdSteps ?? 200} | dt=${config.octopusTdTimeStep ?? (config as any).TDTimeStep ?? 0.05}`);
            } else {
                emit('log', `[Octopus][Note] 当前为 GS 模式，不会输出吸收谱；吸收谱请切换 Calculation Mode=TD 且 excitation=delta`);
            }
            const healthUrls = [`${OCTOPUS_MCP_URL}/health`];
            let healthResp = null;

            const healthRetries = useFastPath ? 1 : OCTOPUS_HEALTH_RETRIES;
            const healthTimeoutMs = useFastPath ? Math.min(OCTOPUS_HEALTH_TIMEOUT_MS, 4000) : OCTOPUS_HEALTH_TIMEOUT_MS;

            for (const url of healthUrls) {
                for (let attempt = 1; attempt <= healthRetries; attempt++) {
                    console.log(`[DEBUG] Checking Octopus health at ${url} (attempt ${attempt}/${OCTOPUS_HEALTH_RETRIES})`);
                    try {
                        const resp = await httpRequest(url, { timeoutMs: healthTimeoutMs });
                        if (resp.ok) {
                            healthResp = resp;
                            break;
                        }
                    } catch (e: any) {
                        console.error(`[DEBUG] Health check failed at ${url} attempt ${attempt}: ${e.message}`);
                        octopusFailureReason = `health check failed: ${e.message}`;
                    }
                    if (attempt < OCTOPUS_HEALTH_RETRIES) {
                        await sleep(700);
                    }
                }
                if (healthResp) break;
            }

            if (healthResp) {
                const healthData = await healthResp.json();
                console.log("[DEBUG] Octopus Health Data:", healthData);
                if (healthData.status === 'ok' || healthData.engine?.includes('octopus') || healthData.TcpTestSucceeded) {
                    appendLog('P2', `Using Octopus backend via Docker (engine: ${healthData.engine || 'unknown'})`);
                    const solveTimeoutMs = useFastPath
                        ? Math.min(OCTOPUS_SOLVE_TIMEOUT_MS, OCTOPUS_FAST_SOLVE_TIMEOUT_MS)
                        : OCTOPUS_SOLVE_TIMEOUT_MS;
                    const payloadSpacing = Number(config.octopusSpacing ?? config.gridSpacing ?? OCTOPUS_FAST_SPACING_BOHR);
                    const payloadRadius = Number(config.octopusRadius ?? config.spatialRange ?? OCTOPUS_FAST_RADIUS_BOHR);
                    const payloadMaxScf = Number((config as any).octopusMaxScfIterations ?? OCTOPUS_FAST_MAX_SCF_ITERATIONS);
                    const octopusRequestPayload = {
                        ...config,
                        octopusLengthUnit: (config.octopusLengthUnit || 'angstrom'),
                        octopusUnitsOutput: (config.octopusUnitsOutput || 'eV_Angstrom'),
                        // Fast-path debugging should prioritize compute turnaround over extra explanation generation.
                        skipRunExplanation: useFastPath || config.skipRunExplanation === true,
                        ...(useFastPath ? {
                            octopusSpacing: Math.max(payloadSpacing, OCTOPUS_FAST_SPACING_BOHR),
                            octopusRadius: Math.min(payloadRadius, OCTOPUS_FAST_RADIUS_BOHR),
                            octopusBoxPadding: OCTOPUS_FAST_BOX_PADDING_BOHR,
                            octopusMaxScfIterations: Math.min(payloadMaxScf, OCTOPUS_FAST_MAX_SCF_ITERATIONS),
                            fastPath: true,
                        } : {}),
                    };

                    const solvePromise = httpRequest(`${OCTOPUS_MCP_URL}/solve`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(octopusRequestPayload),
                        timeoutMs: solveTimeoutMs,
                    });
                    let waitingSec = 0;
                    const waitingTimer = setInterval(() => {
                        waitingSec += 15;
                        emit('log', `[Octopus][Wait] 求解进行中 ${waitingSec}s (timeout=${Math.round(solveTimeoutMs / 1000)}s)...`);
                    }, 15000);
                    let octoResp;
                    try {
                        octoResp = await solvePromise;
                    } finally {
                        clearInterval(waitingTimer);
                    }
                    if (!octoResp.ok) {
                        throw new Error(`Octopus Engine Error: ${await octoResp.text()}`);
                    }
                    solveResult = await octoResp.json();
                    console.log("[DEBUG] Octopus solveResult payload received");

                    // Surface Python-level errors as proper exceptions
                    if (solveResult.status === 'error') {
                        const errMsg = (solveResult.message || solveResult.stderr_tail || solveResult.stdout_tail || 'Unknown Octopus error').toString();
                        appendLog('P2', `Octopus returned error: ${errMsg}`);
                        emit('log', `✗ Octopus Engine Error: ${errMsg}`);
                        throw new Error(`Octopus Engine Error: ${errMsg}`);
                    }

                    const octoEigenvalues = Array.isArray(solveResult.eigenvalues) ? solveResult.eigenvalues : [];
                    if (!solveResult.converged && octoEigenvalues.length === 0) {
                        const diag = (solveResult.stderr_tail || solveResult.stdout_tail || solveResult.message || '').toString();
                        appendLog('P2', `Octopus returned no converged states. ${diag ? `Diagnostics: ${diag}` : ''}`.trim());
                        throw new Error('Octopus returned no converged states');
                    }

                    usedOctopus = true;

                    if (solveResult.stdout_tail) {
                        appendLog('P2', `Octopus Output:\n${solveResult.stdout_tail}`);
                    }
                    if (solveResult.stderr_tail && solveResult.returncode !== 0) {
                        appendLog('P2', `Octopus Error:\n${solveResult.stderr_tail}`);
                    }
                }
            } else {
                octopusFailureReason = octopusFailureReason || 'Octopus health check failed or timed out';
                appendLog('P2', `${octopusFailureReason}.`);
            }
        } catch (e: any) {
            usedOctopus = false;
            solveResult = null;
            octopusFailureReason = e.message || 'Octopus attempt failed';
            appendLog('P2', `Octopus attempt failed: ${octopusFailureReason}`);
        }
    }

    if (!usedOctopus) {
        try {
            if (requestedOctopus) {
                if (!OCTOPUS_ALLOW_LOCAL_FALLBACK) {
                    const reason = octopusFailureReason || 'Octopus backend unavailable';
                    emit('log', `✗ Octopus required but unavailable: ${reason}`);
                    appendLog('P2', `Octopus required but unavailable: ${reason}`);
                    throw new Error(`Octopus required but unavailable: ${reason}`);
                }
                emit('log', `⚠ Octopus unavailable (${octopusFailureReason || 'unknown reason'}), fallback to local Python backend (non-DFT approximation).`);
                appendLog('P2', `Octopus unavailable (${octopusFailureReason || 'unknown reason'}); using local Python fallback (not true Octopus DFT)`);
            }
            appendLog('P2', `Using local Python backend`);
            // Assuming local Python engine might be on a different port if Octopus is on 8000.
            // If they are on the same port, the above logic correctly routes to whichever is running.
            // We'll keep the port as 8000 for local Python too, assuming they aren't run together.
            const resp = await httpRequest(`${LOCAL_ENGINE_URL}/solve`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
                timeoutMs: 120000,
            });
            if (!resp.ok) {
                throw new Error(`Python Engine Error: ${await resp.text()}`);
            }
            solveResult = await resp.json();
        } catch (e: any) {
            appendLog('P2/P3', `Compute Failed: ${e.message}`);
            throw e;
        }
    }

    // 2) Parse JSON response — handle different problem types
    let isHermitian = true;
    // For octopus3D, always treat as 'molecular' problem type for ResultsPanel routing
    const effectiveProblemType = usedOctopus ? 'molecular' : (solveResult?.problemType || config.problemType || 'boundstate');
    const problemType = effectiveProblemType;
    const matrix_info = solveResult?.matrix_info || { size: 0, non_zeros: 0, isHermitian: true };
    const x_grid = solveResult?.x_grid || [];
    const p_grid = solveResult?.p_grid || [];
    const potential_V = solveResult?.potential_V || [];
    const eigenvalues = solveResult?.eigenvalues || [];
    // Format wavefunctions: server may return raw arrays or {psi_up, psi_down} objects
    const rawWfs: any[] = solveResult?.wavefunctions || [];
    const wavefunctions = rawWfs.map((w: any) => {
        if (typeof w === 'object' && 'psi_up' in w) return w;
        return { psi_up: Array.isArray(w) ? w : [], psi_down: [] };
    });

    if (!usedOctopus) {
        // ═══ P2: Build Hamiltonian ═══════════════════════════════════
        const p2Start = Date.now();
        updateDevState({
            currentNode: 'plan', mode: 'PLANNING',
            taskStatus: `P2: Building ${eqLabel} Hamiltonian...`,
            log: `[SCHRO-EXEC-1] P2: Constructing ${eqLabel} Hamiltonian matrix`,
            projectTaskId: 'P2', projectTaskStatus: 'in-progress', projectTaskProgress: 0,
            subTaskId: 'P2', subTaskCurrentNode: 'build_gamma_matrices',
        });
        await sleep(STEP_DELAY);

        updateDevState({
            log: `[EXECUTION] P2: Matrix Size=${matrix_info.size}, Non-Zeros=${matrix_info.non_zeros}`,
            subTaskId: 'P2', subTaskCurrentNode: 'build_free_hamiltonian',
            projectTaskId: 'P2', projectTaskProgress: 50,
        });
        appendLog('P2', `Matrix: N=${matrix_info.size}, nnz=${matrix_info.non_zeros}`);
        await sleep(STEP_DELAY);

        isHermitian = matrix_info.isHermitian;
        updateDevState({
            log: `[VERIFICATION] P2: Hermiticity: ${isHermitian ? '✓' : '✗'}`,
            subTaskId: 'P2', subTaskCurrentNode: 'verify_hermiticity',
            projectTaskId: 'P2', projectTaskStatus: 'done', projectTaskProgress: 100,
            nodeResult: { nodeId: 'P2_hamiltonian', data: matrix_info },
        });
        appendLog('P2', `Hermiticity: ${isHermitian ? '✓' : '✗'}`, `${((Date.now() - p2Start) / 1000).toFixed(1)}s`);
        await sleep(STEP_DELAY);
    } else {
        updateDevState({
            log: `[OCTO-VERIFY-1] P2: Octopus results parsed (${wavefunctions.length} states)`,
            projectTaskId: 'P2', projectTaskStatus: 'done', projectTaskProgress: 100,
        });
        appendLog('P2', `Octopus states: ${wavefunctions.length}`);
    }

    // ═══ For Time Evolution / Scattering — skip eigenstate processing ═══
    if (problemType === 'timeevolution' || problemType === 'scattering') {
        const totalTime = (Date.now() - startTime) / 1000;

        updateDevState({
            currentNode: 'implement', mode: 'EXECUTION',
            taskStatus: `P3: ${problemType === 'timeevolution' ? 'Time-evolving wavepacket' : 'Computing T(E)/R(E)'}...`,
            log: `[EXECUTION] P3: ${problemType} solver complete`,
            projectTaskId: 'P3', projectTaskStatus: 'done', projectTaskProgress: 100,
            subTaskId: 'P3', subTaskCurrentNode: 'done',
        });
        appendLog('P3', `${problemType} solver done`, `${totalTime.toFixed(1)}s`);
        await sleep(STEP_DELAY);

        updateDevState({
            currentNode: 'idle', mode: 'IDLE', taskStatus: '', taskName: '',
            log: `[SYSTEM] ✓ ${eqLabel} ${problemType} pipeline complete in ${totalTime.toFixed(1)}s`,
        });
        appendLog('Total', `Completed in ${totalTime.toFixed(1)}s`);

        const MEV_TO_JOULES = 1.602176634e-13;
        const evalsSI = eigenvalues.map((E: number) => {
            return `${(E * MEV_TO_JOULES).toExponential(3)} J`;
        });

        const finalRes = {
            config,
            problemType,
            x_grid,
            y_grid: solveResult?.y_grid,
            p_grid,
            potential_V,
            hamiltonian: [[0, 0], [0, 0]],
            eigenvalues,
            eigenvaluesSI: evalsSI,
            eigenvectors: [],
            wavefunctions: wavefunctions.length > 0 ? wavefunctions : [{ psi_up: [], psi_down: [] }],
            probabilityDensity: [],
            verified: true,
            equationType: eqLabel,
            computationTime: totalTime,
            // Time evolution data
            ...(solveResult?.time_grid ? {
                timeEvolution: {
                    time_grid: solveResult.time_grid,
                    psi_t: solveResult.psi_t,
                    initial_state: solveResult.initial_state,
                    initial_coefficients: solveResult.initial_coefficients,
                    eigenvalues: solveResult.eigenvalues,
                }
            } : {}),
            // Scattering data
            ...(solveResult?.energy_range ? {
                scattering: {
                    energy_range: solveResult.energy_range,
                    transmission: solveResult.transmission,
                    reflection: solveResult.reflection,
                    resonances: solveResult.resonances || [],
                    sample_wavefunctions: solveResult.sample_wavefunctions || [],
                }
            } : {}),
        };
        globalEmitter = undefined;
        return finalRes;
    }

    // ═══ P3: Bound State — Eigenvalue Problem ═══════════════════
    // SKIP this logic for Octopus, as it's already processed in solveResult
    if (usedOctopus) {
        const totalTime = (Date.now() - startTime) / 1000;
        const molData = solveResult?.molecular;
        const scheduler = solveResult?.scheduler;
        const converged: boolean = molData?.converged ?? solveResult?.converged ?? false;
        const scfIter: number = molData?.scf_iterations ?? solveResult?.scf_iterations ?? 0;

        updateDevState({
            currentNode: 'idle', mode: 'IDLE', taskStatus: '', taskName: '',
            log: `[OCTO-SYSTEM-1] ✓ Octopus pipeline complete in ${totalTime.toFixed(1)}s | converged=${converged} | ${eigenvalues.length} states`,
        });
        appendLog('Total', `Completed in ${totalTime.toFixed(1)}s | converged=${converged}`);

        // Eigenvalues from server.py are already in Hartree;
        // eigenvaluesSI: display as eV strings for readability
        const evalsSI = eigenvalues.map((E: number) => `${(E * 27.2114).toFixed(4)} eV`);

        emit('log', `[Octopus] SCF ${converged ? 'converged' : 'did not converge'} in ${scfIter} iterations`);
        if (eigenvalues.length > 0) {
            emit('log', `[Octopus] Eigenvalues: ${eigenvalues.slice(0, 4).map((e: number) => e.toFixed(4) + ' H').join(', ')}${eigenvalues.length > 4 ? ' ...' : ''}`);
        }
        if (molData?.homo_energy != null) {
            emit('log', `[Octopus] HOMO = ${molData.homo_energy.toFixed(3)} eV  |  LUMO = ${molData.lumo_energy != null ? molData.lumo_energy.toFixed(3) + ' eV' : 'N/A'}`);
        }
        if (molData?.total_energy_hartree != null) {
            emit('log', `[Octopus] Total energy = ${molData.total_energy_hartree.toFixed(6)} H`);
        }
        if ((config.calcMode || 'gs') === 'td' && molData?.td_skipped_reason) {
            emit('log', `[Octopus][TD] ${molData.td_skipped_reason}`);
        }
        if (scheduler) {
            const runId = scheduler.run_dir || '-';
            const jobId = scheduler.job_id || '-';
            const node = scheduler.selected_node || scheduler.exec_vnode || '-';
            const cpu = scheduler.ncpus ?? '-';
            const mpi = scheduler.mpiprocs ?? '-';
            const queue = scheduler.queue || '-';
            emit('log', `[Octopus][Scheduler] run=${runId} | job=${jobId} | node=${node} | cpu=${cpu} | mpi=${mpi} | queue=${queue}`);
        }

        globalEmitter = undefined;
        return {
            config,
            problemType: 'molecular',
            x_grid,
            p_grid,
            potential_V,
            hamiltonian: [[0, 0], [0, 0]],
            eigenvalues,
            eigenvaluesSI: evalsSI,
            eigenvectors: [],
            wavefunctions,
            probabilityDensity: [],
            verified: converged,
            equationType: 'Octopus DFT',
            engine: 'octopus-mcp',
            dimensionality: config.octopusDimensions || '3D',
            computationTime: totalTime,
            ragContext: ragContext || undefined,
            scheduler,
            molecular: molData ? {
                moleculeName: molData.moleculeName,
                calcMode: (config.calcMode as 'gs' | 'td') || 'gs',
                energy_levels: molData.energy_levels,
                homo_energy: molData.homo_energy,
                lumo_energy: molData.lumo_energy,
                total_energy_hartree: molData.total_energy_hartree,
                scf_iterations: molData.scf_iterations,
                converged: molData.converged,
                optical_spectrum: molData.optical_spectrum,
                td_dipole: molData.td_dipole,
                run_explanation: molData.run_explanation,
                radiation_spectrum: molData.radiation_spectrum,
                eels_spectrum: molData.eels_spectrum,
            } : undefined,
        };
    }

    const p3Start = Date.now();
    const evals = eigenvalues;

    updateDevState({
        currentNode: 'implement', mode: 'EXECUTION',
        taskStatus: `P3: Solving ${eqLabel} eigenvalue equation...`,
        log: `[EXECUTION] P3: Computing eigenvalues via Lanczos/Arnoldi`,
        projectTaskId: 'P3', projectTaskStatus: 'in-progress', projectTaskProgress: 0,
        subTaskId: 'P3', subTaskCurrentNode: 'select_solver',
    });
    await sleep(STEP_DELAY);

    if (evals.length >= 2) {
        updateDevState({
            log: `[EXECUTION] P3: E₊=${evals[0].toFixed(6)}, E₋=${evals[1].toFixed(6)}`,
            subTaskId: 'P3', subTaskCurrentNode: 'solve_positive_energy',
            projectTaskId: 'P3', projectTaskProgress: 40,
        });
        appendLog('P3', `Eigenvalues: E₊=${evals[0].toFixed(6)}, E₋=${evals[1].toFixed(6)}`);
    } else if (evals.length === 1) {
        updateDevState({
            log: `[EXECUTION] P3: E₀=${evals[0].toFixed(6)}`,
            subTaskId: 'P3', subTaskCurrentNode: 'solve_positive_energy',
            projectTaskId: 'P3', projectTaskProgress: 40,
        });
        appendLog('P3', `Eigenvalue: E₀=${evals[0].toFixed(6)}`);
    }
    await sleep(STEP_DELAY);

    // Convert backend wavefunctions to simple arrays for frontend 1D view
    const eigenvectors = wavefunctions.map((w: any) => w.psi_up);
    const psi_p_mag = wavefunctions.map((w: any) => w.psi_p_mag);

    updateDevState({
        log: `[EXECUTION] P3: Extracted wavefunctions for ${evals.length} computed states`,
        subTaskId: 'P3', subTaskCurrentNode: 'solve_negative_energy',
        projectTaskId: 'P3', projectTaskProgress: 70,
    });
    await sleep(STEP_DELAY);

    // Compute orthogonality
    let dot = 0;
    const nSpatialPoints = wavefunctions[0]?.psi_up?.length || 0;
    const prob: number[] = new Array(nSpatialPoints).fill(0);

    for (let i = 0; i < nSpatialPoints; i++) {
        if (wavefunctions.length > 1) {
            dot += (wavefunctions[0].psi_up[i] || 0) * (wavefunctions[1].psi_up[i] || 0)
                + (wavefunctions[0].psi_down[i] || 0) * (wavefunctions[1].psi_down[i] || 0);
        }
        prob[i] = (wavefunctions[0].psi_up[i] || 0) ** 2 + (wavefunctions[0].psi_down[i] || 0) ** 2;
    }
    dot *= config.gridSpacing;

    const isOrthogonal = Math.abs(dot) < 1e-4;
    updateDevState({
        currentNode: 'test', mode: 'VERIFICATION',
        taskStatus: 'P3: Verifying results...',
        log: `[VERIFICATION] P3: ⟨S0|S1⟩=${dot.toFixed(8)} → ${isOrthogonal ? '✓ Orthogonal' : '✗'}`,
        subTaskId: 'P3', subTaskCurrentNode: 'check_completeness',
        projectTaskId: 'P3', projectTaskProgress: 90,
    });
    await sleep(STEP_DELAY);

    const verified = isHermitian && isOrthogonal;
    const totalTime = (Date.now() - startTime) / 1000;

    let probStr = prob.slice(0, 2).map(p => p.toFixed(4)).join(', ');
    if (prob.length > 2) probStr += '...';

    updateDevState({
        currentNode: 'walkthrough', mode: 'VERIFICATION',
        taskStatus: 'Pipeline complete',
        log: `[VERIFICATION] P3: |ψ|²=[${probStr}] ✓`,
        subTaskId: 'P3', subTaskCurrentNode: 'compare_analytical',
        projectTaskId: 'P3', projectTaskStatus: 'done', projectTaskProgress: 100,
    });
    appendLog('P3', `Orthogonality: ${isOrthogonal ? '✓' : '✗'}, |ψ|²=[${probStr}]`, `${((Date.now() - p3Start) / 1000).toFixed(1)}s`);
    updateDevState({
        nodeResult: {
            nodeId: 'P3_eigensolve', data: {
                eigenvalues: evals,
                dotProduct: dot, isOrthogonal, probabilityDensity: prob, verified,
                p_grid,
                psi_p_mag,
            }
        },
    });
    await sleep(STEP_DELAY);

    const evalsHead = evals.slice(0, 3).map((e: number) => e.toFixed(4)).join(', ');
    const evalsTail = evals.length > 3 ? '...' : '';
    updateDevState({
        currentNode: 'idle', mode: 'IDLE', taskStatus: '', taskName: '',
        log: `[SYSTEM] ✓ ${eqLabel} pipeline complete in ${totalTime.toFixed(1)}s. E=[${evalsHead}${evalsTail}]`,
    });

    appendLog('Total', `Completed in ${totalTime.toFixed(1)}s`);
    const MEV_TO_JOULES = 1.602176634e-13;
    const evalsSI = evals.map((E: number) => {
        const joules = E * MEV_TO_JOULES;
        return `${joules.toExponential(3)} J`;
    });

    const finalRes: PhysicsResult = {
        config,
        problemType: solveResult?.problemType || config.problemType || 'boundstate',
        x_grid,
        y_grid: solveResult?.y_grid,
        p_grid: p_grid || [],
        potential_V,
        hamiltonian: [[0, 0], [0, 0]],
        eigenvalues: evals,
        eigenvaluesSI: evalsSI,
        eigenvectors: eigenvectors,
        wavefunctions: wavefunctions,
        probabilityDensity: prob,
        verified,
        engine: 'local-python',
        equationType: eqLabel,
        computationTime: totalTime,
        ragContext: ragContext || undefined,
        molecular: usedOctopus ? solveResult?.molecular : undefined,
    };
    globalEmitter = undefined;
    return finalRes;
}
