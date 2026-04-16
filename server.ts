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
        fetch('/api/physics/explanation/raw?file=' + encodeURIComponent(file))
      .then(r => {
        if (!r.ok) throw new Error('Not found');
        return r.text();
      })
      .then(text => {
        document.getElementById('content').textContent = text;
      })
      .catch(() => {
        document.getElementById('content').textContent = 'Computation explanation not found. Please generate one first.';
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

app.get('/api/automation/dispatch/latest', (_req, res) => {
    try {
        if (!fs.existsSync(HARNESS_REPORTS_DIR)) {
            return res.status(404).json({ error: 'harness_reports directory not found' });
        }

        const latestFile = fs
            .readdirSync(HARNESS_REPORTS_DIR)
            .filter((name) => /^task_dispatch_\d{8}T\d{6}Z\.json$/i.test(name))
            .map((name) => ({
                name,
                fullPath: path.join(HARNESS_REPORTS_DIR, name),
                mtimeMs: fs.statSync(path.join(HARNESS_REPORTS_DIR, name)).mtimeMs,
            }))
            .sort((a, b) => b.mtimeMs - a.mtimeMs)[0];

        if (!latestFile) {
            return res.status(404).json({ error: 'No dispatch report found' });
        }

        const raw = fs.readFileSync(latestFile.fullPath, 'utf-8');
        const payload = JSON.parse(raw || '{}');
        const phaseStream = Array.isArray(payload?.phase_stream) ? payload.phase_stream : [];

        return res.json({
            status: 'ok',
            reportPath: path.relative(path.resolve(__dirname, '..'), latestFile.fullPath).replace(/\\/g, '/'),
            timestamp: payload?.timestamp || null,
            dispatchStatus: payload?.status || 'unknown',
            humanStatus: payload?.human_status || '',
            failureReason: payload?.failure_reason || '',
            workflowState: payload?.workflow?.state || 'UNKNOWN',
            workflowEvent: payload?.workflow?.last_event || '-',
            workflowRoute: payload?.workflow?.route || 'L0',
            phaseStream,
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
