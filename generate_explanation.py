import sys
import json
import os
from llm_client import LLMClient

def generate_explanation(result_data):
    """
    Generates a Markdown explanation of the physics computation results using ZChat.
    """
    try:
        # Format the prompt
        prompt =f"""
You are an expert computational physicist. Please provide a detailed yet accessible explanation of the following quantum physics computation results.

Please output the explanation in BOTH Chinese and English.
You MUST separate the two languages using following block delimiters strictly on their own lines:

---START_ZH---
(Your Chinese explanation here)
---END_ZH---

---START_EN---
(Your English explanation here)
---END_EN---

Your explanation MUST cover the following key points in both versions:
1. What physical problem was solved (e.g., Infinite Square Well, Schrödinger equation, dimensionality, mass, spatial range, grid spacing, boundary conditions).
2. The Approach/Methodology computationally.
3. Note that the computation used `scipy.sparse.linalg.eigsh` (or dense `eigh`) to solve the discretized Hamiltonian matrix.
4. What results were returned (energy eigenvalues, computation time, orthogonality verification). If the natural unit energies were also given in SI units (Joules), mention them.
5. **Strict Physics Evaluation**: Check the physical significance of these specific energy levels and wavefunctions. YOU MUST ACT AS A STRICT EXAMINER. Does the result match analytical expectations (e.g., for an Infinite Square Well, $E_n = \\frac{{n^2 \\pi^2 \\hbar^2}}{{2 m L^2}} + V_0$ where $V_0$ is the potentialStrength)? Note that the computational solver incorporates the base potential depth $V_0$ into the total energy! If the calculation engine's eigenvalues match the theory within a few percent (e.g., $~8.60$ vs $8.66$), explain that this tiny discrepancy is entirely expected due to $O(dx^2)$ truncation errors inherent to the finite difference grid approximation. If the discrepancy is massive, explicitly state: "These numerical results mathematically deviate from the theoretical physics expectations (explain why) and are likely numerical artifacts caused by insufficient grid resolution."

The results JSON from the solver is as follows:
```json
{json.dumps(result_data, indent=2, ensure_ascii=False)}
```

Please output strictly in well-formatted Markdown. Use appropriate headers, bullet points, and LaTeX math blocks (e.g. `$E = mc^2$`) where helpful.
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
