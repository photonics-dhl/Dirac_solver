import sys
import json
import os
from llm_client import LLMClient

def generate_explanation(result_data):
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

        prompt = f"""You are an expert computational physicist. Analyse the following quantum physics computation results and produce a rigorous, well-structured report.

Engine context:
{physics_context}

Full result JSON:
```json
{json.dumps(result_data, indent=2, ensure_ascii=False)}
```

Output the explanation in BOTH Chinese and English, separated by these exact delimiters on their own lines:

---START_ZH---
(中文说明)
---END_ZH---

---START_EN---
(English explanation)
---END_EN---

Each section MUST cover:
1. **Problem description** – what system was simulated, dimensionality, key parameters.
2. **Methodology** – computational approach (DFT/finite-difference), grid, convergence.
3. **Results analysis** – eigenvalues, energies, HOMO/LUMO (if DFT), convergence status.
4. **Physical validity** – compare to known analytic/experimental references; flag concerns if results are unphysical.
5. **Limitations** – grid resolution effects, DEV vs production accuracy.

Use well-formatted Markdown with headers, bullet points, and LaTeX math (e.g. $E = mc^2$) where appropriate.
"""

        messages = [
            {"role": "developer", "content": "You are an expert computational physicist and a helpful AI assistant."},
            {"role": "user", "content": prompt}
        ]

        # Initialize the LLM Client
        print("Initializing LLM client...", file=sys.stderr)
        llm = LLMClient()
        
        # Call the chat completion API
        print("Calling chat completion...", file=sys.stderr)
        reply = llm.chat_completion(messages)
        
        explanation = reply.choices[0].message.content
        explanation = reply.choices[0].message.content
        
        # Write the explanation to the output file
        output_file = "physics_explanation.md"
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
        generate_explanation(data)
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "message": f"Invalid JSON input: {str(e)}"}))
        sys.exit(1)
