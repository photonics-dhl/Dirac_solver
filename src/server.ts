import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { quantumSolverApp } from './langgraph_agent';
import { HumanMessage } from '@langchain/core/messages';

const app = express();
app.use(cors());
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));

const DEV_STATE_PATH = path.resolve(__dirname, '..', 'dev_state.json');

// ─── Dirac Solver API ────────────────────────────────────────────

app.post('/api/simulate', async (req, res) => {
    try {
        const { dimensionality, gridSpacing, potentialType } = req.body;

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

        const onEvent = (eventName: string, data: any) => {
            res.write(`event: ${eventName}\n`);
            res.write(`data: ${JSON.stringify(data)}\n\n`);
        };

        const result = await runPhysicsPipeline(config, onEvent);

        const eLabels = result.eigenvalues.slice(0, 3).map((e: number) => e.toFixed(4)).join(', ');
        const eTail = result.eigenvalues.length > 3 ? '...' : '';
        console.log(`[Physics Stream] Pipeline complete. E=[${eLabels}${eTail}]`);

        onEvent('result', result);
        // Do NOT call res.end() here — let the client close the connection by calling
        // eventSource.close() when it receives the 'result' event. This prevents the
        // browser from auto-reconnecting (EventSource reconnects when server closes).
        // Safety valve: force-close after 10 s if client never disconnects.
        const safetyClose = setTimeout(() => { try { res.end(); } catch (_) {} }, 10_000);
        req.on('close', () => clearTimeout(safetyClose));
    } catch (error: any) {
        console.error("[Physics Stream] Pipeline error:", error.message);
        res.write(`event: pipeline_error\n`);
        res.write(`data: ${JSON.stringify({ message: error.message })}\n\n`);
        // Error path: close immediately
        res.end();
    }
});

app.post('/api/physics/explain', (req, res) => {
    try {
        const resultData = req.body;

        console.log(`[Physics] Generating explanation via ZChat...`);
        // Detect Python executable: Windows uses .venv\Scripts\python, Linux always uses python3
        const isWin = process.platform === 'win32';
        const pyExec = isWin ? path.join('.venv', 'Scripts', 'python') : 'python3';
        const pythonProcess = spawn(pyExec, ['generate_explanation.py']);

        let output = '';
        let errOutput = '';

        pythonProcess.stdout.on('data', (data) => {
            output += data.toString();
        });

        pythonProcess.stderr.on('data', (data) => {
            errOutput += data.toString();
            console.error(data.toString());
        });

        pythonProcess.on('error', (err) => {
            console.error("Failed to start python process:", err);
            if (!res.headersSent) {
                res.status(500).json({ error: `Failed to start explanation script: ${err.message}` });
            }
        });

        pythonProcess.on('close', (code) => {
            if (code !== 0) {
                console.error(`[Physics] Python Explanation script exited with code ${code}`);
                return res.status(500).json({ error: errOutput || 'Process exited with error code.' });
            }
            res.json({ status: 'success', file: 'physics_explanation.md' });
        });

        pythonProcess.stdin.write(JSON.stringify(resultData));
        pythonProcess.stdin.end();

    } catch (e: any) {
        console.error("Explanation generation error:", e);
        res.status(500).json({ error: e.message });
    }
});

app.get('/api/physics/explanation/raw', (req, res) => {
    try {
        const mdPath = path.join(process.cwd(), 'physics_explanation.md');
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

app.get('/api/physics/explanation', (req, res) => {
    const html = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>AI Physics Explanation - Dirac Solver</title>
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Marked.js for Markdown parsing -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <!-- MathJax for rendering LaTeX -->
    <script>
      MathJax = {
        tex: {
          inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
          displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
          processEscapes: true
        },
        svg: { fontCache: 'global' }
      };
    </script>
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>

    <style>
      body { background-color: #09090b; color: #f4f4f5; font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", "Inter", sans-serif; }
      .markdown-body h1, .markdown-body h2, .markdown-body h3 { 
          color: #fff; border-bottom: 1px solid #27272a; padding-bottom: 0.3em; margin-top: 1.5em; margin-bottom: 0.5em;
      }
      .markdown-body h1 { font-size: 2em; font-weight: 700; }
      .markdown-body h2 { font-size: 1.5em; font-weight: 600; }
      .markdown-body p { line-height: 1.7; margin-bottom: 1em; color: #d4d4d8; }
      .markdown-body ul { list-style-type: disc; padding-left: 1.5em; margin-bottom: 1em; color: #d4d4d8; }
      .markdown-body ol { list-style-type: decimal; padding-left: 1.5em; margin-bottom: 1em; color: #d4d4d8; }
      .markdown-body li { margin-bottom: 0.5em; }
      .markdown-body code { background-color: #18181b; padding: 0.2em 0.4em; border-radius: 4px; font-family: monospace; color: #a78bfa; font-size: 0.9em; }
      .markdown-body pre { background-color: #18181b; padding: 1.2em; border-radius: 8px; overflow-x: auto; margin-bottom: 1.5em; border: 1px solid #27272a; }
      .markdown-body pre code { background-color: transparent; padding: 0; color: #e4e4e7; border: none; }
      .markdown-body strong { color: #fff; font-weight: 600; }
      .markdown-body blockquote { border-left: 4px solid #3f3f46; padding-left: 1em; color: #a1a1aa; font-style: italic; }
      .MathJax:focus { outline: none; }
    </style>
</head>
<body class="p-4 md:p-12">
    <div class="max-w-4xl mx-auto bg-[#111113] border border-gray-800 rounded-2xl p-6 md:p-10 shadow-2xl relative">
        <div class="absolute top-6 right-6 flex gap-2">
            <button id="langToggleBtn" class="bg-[#27272a] hover:bg-[#3f3f46] text-sm text-white px-3 py-1.5 rounded-lg transition-colors border border-gray-700 hidden">
                English
            </button>
        </div>
        <div id="content" class="markdown-body">
            <p class="animate-pulse flex items-center gap-3">
                <svg class="animate-spin h-5 w-5 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                Loading physical derivation and analysis...
            </p>
        </div>
    </div>

    <script>
        let rawContent = { zh: '', en: '' };
        let currentLang = 'zh';

        function renderContent(mdText) {
            // Pre-process markdown to protect LaTeX blocks from being munged by marked.js
            let processedText = mdText.replace(/\\$\\$([\\s\\S]*?)\\$\\$/g, '<div class="math-display">$$$$$1$$$$</div>');
            processedText = processedText.replace(/\\\\\\[([\\s\\S]*?)\\\\\\]/g, '<div class="math-display">\\\\[$1\\\\]</div>');
            processedText = processedText.replace(/(^|[^\\\\])\\$((?!\\$)[^\\n]*?)\\$/g, '$1<span class="math-inline">$$$2$$</span>');
            processedText = processedText.replace(/\\\\\\(([\\s\\S]*?)\\\\\\)/g, '<span class="math-inline">\\\\($1\\\\)</span>');

            const parsedHTML = marked.parse(processedText);
            document.getElementById('content').innerHTML = parsedHTML;
            
            if (window.MathJax) {
                MathJax.typesetPromise().catch(err => console.error('MathJax error:', err));
            }
        }

        fetch('/api/physics/explanation/raw')
            .then(response => {
                if (!response.ok) throw new Error('Not found');
                return response.text();
            })
            .then(fullText => {
                // Parse the dual language delimiters
                const zhMatch = fullText.match(/---START_ZH---\\s*([\\s\\S]*?)\\s*---END_ZH---/);
                const enMatch = fullText.match(/---START_EN---\\s*([\\s\\S]*?)\\s*---END_EN---/);

                if (zhMatch && enMatch) {
                    rawContent.zh = zhMatch[1];
                    rawContent.en = enMatch[1];
                    document.getElementById('langToggleBtn').classList.remove('hidden');
                } else {
                    // Fallback if delimiters not found
                    rawContent.zh = fullText;
                    rawContent.en = '# English translation not available.';
                }

                renderContent(rawContent.zh);
            })
            .catch(e => {
                document.getElementById('content').innerHTML = '<h2 class="text-red-500">Computation explanation not found</h2><p>Please return to the solver and click "Generate AI Physics Explanation".</p>';
            });

        document.getElementById('langToggleBtn').addEventListener('click', (e) => {
            if (currentLang === 'zh') {
                currentLang = 'en';
                e.target.innerText = '中文';
                renderContent(rawContent.en);
            } else {
                currentLang = 'zh';
                e.target.innerText = 'English';
                renderContent(rawContent.zh);
            }
        });
    </script>
</body>
</html>
    `;
    res.type('text/html');
    res.send(html);
});

// ─── Visualization Endpoint (matplotlib for 1D/2D, VisIt for 3D) ─────────────
import { isVisItAvailable, writeVisItScript, renderWithVisIt, dockerPathToWindows } from './visit_renderer';

const OCTOPUS_OUTPUT_DIR = process.env.OCTOPUS_OUTPUT_DIR
    ?? path.join(process.cwd(), '@Octopus_docs', 'output');
const MPL_SCRIPT = path.join(process.cwd(), 'src', 'render_mpl.py');

/** Render a 1D/2D slice using matplotlib (fast, reliable). */
function renderWithMatplotlib(
    inputPath: string, plotType: string, outputPng: string,
    isoValue?: number, colormap?: string
): Promise<{ success: boolean; pngBase64?: string; durationMs: number; reason?: string }> {
    return new Promise((resolve) => {
        const start = Date.now();
        // Matplotlib lives in the system python (not .venv), use python3 directly
        const pyExe = process.platform === 'win32' ? 'python' : 'python3';
        const extraArgs: string[] = [];
        if (isoValue !== undefined) extraArgs.push(String(isoValue));
        if (colormap)               extraArgs.push(colormap);
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
        const { plotType = 'wavefunction_1d', inputFile, isoValue, colormap, wfStateIndex } = req.body as {
            plotType?: 'wavefunction_1d' | 'density_2d' | 'density_3d';
            inputFile?: string;
            isoValue?: number;
            colormap?: string;
            wfStateIndex?: number;
        };

        const stateIdx = wfStateIndex ?? 1;
        const wfSliceFile = `wf-st${String(stateIdx).padStart(5, '0')}.y=0,z=0`;
        const wfCubeFile  = `wf-st${String(stateIdx).padStart(5, '0')}.cube`;

        // Resolve input file path (docker path → host path if needed)
        const resolveInput = (filePath: string) =>
            filePath.startsWith('/') ? dockerPathToWindows(filePath) : filePath;

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
                console.log(`[mpl] Rendering density_2d_cube from: ${path.basename(cubeFile)}`);
                const result = await renderWithMatplotlib(
                    cubeFile, 'density_2d_cube', outputPng,
                    undefined, colormap ?? 'plasma'
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

        // ── Density 3D — isosurface panels from cube file (no VisIt needed) ─
        if (plotType === 'density_3d') {
            const cubeFile = inputFile ? resolveInput(inputFile) : path.join(OCTOPUS_OUTPUT_DIR, 'density.cube');
            const outputPng = path.join(OCTOPUS_OUTPUT_DIR, 'render_density_3d.png');

            if (!fs.existsSync(cubeFile)) {
                return res.json({
                    status: 'not_available',
                    reason: 'density.cube not found. Run a 3D GS Octopus calculation first (the cube file requires OutputFormat = cube + axis_x in the input).'
                });
            }

            const isoArg = isoValue ?? 0.15;
            const cmapArg = colormap ?? 'hot';
            console.log(`[mpl] Rendering density_3d_iso from: ${path.basename(cubeFile)} iso=${isoArg}`);
            const result = await renderWithMatplotlib(cubeFile, 'density_3d_iso', outputPng, isoArg, cmapArg);
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
    try {
        const response = await fetch(`${mcpUrl}/health`);
        const data = await response.json();
        res.json(data);
    } catch {
        res.status(503).json({ status: 'error', engine: 'unavailable' });
    }
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
    console.log(`LangGraph Backend running on port ${PORT}`);
});
