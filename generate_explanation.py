import sys
import json
import os
import re
from llm_client import LLMClient

def load_output_fields_knowledge():
    kb_path = os.path.join(os.path.dirname(__file__), "@Octopus_docs", "Output_Fields_Explanation.md")
    if not os.path.exists(kb_path):
        return ""
    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def sanitize_explanation_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def compact_for_prompt(obj, max_list_items=40, depth=0, max_depth=6):
    if depth > max_depth:
        return "<truncated-depth>"

    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out[k] = compact_for_prompt(v, max_list_items=max_list_items, depth=depth + 1, max_depth=max_depth)
        return out

    if isinstance(obj, list):
        if len(obj) <= max_list_items:
            return [compact_for_prompt(v, max_list_items=max_list_items, depth=depth + 1, max_depth=max_depth) for v in obj]
        head = [compact_for_prompt(v, max_list_items=max_list_items, depth=depth + 1, max_depth=max_depth) for v in obj[:max_list_items]]
        head.append(f"<... {len(obj) - max_list_items} items omitted ...>")
        return head

    return obj


def generate_explanation(result_data, output_file="physics_explanation.md", external_knowledge="", image_paths=None, image_urls=None):
    """
    Generates a Markdown explanation of the physics computation results using ZChat.
    Supports both Local 1D solver results and Octopus 3D DFT results.
    """
    try:
        # Detect engine type to build an appropriate prompt
        engine = result_data.get('engine', '')
        is_octopus = 'octopus' in str(engine).lower() or 'dft' in str(engine).lower() or result_data.get('scfConverged') is not None

        if is_octopus:
            physics_context = f"""
This is an **Octopus DFT (Density Functional Theory)** calculation result for a real 3D quantum system.
Key result fields to analyse:
- `eigenvalues`: Kohn-Sham orbital energies in Hartree (1 Ha = 27.211 eV)
- `homoEv` / `lumoEv`: HOMO and LUMO energies in eV; gap = LUMO - HOMO
- `totalEnergy`: Total DFT ground-state energy in Hartree
- `scfConverged` / `scfIterations`: self-consistent field convergence quality
- `molecule`: the system studied (e.g. H2, He, Ne)
- `spacing` (Bohr), `radius` (Bohr): real-space grid parameters
- `tdMaxSteps`: if present, a time-dependent (TD-DFT) run was performed

Physics evaluation checklist:
1. For H₂: bonding orbital eigenvalue should be around -0.5 Ha (experimental -0.594 Ha); check sign and magnitude.
2. SCF convergence: confirm `scfConverged=true`; note number of iterations.
3. HOMO–LUMO gap: for H₂ the fundamental gap is ~10–16 eV; evaluate whether the computed gap is physically reasonable.
4. If TD-DFT was run, note that the optical absorption spectrum captures electron dynamics beyond ground-state DFT.
5. Grid quality: spacing ≥ 0.2 Bohr is DEV mode (coarse); spacing < 0.1 Bohr is production quality.
"""
        else:
            physics_context = f"""
This is a **local 1D Schrödinger/Dirac equation** solver result.
Key result fields to analyse:
- `eigenvalues`: energy eigenvalues in the chosen unit system (natural units or SI)
- `gridPoints`, `spatialRange`, `gridSpacing`: finite-difference grid parameters
- `boundaryCondition`: Dirichlet, periodic, or absorbing
- `potentialType` / `potentialStrength`: potential well configuration

Physics evaluation checklist:
1. For an Infinite Square Well: $E_n = n^2 \\pi^2 \\hbar^2 / (2mL^2)$. Compare computed vs analytic.
2. Finite difference introduces $O(\\Delta x^2)$ truncation error; a ~1–5% deviation from analytic is normal.
3. If deviation is large (>10%), flag as possible grid resolution artifact.
"""

        kb_text = external_knowledge or load_output_fields_knowledge()
        compact_result = compact_for_prompt(result_data, max_list_items=40)
        prompt = f"""You are an expert computational physicist. Analyse the following quantum physics computation results and produce a concise, practical report.

Engine context:
{physics_context}

    Knowledge-base context for output file interpretation:
    {kb_text[:4000] if kb_text else "(No extra knowledge base provided.)"}

Full result JSON:
```json
{json.dumps(compact_result, indent=2, ensure_ascii=False)}
```

Output requirements:
- Prefer Chinese.
- Keep total length within ~500 Chinese characters (or equivalent concise length).
- Focus only on this run's key outputs, avoid generic textbook content.
- Use Markdown headings and bullets.

Must include exactly these sections:
1. `## 本次计算概览` (system, mode, key params)
2. `## 关键结果` (eigenvalues / HOMO-LUMO / convergence)
3. `## 字段速读` (DOS, cross_section_vector, and important output files)
4. `## 结果可信度与下一步` (brief validation + one actionable suggestion)

For missing fields, say "当前输出未包含".
"""

        # Initialize the LLM Client
        print("Initializing LLM client...", file=sys.stderr)
        llm_timeout = int(os.getenv("ZCHAT_MODEL_TIMEOUT_S", "60"))
        llm = LLMClient(timeout_seconds=max(15, llm_timeout))

        messages = [
            {"role": "developer", "content": "You are an expert computational physicist and a helpful AI assistant."},
        ]
        messages.append(
            llm.build_multimodal_user_message(
                prompt,
                image_paths=image_paths or [],
                image_urls=image_urls or [],
            )
        )
        
        # Call the chat completion API
        print("Calling chat completion...", file=sys.stderr)
        models_env = os.getenv("ZCHAT_MODEL_FALLBACK", "gpt-5,gpt-5-thinking,gemini-3-pro")
        model_list = [m.strip() for m in models_env.split(",") if m.strip()]
        if not model_list:
            model_list = ["gpt-5"]
        reply = llm.chat_completion(
            messages,
            models=model_list,
        )
        
        explanation = sanitize_explanation_text(reply.choices[0].message.content)
        
        # Write the explanation to the output file
        output_file = output_file or "physics_explanation.md"
        output_dir = os.path.dirname(output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(explanation)
            
        # VERY IMPORTANT: ONLY output JSON to stdout so Node.js `JSON.parse` does not crash
        print(json.dumps({"status": "success", "file": output_file}))

    except Exception as e:
        print(f"Error generating explanation: {str(e)}", file=sys.stderr)
        print(json.dumps({"status": "error", "message": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    # Ensure UTF-8 encoding for stdout/stderr in Windows
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    # Read the JSON string from stdin
    input_data = sys.stdin.read()
    if not input_data.strip():
        print(json.dumps({"status": "error", "message": "No input data provided."}))
        sys.exit(1)
        
    try:
        data = json.loads(input_data)
        if isinstance(data, dict) and "result" in data:
            result_payload = data.get("result") or {}
            output_file = data.get("output_file", "physics_explanation.md")
            external_knowledge = data.get("knowledge_base", "")
            image_paths = data.get("image_paths", [])
            image_urls = data.get("image_urls", [])
            if isinstance(result_payload, dict) and isinstance(data.get("config"), dict):
                result_payload.setdefault("config", data.get("config"))
            generate_explanation(
                result_payload,
                output_file=output_file,
                external_knowledge=external_knowledge,
                image_paths=image_paths,
                image_urls=image_urls,
            )
        else:
            generate_explanation(data)
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "message": f"Invalid JSON input: {str(e)}"}))
        sys.exit(1)
