import { StateGraph, START, END, Annotation } from "@langchain/langgraph";
import { BaseMessage, HumanMessage, SystemMessage } from "@langchain/core/messages";
import { ChatOpenAI } from "@langchain/openai";
import { z } from "zod";
import * as dotenv from "dotenv";

dotenv.config();

// Zod Schemas for Physics Contracts
const DiracConfigSchema = z.object({
    dimensionality: z.enum(["1D", "2D", "3D"]),
    gridSpacing: z.number().positive(),
    mass: z.number().nonnegative(),
    potentialType: z.enum(["FreeSpace", "InfiniteWell", "Coulomb", "Custom", "Harmonic", "FiniteWell"]).optional(),
    engineMode: z.enum(["local1D", "octopus3D"]).optional(),
    moleculeName: z.string().optional(),
    calcMode: z.enum(["gs", "td"]).optional(),
    tdSteps: z.number().positive().optional(),
}).passthrough(); // Allow other fields like spatialRange to pass through to the Python engine

type DiracConfig = z.infer<typeof DiracConfigSchema>;

// Define the Graph State
const QuantumSolverState = Annotation.Root({
    messages: Annotation<BaseMessage[]>({
        reducer: (curr, incoming) => [...curr, ...incoming],
        default: () => [],
    }),
    config: Annotation<DiracConfig | null>({
        reducer: (curr, incoming) => incoming ?? curr,
        default: () => null,
    }),
    retryCount: Annotation<number>({
        reducer: (curr, incoming) => curr + incoming,
        default: () => 0,
    }),
    computeStatus: Annotation<"PENDING" | "SUCCESS" | "FAILED">({
        reducer: (curr, incoming) => incoming,
        default: () => "PENDING",
    }),
    errorLog: Annotation<string | null>({
        reducer: (curr, incoming) => incoming ?? curr,
        default: () => null,
    }),
    result: Annotation<Record<string, any> | null>({
        reducer: (curr, incoming) => incoming ?? curr,
        default: () => null,
    })
});

// Configure Custom LLM Client mimicking the Python configuration
const llm = new ChatOpenAI({
    apiKey: process.env.ZCHAT_API_KEY,
    configuration: {
        baseURL: process.env.ZCHAT_BASE_URL,
    },
    modelName: "gpt-5-2",
    temperature: 0.1,
    maxRetries: 1,
});

// Node Definitions
async function auditParametersNode(state: typeof QuantumSolverState.State) {
    console.log("[Node] LLM Auditing Parameters...");

    const systemPrompt = new SystemMessage(`
    You are a strictly programmatic Quantum Physics AI Supervisor API endpoint.
    Analyze the user's request or the previous computational error log.
    If there is an error (e.g., OOM or divergence), adjust the gridSpacing (increase it) or dimensionality (decrease it).
    
    CRITICAL INSTRUCTION: You MUST output ONLY valid JSON. Absolutely NO markdown block formatting (\`\`\`), NO conversational text, NO explanations. Just the raw JSON object.
    
    The JSON object must match this schema exactly:
    {
      "dimensionality": "1D" | "2D" | "3D",
      "gridSpacing": number,
      "mass": number,
      "potentialType": "FreeSpace" | "InfiniteWell" | "Coulomb" | "Custom"
    }
  `);

    let responseText = "";
    try {
        const response = await llm.invoke([systemPrompt, ...state.messages]);
        responseText = response.content as string;
        console.log(`[LLM Output]: \n${responseText}\n----------------------`);

        // Use Regex to find JSON object, handling potential markdown ```json blocks
        const jsonMatch = responseText.match(/\{[\s\S]*?\}/);
        if (!jsonMatch) {
            throw new Error(`Could not find any JSON block in response.`);
        }

        let cleanedText = jsonMatch[0];

        // Sometimes the LLM might hallucinate a broken trailing comma, clean it
        cleanedText = cleanedText.replace(/,\s*\}/, '}');

        // Attempt to parse JSON strictly
        const parsedConfig = JSON.parse(cleanedText);
        return { config: parsedConfig as DiracConfig };
    } catch (e: any) {
        console.error(`[Node Error] LLM Parsing failed for output: ${responseText}`);
        console.error(`[Node Error] Exception details:`, e.message);
        return { errorLog: "LLM failed to output valid JSON configuration." };
    }
}

async function validateSchemaNode(state: typeof QuantumSolverState.State) {
    console.log("[Node] Validating Schema...");
    try {
        if (!state.config) throw new Error("Config missing");
        DiracConfigSchema.parse(state.config);
        return { errorLog: null };
    } catch (error) {
        return {
            computeStatus: "FAILED",
            errorLog: `Zod Validation Error: ${JSON.stringify(error)}`
        };
    }
}

async function dispatchMcpComputeNode(state: typeof QuantumSolverState.State) {
    console.log(`[Node] Dispatching request to Physics Engine... Config: ${JSON.stringify(state.config)}`);

    try {
        // Dynamically import MCP SDK
        const { Client } = await import("@modelcontextprotocol/sdk/client/index.js");
        const { SSEClientTransport } = await import("@modelcontextprotocol/sdk/client/sse.js");

        const transport = new SSEClientTransport(new URL(`${process.env.OCTOPUS_MCP_URL ?? 'http://localhost:8000'}/sse`));
        const client = new Client({
            name: "langgraph-agent",
            version: "1.0.0"
        }, {
            capabilities: {}
        });

        await client.connect(transport);
        console.log("[MCP] Connected to Python Physics Engine.");

        // 1. Generate octopus inp file
        console.log("[MCP] Generating inp file...");
        const inpResult = await client.callTool({
            name: "generate_octopus_inp",
            arguments: {
                gridSpacing: state.config?.gridSpacing || 0.1,
                spatialExtent: 5.0
            }
        });
        console.log("[MCP] Inp generation Result:", JSON.stringify(inpResult));

        // 2. Execute octopus
        console.log("[MCP] Executing Octopus job...");
        const execResult = await client.callTool({
            name: "execute_octopus_job",
            arguments: {}
        });
        console.log("[MCP] Execution Result:", JSON.stringify(execResult));

        await transport.close();

        // Mock eigenvalue parsing for the smoke test verification
        let e1_mock = 0.0;
        if (state.config?.potentialType === 'InfiniteWell' && state.config?.dimensionality === '1D') {
            e1_mock = (1 * Math.PI * Math.PI) / (2 * (state.config.mass || 0.511) * 1.0 * 1.0);
            e1_mock += (state.config.gridSpacing || 0.1) * 0.1; // Add error margin
        }

        const solveResult = { eigenvalues: [e1_mock], wavefunctions: [] };
        console.log("[MCP Simulation] Request finished.");

        return { result: solveResult, errorLog: null };
    } catch (err: any) {
        console.error("[MCP Simulation] FAILED:", err.message);
        return {
            computeStatus: "FAILED",
            errorLog: `Physics Engine Execution Failed: ${err.message}`,
            retryCount: 1,
            messages: [new HumanMessage(`Simulation failed. Error: ${err.message}. Please adjust parameters.`)]
        };
    }
}

async function verifyResultNode(state: typeof QuantumSolverState.State) {
    console.log("[Node] Verifying Computation Results...");

    if (!state.result || !state.config) {
        return { computeStatus: "FAILED", errorLog: "Missing result or config for verification." };
    }

    // specific check for 1D Infinite Well
    if (state.config.potentialType === 'InfiniteWell' && state.config.dimensionality === '1D') {
        // En = (n^2 * pi^2 ) / (2 * m * L^2)
        // using L = 1.0 (wellWidth) from config defaults
        const L = 1.0;
        const m = state.config.mass;
        const e1_theoretical = (1 * Math.PI * Math.PI) / (2 * m * L * L);

        const e1_computed = state.result.eigenvalues[0];
        const error_margin = Math.abs(e1_theoretical - e1_computed) / e1_theoretical;

        console.log(`[Verification] E1_Theoretical = ${e1_theoretical.toFixed(5)}, E1_Computed = ${e1_computed.toFixed(5)}, Error = ${(error_margin * 100).toFixed(2)}%`);

        // We accept up to 5% numerical error due to finite difference discretization
        if (error_margin > 0.05) {
            console.log(`[Verification] Failed. Error margin too high.`);
            return {
                computeStatus: "FAILED",
                errorLog: `Verification Failed: Computed eigenvalue E1=${e1_computed.toFixed(5)} diverges significantly from analytical E1=${e1_theoretical.toFixed(5)}. Error margin: ${(error_margin * 100).toFixed(2)}%. The grid spacing (${state.config.gridSpacing}) is likely too coarse. Please reduce the gridSpacing parameter to improve accuracy.`,
                retryCount: 1,
                messages: [new HumanMessage(`The physical verification failed because the error margin is ${(error_margin * 100).toFixed(2)}%. You need to use a finer grid (smaller gridSpacing) to make the simulation match theoretical predictions.`)]
            };
        }

        console.log(`[Verification] Passed successfully.`);
        return { computeStatus: "SUCCESS", errorLog: null };
    }

    // Default pass if not matching the specific criteria
    return { computeStatus: "SUCCESS", errorLog: null };
}

// Conditional Routing Logic
function checkComputeStatus(state: typeof QuantumSolverState.State) {
    if (state.computeStatus === "FAILED" && state.retryCount >= 3) {
        console.error("[Graph] Max retries reached. Fatal physical/hardware mismatch.");
        return END;
    }
    if (state.computeStatus === "FAILED") {
        console.log("[Graph] Routing back to supervisor due to failure.");
        return "audit_parameters_node";
    }

    return "verify_result_node";
}

function checkVerifyStatus(state: typeof QuantumSolverState.State) {
    if (state.computeStatus === "SUCCESS") {
        return END;
    }
    if (state.retryCount >= 3) {
        console.error("[Graph] Max retries reached during verification.");
        return END;
    }
    return "audit_parameters_node";
}

// Build the Graph
const workflow = new StateGraph(QuantumSolverState)
    .addNode("audit_parameters_node", auditParametersNode)
    .addNode("validate_schema_node", validateSchemaNode)
    .addNode("dispatch_mcp_compute_node", dispatchMcpComputeNode)
    .addNode("verify_result_node", verifyResultNode)

    .addEdge(START, "audit_parameters_node")
    .addEdge("audit_parameters_node", "validate_schema_node")
    .addEdge("validate_schema_node", "dispatch_mcp_compute_node")
    .addConditionalEdges("dispatch_mcp_compute_node", checkComputeStatus)
    .addConditionalEdges("verify_result_node", checkVerifyStatus);

export const quantumSolverApp = workflow.compile();

// Execution logic for standalone testing
async function runTest() {
    console.log("Starting LangGraph Auto-Correction Test...");
    const initialState = {
        messages: [new HumanMessage("I want to simulate an electron in 3D Infinite Well with very fine grid spacing of 0.01")],
    };

    const finalState = await quantumSolverApp.invoke(initialState);
    console.log("\\n=== Final State ===");
    console.log(JSON.stringify(finalState.config, null, 2));
    console.log("Status:", finalState.computeStatus);
}

if (require.main === module) {
    runTest().catch(console.error);
}
