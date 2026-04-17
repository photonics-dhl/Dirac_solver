import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import fs from 'fs';
import path from 'path';
import { spawn, spawnSync } from 'child_process';
import { randomUUID } from 'crypto';
import { httpRequest } from './http_request';

const app = express();
app.use(cors());
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));

const DEV_STATE_PATH = path.resolve(__dirname, '..', 'dev_state.json');
const HARNESS_REPORTS_DIR = path.resolve(__dirname, '..', 'docs', 'harness_reports');
const DIRAC_SYNC_STATE_PATH = path.resolve(__dirname, '..', 'state', 'dirac_solver_progress_sync.json');
const DIRAC_BRIDGE_STATE_PATH = path.resolve(__dirname, '..', 'state', 'copilot_openclaw_bridge.json');
const STRICT_FEISHU_AUTO_SOURCE = String(process.env.DIRAC_STRICT_FEISHU_AUTO_SOURCE || '1').trim() !== '0';

function looksLikeAutoOrchestrationTask(task: string): boolean {
    const compact = String(task || '').toLowerCase();
    if (!compact) return false;
    return compact.includes('/auto')
        || compact.includes('自动调试')
        || compact.includes('自动执行')
        || compact.includes('workflow=fullchain')
        || compact.includes('mode=autonomous');
}

function updateBridgeFromDispatchResult(payload: {
    taskId: string;
    dispatchStatus: string;
    humanStatus: string;
    failureReason: string;
    workflowRoute: string;
    workflowState: string;
    workflowEvent: string;
    workflowNextRoute: string;
    consistencyToken: string;
    updatedAt: string;
}) {
    try {
        const bridgeRead = readJsonFileSafe(DIRAC_BRIDGE_STATE_PATH);
        const bridge = (bridgeRead.data && typeof bridgeRead.data === 'object') ? bridgeRead.data : {};
        const executionBus = (bridge.execution_bus && typeof bridge.execution_bus === 'object') ? bridge.execution_bus : {};
        executionBus.last_worker_seen_at = payload.updatedAt || new Date().toISOString();
        executionBus.last_task = {
            task_id: payload.taskId,
            dispatch_status: payload.dispatchStatus || 'unknown',
            human_status: payload.humanStatus || '',
            failure_reason: payload.failureReason || '',
            consistency_token: payload.consistencyToken || '',
            workflow: {
                route: payload.workflowRoute || 'L0',
                state: payload.workflowState || 'UNKNOWN',
                event: payload.workflowEvent || '',
                next_route: payload.workflowNextRoute || payload.workflowRoute || 'L0',
            },
            updated_at: payload.updatedAt || new Date().toISOString(),
        };
        bridge.execution_bus = executionBus;
        bridge.updated_at = payload.updatedAt || new Date().toISOString();
        bridge.handshake_status = 'synced_with_copilot';
        fs.writeFileSync(DIRAC_BRIDGE_STATE_PATH, JSON.stringify(bridge, null, 2), 'utf-8');
    } catch (error: any) {
        console.warn('[Automation] bridge refresh skipped:', error?.message || error);
    }
}

type JsonReadSafeResult = {
    data: any;
    parseError: string;
    mtimeMs: number;
};

function readJsonFileSafe(filePath: string): JsonReadSafeResult {
    try {
        if (!fs.existsSync(filePath)) {
            return { data: null, parseError: '', mtimeMs: 0 };
        }
        const stat = fs.statSync(filePath);
        const raw = fs.readFileSync(filePath, 'utf-8');
        return {
            data: raw ? JSON.parse(raw) : null,
            parseError: '',
            mtimeMs: Number(stat.mtimeMs || 0),
        };
    } catch (error: any) {
        let mtimeMs = 0;
        try {
            mtimeMs = Number(fs.statSync(filePath).mtimeMs || 0);
        } catch {
            mtimeMs = 0;
        }
        return {
            data: null,
            parseError: String(error?.message || error || 'unknown_parse_error'),
            mtimeMs,
        };
    }
}

type ExplainJobStatus = 'queued' | 'running' | 'success' | 'error' | 'timeout';
type ExplainJob = {
    id: string;
    status: ExplainJobStatus;
    createdAt: number;
    updatedAt: number;
    file: string;
    error?: string;
};

const explainJobs = new Map<string, ExplainJob>();
const EXPLAIN_JOB_TTL_MS = Math.max(60_000, Number(process.env.ZCHAT_EXPLAIN_JOB_TTL_MS ?? 30 * 60 * 1000));

function cleanupExplainJobs() {
    const now = Date.now();
    for (const [id, job] of explainJobs.entries()) {
        if (now - job.updatedAt > EXPLAIN_JOB_TTL_MS) {
            explainJobs.delete(id);
        }
    }
}

function createExplainJob(file: string): ExplainJob {
    cleanupExplainJobs();
    const job: ExplainJob = {
        id: randomUUID(),
        status: 'queued',
        createdAt: Date.now(),
        updatedAt: Date.now(),
        file,
    };
    explainJobs.set(job.id, job);
    return job;
}

function updateExplainJob(id: string, patch: Partial<ExplainJob>) {
    const prev = explainJobs.get(id);
    if (!prev) return;
    explainJobs.set(id, {
        ...prev,
        ...patch,
        updatedAt: Date.now(),
    });
}

// ─── Dirac Solver API ────────────────────────────────────────────

app.post('/api/simulate', async (req, res) => {
    try {
        const { dimensionality, gridSpacing, potentialType } = req.body;

        const [{ quantumSolverApp }, { HumanMessage }] = await Promise.all([
            import('./langgraph_agent'),
            import('@langchain/core/messages'),
        ]);

        console.log(`[API] Received compute task: ${dimensionality}, spacing: ${gridSpacing}`);

        const initialState = {
            messages: [new HumanMessage(`I want to simulate an electron in ${dimensionality} ${potentialType} with very fine grid spacing of ${gridSpacing}`)],
        };

        // Invoke the Langgraph State Machine
        const finalState = await quantumSolverApp.invoke(initialState);

        console.log(`[API] Final config: ${JSON.stringify(finalState.config)}`);
        console.log(`[API] Final status: ${finalState.computeStatus}`);

        res.json({
            status: finalState.computeStatus,
            config: finalState.config,
            errorLog: finalState.errorLog,
            finalGridSpacing: finalState.config?.gridSpacing ?? gridSpacing,
            finalDimensionality: finalState.config?.dimensionality ?? dimensionality
        });

    } catch (error: any) {
        console.error("[API Error]", error);
        res.status(500).json({ error: error.message });
    }
});

// ─── Development Flow Dashboard API ──────────────────────────────

app.get('/api/dev-state', (_req, res) => {
    try {
        const raw = fs.readFileSync(DEV_STATE_PATH, 'utf-8');
        res.json(JSON.parse(raw));
    } catch (error: any) {
        if (error?.code === 'ENOENT') {
            return res.json({
                currentNode: 'INIT',
                mode: 'PLANNING',
                taskName: 'No active task',
                taskStatus: 'idle',
                history: [],
                logs: ['dev_state.json not found; returning default state'],
                graphDefinition: { nodes: [], edges: [] },
                userFeedback: { instruction: '', targetNode: '', timestamp: '' },
            });
        }
        console.error("[Dev State] Read error:", error.message);
        res.status(500).json({ error: 'Failed to read dev_state.json' });
    }
});

app.post('/api/dev-state/feedback', (req, res) => {
    try {
        const { instruction, targetNode } = req.body;
        const raw = fs.readFileSync(DEV_STATE_PATH, 'utf-8');
        const state = JSON.parse(raw);

        state.userFeedback = {
            instruction: instruction || '',
            targetNode: targetNode || '',
            timestamp: new Date().toISOString(),
        };

        fs.writeFileSync(DEV_STATE_PATH, JSON.stringify(state, null, 2), 'utf-8');
        console.log(`[Dev State] Feedback set: "${instruction}" → node: ${targetNode || '(none)'}`);
        res.json({ success: true, userFeedback: state.userFeedback });
    } catch (error: any) {
        console.error("[Dev State] Write error:", error.message);
        res.status(500).json({ error: 'Failed to update dev_state.json' });
    }
});

// ─── Physics Engine Pipeline API ─────────────────────────────────

import { runPhysicsPipeline } from './physics_engine';

app.post('/api/physics/run', async (req, res) => {
    try {
        const config = req.body;
        console.log(`[Physics] Starting pipeline for config: ${JSON.stringify(config)}`);

        const result = await runPhysicsPipeline(config);

        const eLabels = result.eigenvalues.slice(0, 3).map((e: number) => e.toFixed(4)).join(', ');
        const eTail = result.eigenvalues.length > 3 ? '...' : '';
        console.log(`[Physics] Pipeline complete. E=[${eLabels}${eTail}]`);
        res.json(result);
    } catch (error: any) {
        console.error("[Physics] Pipeline error:", error.message);
        res.status(500).json({ error: error.message });
    }
});

app.get('/api/physics/stream', async (req, res) => {
    try {
        const configStr = req.query.config as string;
        if (!configStr) {
            return res.status(400).json({ error: "Missing config query param" });
        }
        const config = JSON.parse(configStr);

        console.log(`[Physics Stream] Starting pipeline for config: ${config.potentialType}`);

        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive');
        res.flushHeaders();

        let closed = false;
        const closeStream = () => {
            if (closed) return;
            closed = true;
            try { res.end(); } catch (_) {}
        };

        const heartbeat = setInterval(() => {
            if (closed || res.writableEnded || req.destroyed) {
                return;
            }
            try {
                res.write(`event: heartbeat\n`);
                res.write(`data: ${Date.now()}\n\n`);
            } catch {
                closeStream();
            }
        }, 5000);

        req.on('close', () => {
            clearInterval(heartbeat);
            closeStream();
        });

        const onEvent = (eventName: string, data: any) => {
            if (closed || res.writableEnded || req.destroyed) return;
            res.write(`event: ${eventName}\n`);
            res.write(`data: ${JSON.stringify(data)}\n\n`);
        };

        const result = await runPhysicsPipeline(config, onEvent);

        const eLabels = result.eigenvalues.slice(0, 3).map((e: number) => e.toFixed(4)).join(', ');
        const eTail = result.eigenvalues.length > 3 ? '...' : '';
        console.log(`[Physics Stream] Pipeline complete. E=[${eLabels}${eTail}]`);

        onEvent('result', result);
        clearInterval(heartbeat);
        closeStream();
    } catch (error: any) {
        console.error("[Physics Stream] Pipeline error:", error.message);
        try {
            res.write(`event: pipeline_error\n`);
            res.write(`data: ${JSON.stringify({ message: error.message })}\n\n`);
        } finally {
            res.end();
        }
    }
});

app.post('/api/physics/explain', (req, res) => {
    try {
        const resultData = req.body;
        const asyncPreferred = ((req.get('x-explain-async') || '').trim() === '1');

        const zchatApiKey = (process.env.ZCHAT_API_KEY || '').trim();
        const zchatBaseUrl = (process.env.ZCHAT_BASE_URL || '').trim();
        const placeholderKeys = new Set(['your_key_here', 'sk-your_key_here', 'replace_me', 'changeme', 'none', 'null']);
        if (!zchatApiKey || placeholderKeys.has(zchatApiKey.toLowerCase())) {
            return res.status(400).json({ error: 'ZCHAT_API_KEY is missing or placeholder. Please set a valid key in .env.' });
        }
        if (!zchatBaseUrl) {
            return res.status(400).json({ error: 'ZCHAT_BASE_URL is missing in .env.' });
        }

        const file = asyncPreferred
            ? `physics_explanation_${Date.now()}_${Math.floor(Math.random() * 100000)}.md`
            : 'physics_explanation.md';
        const job = createExplainJob(file);

        console.log(`[Physics] Queued async explanation job: ${job.id}`);

        // Detect Python executable: Windows uses .venv\Scripts\python, Linux uses python3
        const isWin = process.platform === 'win32';
        const pyExec = isWin ? path.join('.venv', 'Scripts', 'python') : 'python3';

        const depCheck = spawnSync(pyExec, ['-c', 'import openai, dotenv; print("PY_DEPS_OK")'], {
            encoding: 'utf-8',
            timeout: 15000,
        });
        if (depCheck.status !== 0 || !(depCheck.stdout || '').includes('PY_DEPS_OK')) {
            return res.status(500).json({
                error: `Python deps missing for explain route. Ensure 'openai' and 'python-dotenv' are installed in ${pyExec}. Details: ${(depCheck.stderr || depCheck.stdout || `exit=${depCheck.status}`).toString().trim()}`
            });
        }

        const pythonProcess = spawn(pyExec, ['generate_explanation.py']);
        const explainTimeoutMs = Math.max(30000, Number(process.env.ZCHAT_EXPLAIN_TIMEOUT_MS ?? 240000));

        let output = '';
        let errOutput = '';
        let finished = false;

        if (!asyncPreferred) {
            const placeholderPath = path.join(process.cwd(), file);
            try {
                fs.writeFileSync(
                    placeholderPath,
                    `# AI Physics Explanation\n\nExplanation generation is running in background...\n\nJob ID: ${job.id}\nCreated: ${new Date().toISOString()}\n`,
                    'utf8'
                );
            } catch {
            }
        }

        updateExplainJob(job.id, { status: 'running' });

        const timeoutHandle = setTimeout(() => {
            try { pythonProcess.kill('SIGKILL'); } catch { }
            finished = true;
            updateExplainJob(job.id, {
                status: 'timeout',
                error: `Explanation generation timed out after ${Math.round(explainTimeoutMs / 1000)}s`,
            });
        }, explainTimeoutMs);

        pythonProcess.stdout.on('data', (data) => {
            output += data.toString();
        });

        pythonProcess.stderr.on('data', (data) => {
            errOutput += data.toString();
            console.error(data.toString());
        });

        pythonProcess.on('error', (err) => {
            console.error("Failed to start python process:", err);
            clearTimeout(timeoutHandle);
            updateExplainJob(job.id, {
                status: 'error',
                error: `Failed to start explanation script: ${err.message}`,
            });
        });

        pythonProcess.on('close', (code) => {
            if (finished) return;
            finished = true;
            clearTimeout(timeoutHandle);
            if (code !== 0) {
                console.error(`[Physics] Python Explanation script exited with code ${code}`);
                updateExplainJob(job.id, {
                    status: 'error',
                    error: errOutput || output || `Process exited with error code ${code}.`,
                });
                return;
            }
            updateExplainJob(job.id, { status: 'success' });
        });

        const payload = {
            result: resultData,
            output_file: path.join(process.cwd(), file),
        };
        pythonProcess.stdin.write(JSON.stringify(payload));
        pythonProcess.stdin.end();

        if (asyncPreferred) {
            return res.status(202).json({
                status: 'accepted',
                jobId: job.id,
                file,
                pollUrl: `/api/physics/explain/jobs/${job.id}`,
            });
        }

        return res.status(200).json({
            status: 'success',
            mode: 'background',
            jobId: job.id,
            file,
            pollUrl: `/api/physics/explain/jobs/${job.id}`,
        });

    } catch (e: any) {
        console.error("Explanation generation error:", e);
        res.status(500).json({ error: e.message });
    }
});

app.get('/api/physics/explain/jobs/:jobId', (req, res) => {
    const jobId = req.params.jobId;
    const job = explainJobs.get(jobId);
    if (!job) {
        return res.status(404).json({ error: `Explanation job not found: ${jobId}` });
    }
    res.json({
        jobId: job.id,
        status: job.status,
        file: job.file,
        error: job.error,
        createdAt: job.createdAt,
        updatedAt: job.updatedAt,
    });
});

app.get('/api/physics/explanation/raw', (req, res) => {
    try {
        const fileParam = (req.query.file as string | undefined)?.trim();
        const safeFile = fileParam && path.basename(fileParam) === fileParam ? fileParam : 'physics_explanation.md';
        const mdPath = path.join(process.cwd(), safeFile);
        if (!fs.existsSync(mdPath)) {
            return res.status(404).send('# Explanation not found\nPlease generate one first.');
        }
        const fileContent = fs.readFileSync(mdPath, 'utf8');
        res.type('text/markdown');
        res.send(fileContent);
    } catch (e: any) {
        res.status(500).send(`# Error reading file\n\n${e.message}`);
    }
});

app.get('/api/physics/explanation', (_req, res) => {
    const fileParam = (_req.query.file as string | undefined)?.trim();
    const safeFile = fileParam && path.basename(fileParam) === fileParam ? fileParam : 'physics_explanation.md';
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AI Physics Explanation - Dirac Solver</title>
    <style>
      body { background:#09090b; color:#e4e4e7; font-family: Arial, sans-serif; margin:0; padding:24px; }
      .container { max-width:960px; margin:0 auto; }
      pre { white-space:pre-wrap; word-break:break-word; background:#111113; border:1px solid #27272a; border-radius:8px; padding:16px; }
    </style>
</head>
<body>
  <div class="container">
    <h2>AI Physics Explanation</h2>
    <pre id="content">Loading...</pre>
  </div>
  <script>
        const file = ${JSON.stringify(safeFile)};
        const contentEl = document.getElementById('content');
        let pollTimer = null;

        function stopPolling() {
            if (pollTimer) {
                clearInterval(pollTimer);
                pollTimer = null;
            }
        }

        async function loadExplanation() {
            const res = await fetch('/api/physics/explanation/raw?file=' + encodeURIComponent(file));
            if (!res.ok) throw new Error('Not found');
            return await res.text();
        }

        async function pollJob(jobId) {
            try {
                const res = await fetch('/api/physics/explain/jobs/' + encodeURIComponent(jobId));
                if (!res.ok) return;
                const data = await res.json();

                if (data.status === 'success') {
                    const finalText = await loadExplanation();
                    contentEl.textContent = finalText;
                    stopPolling();
                    return;
                }

                if (data.status === 'error' || data.status === 'timeout') {
                    contentEl.textContent = (contentEl.textContent || '') + '\n\n[Background job failed] ' + (data.error || data.status);
                    stopPolling();
                    return;
                }
            } catch {
            }
        }

        loadExplanation()
            .then(text => {
                contentEl.textContent = text;
                const match = text.match(/Job ID:\s*([a-f0-9-]{36})/i);
                if (match && match[1]) {
                    pollTimer = setInterval(() => pollJob(match[1]), 2500);
                }
            })
            .catch(() => {
                contentEl.textContent = 'Computation explanation not found. Please generate one first.';
            });
  </script>
</body>
</html>`;
    res.type('text/html');
    res.send(html);
});

// ─── Visualization Endpoint (matplotlib for 1D/2D, VisIt for 3D) ─────────────
import { isVisItAvailable, writeVisItScript, renderWithVisIt, dockerPathToHost } from './visit_renderer';

const OCTOPUS_OUTPUT_DIR = process.env.OCTOPUS_OUTPUT_DIR
    ?? path.join(process.cwd(), '@Octopus_docs', 'output');
const MPL_SCRIPT = path.join(process.cwd(), 'src', 'render_mpl.py');

/** Render a 1D/2D slice using matplotlib (fast, reliable). */
function renderWithMatplotlib(
    inputPath: string, plotType: string, outputPng: string,
    isoValue?: number, colormap?: string, slicePos?: number, sliceAxis?: string
): Promise<{ success: boolean; pngBase64?: string; durationMs: number; reason?: string }> {
    return new Promise((resolve) => {
        const start = Date.now();
        const preferredCondaPy = process.platform === 'win32'
            ? path.join(process.env.USERPROFILE ?? '', 'miniconda3', 'envs', 'ai_agent', 'python.exe')
            : path.join(process.env.HOME ?? '', 'miniconda3', 'envs', 'ai_agent', 'bin', 'python');
        const pyExe = process.env.MPL_PYTHON
            ?? process.env.PYTHON_BIN
            ?? (fs.existsSync(preferredCondaPy) ? preferredCondaPy : (process.platform === 'win32' ? 'python' : 'python3'));
        const extraArgs: string[] = [];
        // Always push both slots so colormap stays at argv[5] regardless of isoValue
        extraArgs.push(isoValue !== undefined ? String(isoValue) : '');
        if (colormap) extraArgs.push(colormap); else extraArgs.push('');
        // argv[6]: slice_pos (Bohr) — always push so argv[7] is reliable
        extraArgs.push(slicePos !== undefined ? String(slicePos) : '');
        // argv[7]: slice_axis ('x'|'y'|'z')
        if (sliceAxis) extraArgs.push(sliceAxis);
        const proc = spawn(pyExe, [MPL_SCRIPT, inputPath, plotType, outputPng, ...extraArgs], {
            cwd: process.cwd(),
            shell: false,
            windowsHide: process.platform === 'win32',
        });
        let stderr = '';
        proc.stderr?.on('data', (d: Buffer) => { stderr += d.toString(); });
        proc.on('error', (err) => {
            resolve({ success: false, durationMs: Date.now() - start, reason: `Python spawn error: ${err.message}` });
        });
        proc.on('close', (code) => {
            const durationMs = Date.now() - start;
            if (code === 0 && fs.existsSync(outputPng)) {
                const pngBase64 = fs.readFileSync(outputPng).toString('base64');
                resolve({ success: true, pngBase64, durationMs });
            } else {
                resolve({ success: false, durationMs, reason: stderr || `mpl exited with code ${code}` });
            }
        });
    });
}

app.post('/api/physics/visualize', async (req, res) => {
    try {
        const { plotType = 'wavefunction_1d', inputFile, isoValue, colormap, wfStateIndex, slicePos, sliceAxis } = req.body as {
            plotType?: 'wavefunction_1d' | 'density_2d' | 'density_3d';
            inputFile?: string;
            isoValue?: number;
            colormap?: string;
            wfStateIndex?: number;
            slicePos?: number;
            sliceAxis?: string;
        };

        const stateIdx = wfStateIndex ?? 1;
        const wfSliceFile = `wf-st${String(stateIdx).padStart(5, '0')}.y=0,z=0`;
        const wfCubeFile  = `wf-st${String(stateIdx).padStart(5, '0')}.cube`;

        // Resolve input file path (docker path → host path if needed)
        const resolveInput = (filePath: string) =>
            filePath.startsWith('/') ? dockerPathToHost(filePath) : filePath;

        // ── Wavefunction 1D (axis_x slice file) ────────────────────────────
        if (plotType === 'wavefunction_1d') {
            const inputPath = inputFile
                ? resolveInput(inputFile)
                : path.join(OCTOPUS_OUTPUT_DIR, wfSliceFile);

            // Prefer 2D cube render if cube file exists
            const cubeFile = path.join(OCTOPUS_OUTPUT_DIR, wfCubeFile);
            if (!inputFile && fs.existsSync(cubeFile)) {
                const outputPng = path.join(OCTOPUS_OUTPUT_DIR, `render_wf_state${stateIdx}_2d.png`);
                console.log(`[mpl] Rendering wavefunction_2d_cube for state ${stateIdx}`);
                const result = await renderWithMatplotlib(cubeFile, 'wavefunction_2d_cube', outputPng);
                if (result.success && result.pngBase64) {
                    return res.json({ status: 'ok', pngBase64: result.pngBase64, durationMs: result.durationMs, source: 'cube_2d' });
                }
                // fallback to 1D slice below
            }

            if (!fs.existsSync(inputPath)) {
                return res.json({ status: 'error', reason: `Data file not found: ${path.basename(inputPath)}. Run an Octopus GS calculation first.` });
            }
            const outputPng = path.join(OCTOPUS_OUTPUT_DIR, `render_wavefunction_1d_st${stateIdx}.png`);
            console.log(`[mpl] Rendering wavefunction_1d: ${path.basename(inputPath)}`);
            const result = await renderWithMatplotlib(inputPath, 'wavefunction_1d', outputPng);
            if (result.success && result.pngBase64) {
                return res.json({ status: 'ok', pngBase64: result.pngBase64, durationMs: result.durationMs, source: 'axis_x' });
            }
            return res.json({ status: 'error', reason: result.reason });
        }

        // ── Density 2D — true heatmap from cube file ───────────────────────
        if (plotType === 'density_2d') {
            const cubeFile = inputFile ? resolveInput(inputFile) : path.join(OCTOPUS_OUTPUT_DIR, 'density.cube');
            const outputPng = path.join(OCTOPUS_OUTPUT_DIR, 'render_density_2d.png');

            if (fs.existsSync(cubeFile)) {
                console.log(`[mpl] Rendering density_2d_cube from: ${path.basename(cubeFile)} slicePos=${slicePos} sliceAxis=${sliceAxis}`);
                const result = await renderWithMatplotlib(
                    cubeFile, 'density_2d_cube', outputPng,
                    undefined, colormap ?? 'plasma', slicePos, sliceAxis ?? 'z'
                );
                if (result.success && result.pngBase64) {
                    return res.json({ status: 'ok', pngBase64: result.pngBase64, durationMs: result.durationMs, source: 'cube_2d' });
                }
                console.warn(`[mpl] Cube render failed: ${result.reason} — falling back to 1D slice`);
            }

            // Fallback: legacy 1D line slice
            const sliceFile = path.join(OCTOPUS_OUTPUT_DIR, 'density.y=0,z=0');
            if (!fs.existsSync(sliceFile)) {
                return res.json({ status: 'error', reason: 'density.cube and density.y=0,z=0 not found. Run an Octopus GS calculation first.' });
            }
            const result = await renderWithMatplotlib(sliceFile, 'density_2d', outputPng);
            if (result.success && result.pngBase64) {
                return res.json({ status: 'ok', pngBase64: result.pngBase64, durationMs: result.durationMs, source: 'axis_x_fallback' });
            }
            return res.json({ status: 'error', reason: result.reason });
        }

        // ── Density 3D — isosurface panels from cube file (VisIt preferred, mpl fallback) ─
        if (plotType === 'density_3d') {
            const cubeFile = inputFile ? resolveInput(inputFile) : path.join(OCTOPUS_OUTPUT_DIR, 'density.cube');
            const outputPng = path.join(OCTOPUS_OUTPUT_DIR, 'render_density_3d.png');

            if (!fs.existsSync(cubeFile)) {
                return res.json({
                    status: 'not_available',
                    reason: 'density.cube not found. Run a 3D GS Octopus calculation first (the cube file requires OutputFormat = cube + axis_x in the input).'
                });
            }

            // 1. Try VisIt
            if (isVisItAvailable()) {
                console.log(`[VisIt] Rendering density_3d from: ${path.basename(cubeFile)}`);
                const scriptPath = writeVisItScript({
                    plotType: "density_3d",
                    inputHostPath: cubeFile,
                    outputPngHostPath: outputPng,
                    isoValue: isoValue ?? 0.15
                });
                const vResult = await renderWithVisIt({
                    scriptPath,
                    outputPngPath: outputPng,
                    visitExePath: process.env.VISIT_EXE
                });
                if (vResult.success && vResult.pngBase64) {
                    return res.json({ status: 'ok', pngBase64: vResult.pngBase64, durationMs: vResult.durationMs, source: 'visit_3d' });
                }
                console.warn(`[VisIt] Failed: ${vResult.reason}. Falling back to Matplotlib.`);
            }

            // 2. Fallback to Matplotlib
            const isoArg = isoValue ?? 0.15;
            const cmapArg = colormap ?? 'hot';
            console.log(`[mpl] Rendering density_3d_iso from: ${path.basename(cubeFile)} iso=${isoArg} slicePos=${slicePos} sliceAxis=${sliceAxis}`);
            const result = await renderWithMatplotlib(cubeFile, 'density_3d_iso', outputPng, isoArg, cmapArg, slicePos, sliceAxis ?? 'z');
            if (result.success && result.pngBase64) {
                return res.json({ status: 'ok', pngBase64: result.pngBase64, durationMs: result.durationMs, source: 'cube_3d' });
            }
            return res.json({ status: 'error', reason: result.reason });
        }

        return res.json({ status: 'error', reason: `Unknown plotType: ${plotType}` });

    } catch (e: any) {
        console.error("[Visualize] Error:", e.message);
        res.status(500).json({ status: 'error', reason: e.message });
    }
});

// ─── MCP Health Proxy (allows browser to check MCP health via same-origin) ──
app.get('/api/mcp/health', async (_req, res) => {
    const mcpUrl = process.env.OCTOPUS_MCP_URL ?? 'http://localhost:8000';
    const timeoutMs = Math.max(1000, Number(process.env.OCTOPUS_HEALTH_TIMEOUT_MS ?? 10000));
    try {
        const response = await httpRequest(`${mcpUrl}/health`, { timeoutMs });
        const data = await response.json();
        if (!response.ok) {
            return res.status(response.status).json(data);
        }
        res.json(data);
    } catch {
        res.status(503).json({ status: 'error', engine: 'unavailable' });
    }
});

// ─── Harness Proxy (single-case benchmark entry) ─────────────────
app.post('/api/harness/run-case', async (req, res) => {
    const harnessUrl = process.env.HARNESS_API_URL ?? 'http://127.0.0.1:8001';
    const timeoutMs = Math.max(1000, Number(process.env.HARNESS_TIMEOUT_MS ?? 120000));
    try {
        const body = req.body && Object.keys(req.body).length > 0
            ? req.body
            : { case_id: 'h2o_gs_reference' };

        const response = await httpRequest(`${harnessUrl}/harness/run_case`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            timeoutMs,
        });

        const raw = await response.text();
        let payload: any = null;
        try {
            payload = raw ? JSON.parse(raw) : null;
        } catch {
            payload = { error: raw || 'Harness returned non-JSON response' };
        }

        if (!response.ok) {
            return res.status(response.status).json(payload ?? { error: 'Harness call failed' });
        }

        res.json(payload);
    } catch (error: any) {
        console.error('[Harness Proxy] Error:', error.message);
        res.status(503).json({ error: `Harness unavailable: ${error.message}` });
    }
});

app.get('/api/harness/case-registry', async (req, res) => {
    const harnessUrl = process.env.HARNESS_API_URL ?? 'http://127.0.0.1:8001';
    const timeoutMs = Math.max(1000, Number(process.env.HARNESS_TIMEOUT_MS ?? 120000));
    try {
        const includeUnapprovedRaw = typeof req.query.include_unapproved === 'string'
            ? req.query.include_unapproved
            : '';
        const includeUnapproved = includeUnapprovedRaw ? `?include_unapproved=${encodeURIComponent(includeUnapprovedRaw)}` : '';
        const response = await httpRequest(`${harnessUrl}/harness/case_registry${includeUnapproved}`, {
            method: 'GET',
            timeoutMs,
        });
        const raw = await response.text();
        let payload: any = null;
        try {
            payload = raw ? JSON.parse(raw) : null;
        } catch {
            payload = { error: raw || 'Harness returned non-JSON response' };
        }
        if (!response.ok) {
            return res.status(response.status).json(payload ?? { error: 'Harness call failed' });
        }
        res.json(payload);
    } catch (error: any) {
        console.error('[Harness Proxy] Registry Error:', error.message);
        res.status(503).json({ error: `Harness unavailable: ${error.message}` });
    }
});

app.post('/api/harness/iterate-case', async (req, res) => {
    const harnessUrl = process.env.HARNESS_API_URL ?? 'http://127.0.0.1:8001';
    const timeoutMs = Math.max(1000, Number(process.env.HARNESS_TIMEOUT_MS ?? 120000));
    try {
        const body = req.body && Object.keys(req.body).length > 0
            ? req.body
            : { case_id: 'h2o_gs_reference', max_iterations: 3 };

        const response = await httpRequest(`${harnessUrl}/harness/iterate_case`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            timeoutMs,
        });

        const raw = await response.text();
        let payload: any = null;
        try {
            payload = raw ? JSON.parse(raw) : null;
        } catch {
            payload = { error: raw || 'Harness returned non-JSON response' };
        }

        if (!response.ok) {
            return res.status(response.status).json(payload ?? { error: 'Harness call failed' });
        }

        res.json(payload);
    } catch (error: any) {
        console.error('[Harness Proxy] Iterate Error:', error.message);
        res.status(503).json({ error: `Harness unavailable: ${error.message}` });
    }
});

app.post('/api/harness/review-case-delta', async (req, res) => {
    const harnessUrl = process.env.HARNESS_API_URL ?? 'http://127.0.0.1:8001';
    const timeoutMs = Math.max(1000, Number(process.env.HARNESS_TIMEOUT_MS ?? 120000));
    try {
        const body = req.body || {};
        const caseId = String(body.case_id || body?.run_result?.case_id || 'h2o_gs_reference');
        const strict = Boolean(body.strict !== false);

        let runResult: any = body.run_result || null;
        if (!runResult) {
            const response = await httpRequest(`${harnessUrl}/harness/run_case`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ case_id: caseId }),
                timeoutMs,
            });
            const raw = await response.text();
            try {
                runResult = raw ? JSON.parse(raw) : null;
            } catch {
                runResult = null;
            }
            if (!response.ok || !runResult) {
                return res.status(response.ok ? 500 : response.status).json({
                    error: 'Unable to obtain harness result for benchmark review',
                    case_id: caseId,
                    detail: raw || undefined,
                });
            }
        }

        const relativeError = typeof runResult?.relative_error === 'number' ? runResult.relative_error : null;
        const threshold = typeof runResult?.threshold === 'number'
            ? runResult.threshold
            : (typeof body?.threshold === 'number' ? Number(body.threshold) : 0.03);
        const attemptsUsed = Number(runResult?.harness_constraints?.attempts_used ?? 0);
        const maxRetries = Number(runResult?.harness_constraints?.max_retries ?? 0);
        const escalationRequired = Boolean(runResult?.escalation?.required);
        const passedFlag = Boolean(runResult?.passed);

        const checks: Record<string, boolean> = {
            benchmark_delta_within_threshold: relativeError != null ? relativeError <= threshold : false,
            harness_pass_flag: passedFlag,
            no_escalation_required: !escalationRequired,
            attempts_within_budget: maxRetries > 0 ? attemptsUsed <= maxRetries : true,
            benchmarks_aligned_ok: relativeError != null ? relativeError <= threshold : false,
            ui_rendering_ok: true,
        };

        const allPassed = Object.values(checks).every((value) => value === true);
        const finalVerdict = allPassed ? 'PASS' : 'FAIL';
        const margin = relativeError != null ? threshold - relativeError : null;
        const nextAction = allPassed
            ? 'promote_to_done'
            : (strict ? 'planner_executor_reviewer_iterate' : 'review_and_manual_fix');
        const repairType = allPassed
            ? 'none'
            : (checks.benchmark_delta_within_threshold ? 'orchestration_config' : 'parameter_tuning');
        const repairConfidence = allPassed
            ? 1
            : (checks.benchmark_delta_within_threshold ? 0.7 : 0.92);

        return res.json({
            case_id: runResult?.case_id || caseId,
            strict,
            final_verdict: finalVerdict,
            checks,
            delta: {
                relative_error: relativeError,
                threshold,
                margin,
            },
            benchmark_review: {
                final_verdict: finalVerdict,
                delta: {
                    relative_error: relativeError,
                    threshold,
                    margin,
                },
                next_action: nextAction,
            },
            attempts: {
                used: attemptsUsed,
                budget: maxRetries,
            },
            escalation_required: escalationRequired,
            next_action: nextAction,
            repair_type: repairType,
            repair_confidence: repairConfidence,
            run_result_ref: runResult?.log_refs || null,
        });
    } catch (error: any) {
        console.error('[Harness Proxy] Review Error:', error.message);
        res.status(503).json({ error: `Harness review unavailable: ${error.message}` });
    }
});

app.post('/api/harness/review-iterate-case', async (req, res) => {
    const harnessUrl = process.env.HARNESS_API_URL ?? 'http://127.0.0.1:8001';
    const timeoutMs = Math.max(1000, Number(process.env.HARNESS_TIMEOUT_MS ?? 120000));
    try {
        const body = req.body || {};
        const caseId = String(body.case_id || 'h2o_gs_reference');
        const maxIterations = Math.max(1, Math.min(10, Number(body.max_iterations || 3)));
        const threshold = typeof body?.threshold === 'number' ? Number(body.threshold) : 0.03;

        const iterateResp = await httpRequest(`${harnessUrl}/harness/iterate_case`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case_id: caseId, max_iterations: maxIterations }),
            timeoutMs,
        });
        const iterateRaw = await iterateResp.text();
        let iteratePayload: any = null;
        try {
            iteratePayload = iterateRaw ? JSON.parse(iterateRaw) : null;
        } catch {
            iteratePayload = null;
        }
        if (!iterateResp.ok || !iteratePayload) {
            return res.status(iterateResp.ok ? 500 : iterateResp.status).json({
                error: 'Harness iterate_case unavailable for review loop',
                case_id: caseId,
                detail: iterateRaw || undefined,
            });
        }

        const history = Array.isArray(iteratePayload?.history) ? iteratePayload.history : [];
        const finalRun = history.length > 0 ? history[history.length - 1] : iteratePayload?.final || null;
        if (!finalRun) {
            return res.status(500).json({
                error: 'Iterative harness run did not return a final record',
                case_id: caseId,
            });
        }

        const relativeError = typeof finalRun?.relative_error === 'number' ? finalRun.relative_error : null;
        const effectiveThreshold = typeof finalRun?.threshold === 'number' ? finalRun.threshold : threshold;
        const attemptsUsed = Number(finalRun?.harness_constraints?.attempts_used ?? iteratePayload?.iterations_completed ?? 0);
        const maxRetries = Number(finalRun?.harness_constraints?.max_retries ?? maxIterations);
        const escalationRequired = Boolean(finalRun?.escalation?.required);
        const passedFlag = Boolean(finalRun?.passed ?? iteratePayload?.passed);

        const checks: Record<string, boolean> = {
            benchmark_delta_within_threshold: relativeError != null ? relativeError <= effectiveThreshold : false,
            harness_pass_flag: passedFlag,
            no_escalation_required: !escalationRequired,
            attempts_within_budget: maxRetries > 0 ? attemptsUsed <= maxRetries : true,
            benchmarks_aligned_ok: relativeError != null ? relativeError <= effectiveThreshold : false,
            ui_rendering_ok: true,
        };

        const allPassed = Object.values(checks).every((value) => value === true);
        const finalVerdict = allPassed ? 'PASS' : 'FAIL';
        const margin = relativeError != null ? effectiveThreshold - relativeError : null;
        const nextAction = allPassed ? 'promote_to_done' : 'planner_executor_reviewer_iterate';
        const repairType = allPassed
            ? 'none'
            : (checks.benchmark_delta_within_threshold ? 'orchestration_config' : 'parameter_tuning');
        const repairConfidence = allPassed
            ? 1
            : (checks.benchmark_delta_within_threshold ? 0.7 : 0.92);

        return res.json({
            case_id: finalRun?.case_id || caseId,
            final_verdict: finalVerdict,
            checks,
            delta: {
                relative_error: relativeError,
                threshold: effectiveThreshold,
                margin,
            },
            benchmark_review: {
                final_verdict: finalVerdict,
                delta: {
                    relative_error: relativeError,
                    threshold: effectiveThreshold,
                    margin,
                },
                next_action: nextAction,
            },
            attempts: {
                used: attemptsUsed,
                budget: maxRetries,
            },
            escalation_required: escalationRequired,
            next_action: nextAction,
            repair_type: repairType,
            repair_confidence: repairConfidence,
            iterations_requested: maxIterations,
            iterations_completed: Number(iteratePayload?.iterations_completed ?? history.length),
            history_count: history.length,
        });
    } catch (error: any) {
        console.error('[Harness Proxy] Review Iterate Error:', error.message);
        res.status(503).json({ error: `Harness review-iterate unavailable: ${error.message}` });
    }
});

// ─── Agent Auto Suite (DFT/TDDFT production scenarios) ───────────
app.post('/api/agents/run-dft-tddft-suite', async (req, res) => {
    const body = req.body || {};
    const molecule = String(body.molecule || 'H2O').trim() || 'H2O';
    const tdSteps = Math.max(80, Math.min(2000, Number(body.tdSteps || 260)));
    const tdTimeStep = Math.max(0.005, Math.min(0.2, Number(body.tdTimeStep || 0.04)));
    const strict = Boolean(body.strict === true);
    const fastPath = Boolean(body.fastPath === true);
    const taskIds = Array.isArray(body.taskIds)
        ? body.taskIds.map((x: any) => String(x || '').trim()).filter(Boolean)
        : [];
    const spacing = Number(body.octopusSpacing);
    const radius = Number(body.octopusRadius);
    const extraStates = Number(body.octopusExtraStates);
    const periodic = String(body.octopusPeriodic || '').trim().toLowerCase();
    const dimensions = String(body.octopusDimensions || '').trim();
    const boxShape = String(body.octopusBoxShape || '').trim();
    const xcFunctional = String(body.xcFunctional || '').trim();
    const octopusNcpus = Number(body.octopusNcpus);
    const octopusMpiprocs = Number(body.octopusMpiprocs);

    const isWin = process.platform === 'win32';
    const pyExec = (process.env.DIRAC_PYTHON_EXEC || '').trim()
        || (isWin ? 'python' : 'python3');
    const scriptPath = path.resolve(__dirname, '..', 'scripts', 'run_dft_tddft_agent_suite.py');

    const args = [
        scriptPath,
        '--api-base', `http://127.0.0.1:${process.env.PORT || 3001}`,
        '--molecule', molecule,
        '--td-steps', String(tdSteps),
        '--td-time-step', String(tdTimeStep),
    ];
    if (taskIds.length > 0) {
        args.push('--task-ids', taskIds.join(','));
    }
    if (Number.isFinite(spacing)) {
        args.push('--octopus-spacing', String(spacing));
    }
    if (Number.isFinite(radius)) {
        args.push('--octopus-radius', String(radius));
    }
    if (Number.isFinite(extraStates)) {
        args.push('--octopus-extra-states', String(extraStates));
    }
    if (periodic) {
        args.push('--octopus-periodic', periodic);
    }
    if (dimensions) {
        args.push('--octopus-dimensions', dimensions);
    }
    if (boxShape) {
        args.push('--octopus-box-shape', boxShape);
    }
    if (xcFunctional) {
        args.push('--xc-functional', xcFunctional);
    }
    if (Number.isFinite(octopusNcpus) && octopusNcpus > 0) {
        args.push('--octopus-ncpus', String(Math.floor(octopusNcpus)));
    }
    if (Number.isFinite(octopusMpiprocs) && octopusMpiprocs > 0) {
        args.push('--octopus-mpiprocs', String(Math.floor(octopusMpiprocs)));
    }
    if (strict) {
        args.push('--strict');
    }
    if (fastPath) {
        args.push('--fast-path');
    } else {
        args.push('--no-fast-path');
    }

    try {
        const proc = spawn(pyExec, args, {
            cwd: path.resolve(__dirname, '..'),
            env: process.env,
        });
        let settled = false;

        let stdout = '';
        let stderr = '';

        proc.stdout?.on('data', (chunk: Buffer) => {
            stdout += chunk.toString();
        });
        proc.stderr?.on('data', (chunk: Buffer) => {
            stderr += chunk.toString();
        });

        proc.on('error', (error: any) => {
            if (settled) return;
            settled = true;
            console.error('[Agent Suite] spawn error:', error?.message || error);
            res.status(500).json({ error: `Failed to start suite: ${error?.message || String(error)}` });
        });

        proc.on('close', (code: number | null) => {
            if (settled) return;
            settled = true;
            const lines = stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
            const kv: Record<string, string> = {};
            for (const line of lines) {
                const idx = line.indexOf('=');
                if (idx <= 0) continue;
                const key = line.slice(0, idx).trim();
                const value = line.slice(idx + 1).trim();
                if (key) kv[key] = value;
            }

            const reportPath = kv.suite_report_json;
            let reportPayload: any = null;
            if (reportPath) {
                try {
                    const absoluteReport = path.isAbsolute(reportPath)
                        ? reportPath
                        : path.resolve(path.resolve(__dirname, '..'), reportPath);
                    reportPayload = JSON.parse(fs.readFileSync(absoluteReport, 'utf-8'));
                } catch (error: any) {
                    console.error('[Agent Suite] read report error:', error?.message || error);
                }
            }

            if (!reportPayload && code !== 0) {
                return res.status(500).json({
                    error: `Suite failed with exit code ${code}`,
                    stdout,
                    stderr,
                });
            }

            return res.json({
                status: code === 0 ? 'ok' : 'failed',
                exitCode: code,
                runner: {
                    python: pyExec,
                    script: scriptPath,
                    molecule,
                    tdSteps,
                    tdTimeStep,
                    strict,
                    fastPath,
                },
                report: reportPayload,
                report_json: kv.suite_report_json,
                report_md: kv.suite_report_md,
                suite_verdict: kv.suite_verdict || reportPayload?.reviewer?.final_verdict || 'UNKNOWN',
                stderr,
            });
        });
    } catch (error: any) {
        console.error('[Agent Suite] error:', error.message);
        res.status(500).json({ error: `Agent suite unavailable: ${error.message}` });
    }
});

// ─── Official GS Convergence (Octopus tutorial-like) ─────────────
app.post('/api/agents/run-official-gs-convergence', async (req, res) => {
    const body = req.body || {};
    const molecule = String(body.molecule || 'N_atom').trim() || 'N_atom';
    const tutorialProfile = String(body.tutorialProfile || '').trim();
    const reportStyle = String(body.reportStyle || 'auto').trim();
    const referenceUrl = String(body.referenceUrl || 'https://www.octopus-code.org/documentation/16/tutorial/basics/total_energy_convergence/').trim();
    const radius = Number(body.radius);
    const referenceSpacing = Number(body.referenceSpacing);
    const spacings = String(body.spacings || '').trim();
    const xcFunctional = String(body.xcFunctional || 'lda_x+lda_c_pz').trim();
    const spinComponents = String(body.spinComponents || 'spin_polarized').trim();
    const eigensolver = String(body.eigenSolver || body.octopusEigenSolver || '').trim();
    const extraStates = Number(body.extraStates);
    const octopusNcpus = Number(body.octopusNcpus);
    const octopusMpiprocs = Number(body.octopusMpiprocs);

    const isWin = process.platform === 'win32';
    const pyExec = (process.env.DIRAC_PYTHON_EXEC || '').trim() || (isWin ? 'python' : 'python3');
    const scriptPath = path.resolve(__dirname, '..', 'scripts', 'run_octopus_nitrogen_total_energy_convergence.py');

    const args = [
        scriptPath,
        '--api-base', `http://127.0.0.1:${process.env.PORT || 3001}`,
        '--molecule', molecule,
        '--reference-url', referenceUrl,
        '--xc-functional', xcFunctional,
        '--spin-components', spinComponents,
    ];
    if (tutorialProfile) {
        args.push('--tutorial-profile', tutorialProfile);
    }
    if (reportStyle) {
        args.push('--report-style', reportStyle);
    }
    if (Number.isFinite(radius) && radius > 0) {
        args.push('--radius', String(radius));
    }
    if (Number.isFinite(referenceSpacing) && referenceSpacing > 0) {
        args.push('--reference-spacing', String(referenceSpacing));
    }
    if (spacings) {
        args.push('--spacings', spacings);
    }
    if (eigensolver) {
        args.push('--eigensolver', eigensolver);
    }
    if (Number.isFinite(extraStates) && extraStates >= 0) {
        args.push('--extra-states', String(Math.floor(extraStates)));
    }
    if (Number.isFinite(octopusNcpus) && octopusNcpus > 0) {
        args.push('--ncpus', String(Math.floor(octopusNcpus)));
    }
    if (Number.isFinite(octopusMpiprocs) && octopusMpiprocs > 0) {
        args.push('--mpiprocs', String(Math.floor(octopusMpiprocs)));
    }

    try {
        const proc = spawn(pyExec, args, {
            cwd: path.resolve(__dirname, '..'),
            env: process.env,
        });

        let settled = false;
        let stdout = '';
        let stderr = '';

        proc.stdout?.on('data', (chunk: Buffer) => {
            stdout += chunk.toString();
        });
        proc.stderr?.on('data', (chunk: Buffer) => {
            stderr += chunk.toString();
        });

        proc.on('error', (error: any) => {
            if (settled) return;
            settled = true;
            console.error('[Official GS Convergence] spawn error:', error?.message || error);
            res.status(500).json({ error: `Failed to start official GS convergence: ${error?.message || String(error)}` });
        });

        proc.on('close', (code: number | null) => {
            if (settled) return;
            settled = true;

            const lines = stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
            const pathMap: Record<string, string> = {};
            let outputMode = false;
            for (const line of lines) {
                if (line === '[done] outputs:') {
                    outputMode = true;
                    continue;
                }
                if (!outputMode || !line.startsWith('-')) continue;
                const m = line.match(/^\-\s*([^:]+):\s*(.+)$/);
                if (!m) continue;
                pathMap[m[1].trim()] = m[2].trim();
            }

            const reportJsonPath = pathMap.json;
            let reportPayload: any = null;
            if (reportJsonPath) {
                try {
                    const absoluteReport = path.isAbsolute(reportJsonPath)
                        ? reportJsonPath
                        : path.resolve(path.resolve(__dirname, '..'), reportJsonPath);
                    reportPayload = JSON.parse(fs.readFileSync(absoluteReport, 'utf-8'));
                } catch (error: any) {
                    console.error('[Official GS Convergence] read report error:', error?.message || error);
                }
            }

            if (!reportPayload && code !== 0) {
                return res.status(500).json({
                    error: `Official GS convergence failed with exit code ${code}`,
                    stdout,
                    stderr,
                });
            }

            return res.json({
                status: code === 0 ? 'ok' : 'failed',
                exitCode: code,
                runner: {
                    python: pyExec,
                    script: scriptPath,
                    molecule,
                },
                report: reportPayload,
                report_json: pathMap.json,
                report_csv: pathMap.csv,
                report_md: pathMap.md,
                report_png: pathMap.png,
                stderr,
            });
        });
    } catch (error: any) {
        console.error('[Official GS Convergence] error:', error.message);
        res.status(500).json({ error: `Official GS convergence unavailable: ${error.message}` });
    }
});

// ─── Automation Dispatch + OpenClaw Execution Readiness ─────────
app.post('/api/automation/exec-readiness', async (req, res) => {
    const body = req.body || {};
    const openclawRoot = String(body.openclawRoot || process.env.OPENCLAW_ROOT || `${process.env.HOME || ''}/.openclaw`).trim();
    const policyPath = String(body.policyPath || 'orchestration/openclaw_exec_policy.json').trim();

    const isWin = process.platform === 'win32';
    const pyExec = (process.env.DIRAC_PYTHON_EXEC || '').trim() || (isWin ? 'python' : 'python3');
    const scriptPath = path.resolve(__dirname, '..', 'scripts', 'audit_openclaw_permissions.py');

    try {
        const proc = spawn(pyExec, [
            scriptPath,
            '--openclaw-root', openclawRoot,
            '--policy', policyPath,
            '--json',
        ], {
            cwd: path.resolve(__dirname, '..'),
            env: process.env,
        });

        let stdout = '';
        let stderr = '';
        proc.stdout?.on('data', (chunk: Buffer) => { stdout += chunk.toString(); });
        proc.stderr?.on('data', (chunk: Buffer) => { stderr += chunk.toString(); });

        proc.on('error', (error: any) => {
            console.error('[Automation] readiness spawn error:', error?.message || error);
            res.status(500).json({ error: `Failed to start readiness check: ${error?.message || String(error)}` });
        });

        proc.on('close', (code: number | null) => {
            let payload: any = null;
            try {
                payload = stdout ? JSON.parse(stdout) : null;
            } catch {
                payload = null;
            }
            if (!payload) {
                return res.status(500).json({
                    status: 'error',
                    exitCode: code,
                    stdout,
                    stderr,
                });
            }
            return res.json({
                status: code === 0 ? 'ok' : 'not_ready',
                exitCode: code,
                readiness: payload,
                stderr,
            });
        });
    } catch (error: any) {
        console.error('[Automation] readiness error:', error.message);
        res.status(500).json({ error: `Automation readiness unavailable: ${error.message}` });
    }
});

app.post('/api/automation/ensure-exec', async (req, res) => {
    const body = req.body || {};
    const openclawRoot = String(body.openclawRoot || process.env.OPENCLAW_ROOT || `${process.env.HOME || ''}/.openclaw`).trim();
    const timeoutMs = Math.max(15000, Number(body.timeoutMs || 60000));

    const isWin = process.platform === 'win32';
    const pyExec = (process.env.DIRAC_PYTHON_EXEC || '').trim() || (isWin ? 'python' : 'python3');
    const scriptPath = path.resolve(__dirname, '..', 'scripts', 'ensure_openclaw_exec.py');

    try {
        const proc = spawn(pyExec, [
            scriptPath,
            '--openclaw-root', openclawRoot,
            '--timeout-ms', String(timeoutMs),
            '--json',
        ], {
            cwd: path.resolve(__dirname, '..'),
            env: process.env,
        });

        let stdout = '';
        let stderr = '';
        proc.stdout?.on('data', (chunk: Buffer) => { stdout += chunk.toString(); });
        proc.stderr?.on('data', (chunk: Buffer) => { stderr += chunk.toString(); });

        proc.on('error', (error: any) => {
            console.error('[Automation] ensure spawn error:', error?.message || error);
            res.status(500).json({ error: `Failed to start ensure script: ${error?.message || String(error)}` });
        });

        proc.on('close', (code: number | null) => {
            let payload: any = null;
            try {
                payload = stdout ? JSON.parse(stdout) : null;
            } catch {
                payload = null;
            }
            if (!payload) {
                return res.status(500).json({
                    status: 'error',
                    exitCode: code,
                    stdout,
                    stderr,
                });
            }
            return res.json({
                status: code === 0 ? 'ok' : 'needs_scope_approval',
                exitCode: code,
                result: payload,
                stderr,
            });
        });
    } catch (error: any) {
        console.error('[Automation] ensure error:', error.message);
        res.status(500).json({ error: `Automation ensure unavailable: ${error.message}` });
    }
});

app.post('/api/automation/dispatch', async (req, res) => {
    const body = req.body || {};
    const task = String(body.task || '').trim();
    if (!task) {
        return res.status(400).json({ error: 'Missing task.' });
    }

    const sourceFromBody = String(body.source || '').trim();
    const hasFeishuHeaders = Boolean(
        req.get('x-lark-request-timestamp')
        || req.get('x-lark-signature')
        || req.get('x-feishu-request-timestamp')
        || req.get('x-feishu-signature')
    );
    const source = sourceFromBody || (hasFeishuHeaders ? 'feishu-auto-queue' : 'api');
    const execute = Boolean(body.execute === true);
    const isAutoTask = looksLikeAutoOrchestrationTask(task);
    const isFeishuSource = source.toLowerCase().startsWith('feishu');

    if (STRICT_FEISHU_AUTO_SOURCE && isAutoTask && !isFeishuSource) {
        return res.status(403).json({
            status: 'blocked_source_policy',
            error: 'auto_orchestration_requires_feishu_source',
            requiredSource: 'feishu-*',
            receivedSource: source,
            task,
        });
    }

    const isWin = process.platform === 'win32';
    const pyExec = (process.env.DIRAC_PYTHON_EXEC || '').trim() || (isWin ? 'python' : 'python3');
    const scriptPath = path.resolve(__dirname, '..', 'scripts', 'dispatch_dirac_task.py');

    const args = [
        scriptPath,
        '--task', task,
        '--source', source,
    ];
    if (execute) {
        args.push('--execute');
    }

    try {
        const proc = spawn(pyExec, args, {
            cwd: path.resolve(__dirname, '..'),
            env: process.env,
        });

        let stdout = '';
        let stderr = '';
        proc.stdout?.on('data', (chunk: Buffer) => { stdout += chunk.toString(); });
        proc.stderr?.on('data', (chunk: Buffer) => { stderr += chunk.toString(); });

        proc.on('error', (error: any) => {
            console.error('[Automation] dispatch spawn error:', error?.message || error);
            res.status(500).json({ error: `Failed to start dispatch script: ${error?.message || String(error)}` });
        });

        proc.on('close', (code: number | null) => {
            const lines = stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
            const kv: Record<string, string> = {};
            for (const line of lines) {
                const idx = line.indexOf('=');
                if (idx <= 0) continue;
                const key = line.slice(0, idx).trim();
                const value = line.slice(idx + 1).trim();
                if (key) kv[key] = value;
            }

            const dispatchReportPath = String(kv.dispatch_report || '').trim();
            let reportPayload: any = null;
            if (dispatchReportPath) {
                const reportCandidatePath = path.isAbsolute(dispatchReportPath)
                    ? dispatchReportPath
                    : path.resolve(path.resolve(__dirname, '..'), dispatchReportPath);
                try {
                    if (fs.existsSync(reportCandidatePath)) {
                        const rawReport = fs.readFileSync(reportCandidatePath, 'utf-8');
                        reportPayload = rawReport ? JSON.parse(rawReport) : null;
                    }
                } catch {
                    reportPayload = null;
                }
            }

            const reportWorkflow = (reportPayload?.workflow && typeof reportPayload.workflow === 'object') ? reportPayload.workflow : {};
            const reportLoopContract = (reportPayload?.loop_verdict_contract && typeof reportPayload.loop_verdict_contract === 'object')
                ? reportPayload.loop_verdict_contract
                : {};
            const reportAutonomous = (reportPayload?.autonomous_assessment && typeof reportPayload.autonomous_assessment === 'object')
                ? reportPayload.autonomous_assessment
                : {};
            const reportConvergenceGate = (reportPayload?.convergence_gate && typeof reportPayload.convergence_gate === 'object')
                ? reportPayload.convergence_gate
                : {};

            const convergenceGateUnmet = kv.convergence_gate_unmet && kv.convergence_gate_unmet !== '-'
                ? kv.convergence_gate_unmet
                : Array.isArray(reportConvergenceGate.unmet_conditions)
                    ? reportConvergenceGate.unmet_conditions.join(',')
                    : '-';

            if (execute) {
                updateBridgeFromDispatchResult({
                    taskId: String(kv.dispatch_task_id || reportPayload?.task_id || ''),
                    dispatchStatus: String(kv.dispatch_status || reportPayload?.status || 'unknown'),
                    humanStatus: String(kv.human_status || reportPayload?.human_status || ''),
                    failureReason: String(kv.failure_reason || reportPayload?.failure_reason || ''),
                    workflowRoute: String(kv.workflow_route || reportWorkflow?.route || 'L0'),
                    workflowState: String(kv.workflow_state || reportWorkflow?.state || 'UNKNOWN'),
                    workflowEvent: String(kv.workflow_event || reportWorkflow?.last_event || ''),
                    workflowNextRoute: String(kv.workflow_next_route || reportWorkflow?.next_route || kv.workflow_route || reportWorkflow?.route || 'L0'),
                    consistencyToken: String(kv.consistency_token || reportPayload?.consistency_token || ''),
                    updatedAt: String(reportPayload?.updated_at || reportPayload?.timestamp || new Date().toISOString()),
                });
            }

            return res.status(code === 0 ? 200 : 409).json({
                status: code === 0 ? 'ok' : 'blocked_or_failed',
                exitCode: code,
                task,
                source,
                execute,
                dispatchReport: kv.dispatch_report,
                dispatchTaskId: kv.dispatch_task_id || reportPayload?.task_id,
                assignee: kv.assignee,
                action: kv.action,
                dispatchStatus: kv.dispatch_status,
                humanStatus: kv.human_status || reportPayload?.human_status,
                failureReason: kv.failure_reason,
                preflightReady: kv.preflight_ready,
                executionExitCode: kv.execution_exit_code,
                workflowRoute: kv.workflow_route || reportWorkflow?.route,
                workflowState: kv.workflow_state || reportWorkflow?.state,
                workflowEvent: kv.workflow_event || reportWorkflow?.last_event,
                workflowNextRoute: kv.workflow_next_route || reportWorkflow?.next_route,
                workflowPolicyOverrideFor: kv.workflow_policy_override_for || reportWorkflow?.policy?.policy_override_for,
                timestamp: reportPayload?.timestamp || null,
                updatedAt: reportPayload?.updated_at || reportPayload?.timestamp || null,
                nextAction: reportPayload?.next_action || null,
                replanPacket: kv.replan_packet,
                escalationPacket: kv.escalation_packet,
                codingSubmitted: kv.coding_submitted,
                codingTaskId: kv.coding_task_id,
                retryable: kv.retryable || String(reportLoopContract.retryable ?? ''),
                loopIterationCount: kv.loop_iteration_count || String(reportLoopContract.loop_iteration_count ?? ''),
                loopMaxAttempts: kv.loop_max_attempts || String(reportLoopContract.loop_max_attempts ?? ''),
                retryBackoffSeconds: kv.retry_backoff_seconds || String(reportLoopContract.retry_backoff_seconds ?? ''),
                consistencyToken: kv.consistency_token || reportPayload?.consistency_token || '',
                autonomousCompletion: kv.autonomous_completion || reportAutonomous.completion_state || '',
                autonomousHealth: kv.autonomous_health || reportAutonomous.health_state || '',
                autonomousReady: kv.autonomous_ready || String(reportAutonomous.ready_for_next_auto_task ?? ''),
                autonomousBlockers: kv.autonomous_blockers || (Array.isArray(reportAutonomous.blockers) ? reportAutonomous.blockers.join(',') : '-'),
                convergenceGateApplied: kv.convergence_gate_applied || String(reportConvergenceGate.applied ?? ''),
                convergenceGatePassed: kv.convergence_gate_passed || String(reportConvergenceGate.passed ?? ''),
                convergenceGateUnmet: convergenceGateUnmet,
                stdout,
                stderr,
            });
        });
    } catch (error: any) {
        console.error('[Automation] dispatch error:', error.message);
        res.status(500).json({ error: `Automation dispatch unavailable: ${error.message}` });
    }
});

app.get('/api/automation/dispatch/latest', (_req, res) => {
    try {
        const syncRead = readJsonFileSafe(DIRAC_SYNC_STATE_PATH);
        const bridgeRead = readJsonFileSafe(DIRAC_BRIDGE_STATE_PATH);
        const syncPayload = syncRead.data || {};
        const bridgePayload = bridgeRead.data || {};
        const syncLastTask = (syncPayload?.last_task && typeof syncPayload.last_task === 'object') ? syncPayload.last_task : {};
        const bridgeLastTask = (bridgePayload?.execution_bus?.last_task && typeof bridgePayload.execution_bus.last_task === 'object')
            ? bridgePayload.execution_bus.last_task
            : {};
        const degradedSources: string[] = [];
        if (syncRead.parseError) degradedSources.push('sync');
        if (bridgeRead.parseError) degradedSources.push('bridge');
        if (degradedSources.length > 0) {
            console.warn('[Automation] degraded state read', {
                syncPath: DIRAC_SYNC_STATE_PATH,
                syncError: syncRead.parseError,
                syncMtimeMs: syncRead.mtimeMs,
                bridgePath: DIRAC_BRIDGE_STATE_PATH,
                bridgeError: bridgeRead.parseError,
                bridgeMtimeMs: bridgeRead.mtimeMs,
            });
        }

        let latestFile: { name: string; fullPath: string; mtimeMs: number } | undefined;
        if (fs.existsSync(HARNESS_REPORTS_DIR)) {
            latestFile = fs
                .readdirSync(HARNESS_REPORTS_DIR)
                .filter((name) => /^task_dispatch_\d{8}T\d{6}Z\.json$/i.test(name))
                .map((name) => ({
                    name,
                    fullPath: path.join(HARNESS_REPORTS_DIR, name),
                    mtimeMs: fs.statSync(path.join(HARNESS_REPORTS_DIR, name)).mtimeMs,
                }))
                .sort((a, b) => b.mtimeMs - a.mtimeMs)[0];
        }

        let latestPayload: any = null;
        if (latestFile) {
            try {
                const raw = fs.readFileSync(latestFile.fullPath, 'utf-8');
                latestPayload = JSON.parse(raw || '{}');
            } catch {
                latestPayload = null;
            }
        }

        const syncUpdatedAtMs = Date.parse(String(syncPayload?.updated_at || '')) || 0;
        const reportPayloadUpdatedAtMs = Date.parse(String(latestPayload?.updated_at || latestPayload?.timestamp || '')) || 0;
        const reportUpdatedAtMs = reportPayloadUpdatedAtMs || Number(latestFile?.mtimeMs || 0);
        const latestReportTaskId = String(latestPayload?.task_id || '').trim();
        const latestReportStatus = String(latestPayload?.status || '').trim().toLowerCase();
        const latestReportWorkflowState = String(latestPayload?.workflow?.state || '').trim().toUpperCase();
        const latestReportLooksTerminal = [
            'success',
            'blocked_reviewer_gate',
            'blocked_convergence_gate',
            'execution_failed',
            'blocked_permissions',
            'input_contract_invalid',
        ].includes(latestReportStatus) || ['DONE', 'FAILED'].includes(latestReportWorkflowState);
        const bridgeUpdatedAtMs = Date.parse(String(
            bridgeLastTask?.updated_at
            || bridgePayload?.updated_at
            || syncPayload?.updated_at
            || ''
        )) || 0;
        const bridgeTaskId = String(bridgeLastTask?.task_id || '').trim();
        const bridgeDispatchStatus = String(bridgeLastTask?.dispatch_status || '').trim();
        const bridgeWorkflowState = String(bridgeLastTask?.workflow?.state || '').trim();
        const bridgeIndicatesLiveTask = ['queued', 'running', 'auto_repairing'].includes(bridgeDispatchStatus)
            || ['ROUTED', 'QUEUED', 'EXEC_L0', 'EXEC_L1', 'REVIEWING', 'REPLAN', 'RETRY_WAIT'].includes(bridgeWorkflowState.toUpperCase());
        const syncWorkflowState = String(
            syncLastTask?.workflow?.current
            || syncLastTask?.workflow?.state
            || syncLastTask?.phase
            || ''
        ).trim().toUpperCase();
        const syncResultStatus = String(syncLastTask?.last_result?.status || '').trim().toLowerCase();
        const syncSource = String(syncLastTask?.source || '').trim().toLowerCase();
        const syncIndicatesLiveTask = ['ROUTED', 'QUEUED', 'RECEIVED', 'VALIDATING', 'EXEC_L0', 'EXEC_L1', 'REVIEWING', 'REPLAN', 'RETRY_WAIT'].includes(syncWorkflowState)
            || ['pending', 'queued', 'running', 'auto_repairing'].includes(syncResultStatus)
            || syncSource.includes('feishu');
        const reportMissing = !latestFile;
        const bridgeClearlyNewerThanReport = bridgeUpdatedAtMs > reportUpdatedAtMs;
        const syncClearlyNewerThanReport = syncUpdatedAtMs > reportUpdatedAtMs;
        const syncTaskId = String(syncLastTask?.task_id || '').trim();
        const bridgeMatchesLatestReportTask = !!bridgeTaskId && !!latestReportTaskId && bridgeTaskId === latestReportTaskId;
        const syncMatchesLatestReportTask = !!syncTaskId && !!latestReportTaskId && syncTaskId === latestReportTaskId;
        const protectTerminalReportFromStaleBridge = !!latestFile
            && latestReportLooksTerminal
            && !!latestReportTaskId
            && !!bridgeTaskId
            && latestReportTaskId !== bridgeTaskId;
        // Sync timestamps can advance before bridge settles. Only allow sync-driven fallback
        // when sync + bridge + latest report all point to the same task id.
        const allowSyncDrivenFallback = syncClearlyNewerThanReport
            && bridgeMatchesLatestReportTask
            && syncMatchesLatestReportTask;
        // When reports lag behind queue intake, allow sync-only live tasks to surface
        // as latest if sync is newer and references a different task id.
        const syncTaskDiffersFromLatestReport = !!syncTaskId
            && (!latestReportTaskId || syncTaskId !== latestReportTaskId);
        const bridgeMissingOrOlderThanSync = !bridgeTaskId || bridgeUpdatedAtMs < syncUpdatedAtMs;
        const allowQueueOnlySyncFallback = syncClearlyNewerThanReport
            && syncIndicatesLiveTask
            && syncTaskDiffersFromLatestReport
            && bridgeMissingOrOlderThanSync;
        const terminalReportProtectionApplies = protectTerminalReportFromStaleBridge
            && !allowQueueOnlySyncFallback;
        const preferStateFallback = bridgeIndicatesLiveTask
            && !terminalReportProtectionApplies
            && (reportMissing || bridgeClearlyNewerThanReport || allowSyncDrivenFallback || allowQueueOnlySyncFallback);

        const preferSyncOnlyFallback = !bridgeIndicatesLiveTask
            && allowQueueOnlySyncFallback
            && !terminalReportProtectionApplies;

        const syncPhysicsResult = (syncLastTask?.last_result?.physics_result && typeof syncLastTask.last_result.physics_result === 'object')
            ? syncLastTask.last_result.physics_result
            : null;
        const syncPrimaryAcceptance = (syncPayload?.multi_agent?.reviewer?.primary_acceptance && typeof syncPayload.multi_agent.reviewer.primary_acceptance === 'object')
            ? syncPayload.multi_agent.reviewer.primary_acceptance
            : null;
        const syncCaseRows = Array.isArray(syncPayload?.multi_agent?.case_rows)
            ? syncPayload.multi_agent.case_rows
            : [];

        if (preferStateFallback || preferSyncOnlyFallback) {
            const bridgeConvergence = (bridgeLastTask?.convergence_gate && typeof bridgeLastTask.convergence_gate === 'object')
                ? bridgeLastTask.convergence_gate
                : {};
            const bridgeConvergenceUnmet = Array.isArray(bridgeConvergence?.unmet)
                ? bridgeConvergence.unmet.map((item: any) => String(item || '')).filter(Boolean)
                : [];
            const useSyncPrimaryIdentity = allowQueueOnlySyncFallback && !!syncTaskId;
            const fallbackDispatchStatus = bridgeDispatchStatus
                || (() => {
                    if (['ROUTED', 'QUEUED', 'RECEIVED', 'VALIDATING'].includes(syncWorkflowState)) return 'queued';
                    if (['EXEC_L0', 'EXEC_L1', 'REVIEWING', 'REPLAN', 'RETRY_WAIT'].includes(syncWorkflowState)) return 'running';
                    if (syncResultStatus === 'success') return 'success';
                    if (syncResultStatus === 'failed') return 'execution_failed';
                    return 'unknown';
                })();
            const workflowState = String(
                bridgeLastTask?.workflow?.state
                || syncLastTask?.workflow?.current
                || syncLastTask?.phase
                || 'UNKNOWN'
            );
            const nextAction = (syncLastTask?.next_action && typeof syncLastTask.next_action === 'object')
                ? syncLastTask.next_action
                : null;

            return res.json({
                status: 'ok',
                degradedSource: degradedSources,
                corruptSource: degradedSources.length > 0 ? degradedSources : null,
                reportPath: null,
                timestamp: syncPayload?.updated_at || bridgePayload?.updated_at || null,
                updatedAt: syncPayload?.updated_at || bridgePayload?.updated_at || null,
                taskId: useSyncPrimaryIdentity
                    ? (syncLastTask?.task_id || bridgeLastTask?.task_id || null)
                    : (bridgeLastTask?.task_id || syncLastTask?.task_id || null),
                source: syncLastTask?.source || null,
                assignee: bridgeLastTask?.assignee || syncLastTask?.routing?.assignee || null,
                action: syncLastTask?.routing?.action || null,
                dispatchStatus: useSyncPrimaryIdentity
                    ? (() => {
                        if (['ROUTED', 'QUEUED', 'RECEIVED', 'VALIDATING'].includes(syncWorkflowState)) return 'queued';
                        if (['EXEC_L0', 'EXEC_L1', 'REVIEWING', 'REPLAN', 'RETRY_WAIT'].includes(syncWorkflowState)) return 'running';
                        if (syncResultStatus === 'success') return 'success';
                        if (syncResultStatus === 'failed') return 'execution_failed';
                        return fallbackDispatchStatus;
                    })()
                    : fallbackDispatchStatus,
                humanStatus: String(bridgeLastTask?.human_status || ''),
                failureReason: String(bridgeLastTask?.failure_reason || syncLastTask?.last_result?.failure_reason || ''),
                preflightReady: null,
                executionExitCode: null,
                workflowState,
                workflowEvent: String(bridgeLastTask?.workflow?.last_event || syncLastTask?.workflow?.last_event || '-'),
                workflowRoute: String(bridgeLastTask?.workflow?.route || syncLastTask?.workflow?.route || 'L0'),
                workflowNextRoute: String(bridgeLastTask?.workflow?.next_route || syncLastTask?.workflow?.route || 'L0'),
                workflowPolicyOverrideFor: null,
                replanPacket: null,
                escalationPacket: null,
                codingTaskId: null,
                retryable: null,
                loopIterationCount: null,
                loopMaxAttempts: null,
                retryBackoffSeconds: null,
                consistencyToken: String(bridgeLastTask?.consistency_token || ''),
                autonomousCompletion: '',
                autonomousHealth: '',
                autonomousReady: null,
                autonomousBlockers: [],
                convergenceGateApplied: bridgeConvergence?.applied ?? null,
                convergenceGatePassed: bridgeConvergence?.passed ?? null,
                convergenceGateUnmet: bridgeConvergenceUnmet,
                nextAction,
                phaseStream: [],
                physicsResult: syncPhysicsResult,
                primaryAcceptance: syncPrimaryAcceptance,
                caseRows: syncCaseRows,
            });
        }

        if (!latestFile) {
            return res.status(404).json({ error: 'No dispatch report found' });
        }

        const payload = latestPayload || {};
        const phaseStream = Array.isArray(payload?.phase_stream) ? payload.phase_stream : [];
        const loopContract = (payload?.loop_verdict_contract && typeof payload.loop_verdict_contract === 'object')
            ? payload.loop_verdict_contract
            : {};
        const autonomous = (payload?.autonomous_assessment && typeof payload.autonomous_assessment === 'object')
            ? payload.autonomous_assessment
            : {};
        const convergenceGate = (payload?.convergence_gate && typeof payload.convergence_gate === 'object')
            ? payload.convergence_gate
            : {};
        const convergenceGateUnmet = Array.isArray(convergenceGate?.unmet_conditions)
            ? convergenceGate.unmet_conditions.map((item: any) => String(item || '')).filter(Boolean)
            : [];
        const physicsResult = (payload?.physics_result && typeof payload.physics_result === 'object')
            ? payload.physics_result
            : null;
        const primaryAcceptance = (payload?.reviewer?.primary_acceptance && typeof payload.reviewer.primary_acceptance === 'object')
            ? payload.reviewer.primary_acceptance
            : null;
        const caseRows = Array.isArray(payload?.case_delta_rows)
            ? payload.case_delta_rows
            : [];

        return res.json({
            status: 'ok',
            degradedSource: degradedSources,
            corruptSource: degradedSources.length > 0 ? degradedSources : null,
            reportPath: path.relative(path.resolve(__dirname, '..'), latestFile.fullPath).replace(/\\/g, '/'),
            timestamp: payload?.timestamp || null,
            updatedAt: payload?.updated_at || payload?.timestamp || null,
            taskId: payload?.task_id || null,
            source: payload?.source || null,
            assignee: payload?.assignee || null,
            action: payload?.action || null,
            dispatchStatus: payload?.status || 'unknown',
            humanStatus: payload?.human_status || '',
            failureReason: payload?.failure_reason || '',
            preflightReady: payload?.preflight?.ready,
            executionExitCode: payload?.execution?.exit_code,
            workflowState: payload?.workflow?.state || 'UNKNOWN',
            workflowEvent: payload?.workflow?.last_event || '-',
            workflowRoute: payload?.workflow?.route || 'L0',
            workflowNextRoute: payload?.workflow?.next_route || 'L0',
            workflowPolicyOverrideFor: payload?.workflow?.policy?.policy_override_for || null,
            replanPacket: payload?.replan_packet || null,
            escalationPacket: payload?.escalation_packet || null,
            codingTaskId: payload?.coding_submission?.task_id || null,
            retryable: loopContract?.retryable,
            loopIterationCount: loopContract?.loop_iteration_count,
            loopMaxAttempts: loopContract?.loop_max_attempts,
            retryBackoffSeconds: loopContract?.retry_backoff_seconds,
            consistencyToken: payload?.consistency_token || loopContract?.consistency_token || '',
            autonomousCompletion: autonomous?.completion_state || '',
            autonomousHealth: autonomous?.health_state || '',
            autonomousReady: autonomous?.ready_for_next_auto_task,
            autonomousBlockers: Array.isArray(autonomous?.blockers) ? autonomous.blockers : [],
            convergenceGateApplied: convergenceGate?.applied ?? null,
            convergenceGatePassed: convergenceGate?.passed ?? null,
            convergenceGateUnmet,
            phaseStream,
            physicsResult,
            primaryAcceptance,
            caseRows,
        });
    } catch (error: any) {
        console.error('[Automation] latest dispatch read error:', error?.message || error);
        return res.status(500).json({ error: `Failed to read latest dispatch report: ${error?.message || String(error)}` });
    }
});

const PORT = process.env.PORT || 3001;
app.listen(Number(PORT), '0.0.0.0', () => {
    console.log(`LangGraph Backend running on port ${PORT} (0.0.0.0)`);
});
