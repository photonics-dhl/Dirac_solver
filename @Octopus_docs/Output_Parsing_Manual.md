# Octopus Output Parsing Manual

Reference for MCP server (`docker/workspace/server.py`) to parse all Octopus output files.  
All patterns here assume the compute runs inside Docker with outputs at `/workspace/output/`.

---

## 1. `static/info` — Regex-Based Parsing

This is always the first file to parse after a GS run.

### 1.1 Complete Parser Function

```python
import re
from typing import TypedDict, Optional

class EigenvalueEntry(TypedDict):
    state: int
    spin: str
    eigenvalue_hartree: float
    occupation: float

class StaticInfoResult(TypedDict):
    converged: bool
    scf_iterations: Optional[int]
    total_energy_hartree: Optional[float]
    eigenvalues: list[EigenvalueEntry]
    homo_hartree: Optional[float]
    lumo_hartree: Optional[float]
    homo_lumo_gap_eV: Optional[float]
    dipole_debye: Optional[list[float]]

def parse_static_info(path: str) -> StaticInfoResult:
    with open(path, "r") as f:
        text = f.read()

    # --- Convergence ---
    conv_match = re.search(r"SCF converged in\s+(\d+)\s+iterations", text)
    converged = conv_match is not None
    scf_iter = int(conv_match.group(1)) if conv_match else None

    # --- Total Energy ---
    energy_match = re.search(r"Total\s*=\s*([-\d.eE+]+)", text)
    total_energy = float(energy_match.group(1)) if energy_match else None

    # --- Eigenvalues ---
    # Matches table under "Eigenvalues [H]" header
    ev_block = re.search(
        r"#st\s+Spin\s+Eigenvalue\s+\[H\]\s+Occupation([\s\S]+?)(?:\n\n|\Z)",
        text
    )
    eigenvalues: list[EigenvalueEntry] = []
    if ev_block:
        for row in re.finditer(
            r"^\s*(\d+)\s+(\S+)\s+([-\d.eE+]+)\s+([\d.]+)", ev_block.group(1), re.MULTILINE
        ):
            eigenvalues.append({
                "state": int(row.group(1)),
                "spin": row.group(2),
                "eigenvalue_hartree": float(row.group(3)),
                "occupation": float(row.group(4)),
            })

    # --- HOMO / LUMO ---
    occupied = [e for e in eigenvalues if e["occupation"] > 0.5]
    unoccupied = [e for e in eigenvalues if e["occupation"] < 0.5]
    homo = occupied[-1]["eigenvalue_hartree"] if occupied else None
    lumo = unoccupied[0]["eigenvalue_hartree"] if unoccupied else None
    gap_eV = (lumo - homo) * 27.2114 if (homo is not None and lumo is not None) else None

    # --- Dipole ---
    dip_match = re.search(
        r"Dipole\s*(?:\[Debye\])?\s*[:=]?\s*"
        r"\(\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*\)",
        text
    )
    dipole = [float(dip_match.group(i)) for i in (1, 2, 3)] if dip_match else None

    return {
        "converged": converged,
        "scf_iterations": scf_iter,
        "total_energy_hartree": total_energy,
        "eigenvalues": eigenvalues,
        "homo_hartree": homo,
        "lumo_hartree": lumo,
        "homo_lumo_gap_eV": gap_eV,
        "dipole_debye": dipole,
    }
```

### 1.2 Minimal Quick-Parse (for retry loop decision)

```python
def quick_convergence_check(info_path: str) -> tuple[bool, int]:
    """Returns (converged, num_iterations). Fast path for retry decisions."""
    with open(info_path, "r") as f:
        text = f.read()
    m = re.search(r"SCF converged in\s+(\d+)\s+iterations", text)
    return (m is not None, int(m.group(1)) if m else 0)
```

---

## 2. `static/convergence` — Tabular ASCII Parse

```python
import numpy as np

def parse_convergence(path: str) -> dict:
    """
    Returns convergence trajectory.
    Columns depend on Octopus version; typical: iter, energy_diff, abs_dens, rel_dens
    """
    data = np.loadtxt(path, comments="#")
    if data.ndim == 1:
        data = data.reshape(1, -1)  # single-iteration edge case
    return {
        "iterations": data[:, 0].tolist(),
        "energy_diff": data[:, 1].tolist(),
        "abs_dens": data[:, 2].tolist() if data.shape[1] > 2 else [],
    }
```

---

## 3. Wavefunction ASCII Files (`static/wf-stNNNNN.y=0,z=0`)

These are 1D slices already — safe to load directly.

```python
import numpy as np, os, gc

def parse_wavefunction_1d(run_dir: str, state_index: int = 1) -> dict:
    """
    Parses the 1D wavefunction slice for state `state_index`.
    Returns x-axis (Bohr), real part, imaginary part, and |ψ|².
    """
    filename = f"wf-st{state_index:05d}.y=0,z=0"
    path = os.path.join(run_dir, "static", filename)

    data = np.loadtxt(path, comments="#")
    x      = data[:, 0].tolist()
    wf_re  = data[:, 1].tolist()
    wf_im  = data[:, 2].tolist() if data.shape[1] > 2 else [0.0] * len(x)
    prob   = (data[:, 1]**2 + (data[:, 2]**2 if data.shape[1] > 2 else 0)).tolist()

    del data; gc.collect()
    return {"x_bohr": x, "wf_real": wf_re, "wf_imag": wf_im, "probability_density": prob}


def list_available_wavefunctions(run_dir: str) -> list[int]:
    """Returns list of available state indices from filenames."""
    static_dir = os.path.join(run_dir, "static")
    states = []
    for f in os.listdir(static_dir):
        m = re.match(r"wf-st(\d+)\.y=0,z=0", f)
        if m:
            states.append(int(m.group(1)))
    return sorted(states)
```

---

## 4. NetCDF Density Files (`static/density.nc`)

**Anti-OOM rule**: Always extract slice, never return full 3D array to Node.js.

```python
import xarray as xr, gc

def parse_density_1d_slice(nc_path: str) -> dict:
    """
    Extracts the 1D density profile along x at y=0, z=0.
    Safe for 3D runs — does not load full volume.
    """
    ds = xr.open_dataset(nc_path, engine="scipy")
    try:
        # Select 1D slice
        rho = ds["density"].sel(y=0.0, z=0.0, method="nearest")
        x_coords = rho.coords["x"].values.tolist()
        density_values = rho.values.tolist()
        return {"x_bohr": x_coords, "density": density_values}
    finally:
        ds.close()
        gc.collect()


def probe_density_metadata(nc_path: str) -> dict:
    """
    Returns shape, min, max without loading full data.
    MUST be called before slice extraction to verify grid size.
    """
    ds = xr.open_dataset(nc_path, engine="scipy")
    try:
        d = ds["density"]
        return {
            "shape": list(d.shape),
            "dims": list(d.dims),
            "min": float(d.min()),
            "max": float(d.max()),
            "n_points_total": int(d.size),
        }
    finally:
        ds.close()
        gc.collect()
```

---

## 5. TD Dipole (`td.general/dipole`)

```python
import numpy as np, gc

def parse_td_dipole(path: str) -> dict:
    """
    Parses TDDFT dipole output.
    Returns time series (Hartree-time) and x/y/z dipole components (Bohr).
    """
    data = np.loadtxt(path, comments="#")
    result = {
        "time_au":  data[:, 0].tolist(),
        "dipole_x": data[:, 1].tolist(),
        "dipole_y": data[:, 2].tolist(),
        "dipole_z": data[:, 3].tolist(),
    }
    del data; gc.collect()
    return result


def compute_absorption_spectrum(dipole_path: str, polarization: str = "x") -> dict:
    """
    Computes the optical absorption spectrum via FFT of the dipole signal.
    Returns frequency array (eV) and oscillator strength proxy.
    """
    data = np.loadtxt(dipole_path, comments="#")
    time = data[:, 0]
    col_map = {"x": 1, "y": 2, "z": 3}
    d = data[:, col_map[polarization]]
    dt = time[1] - time[0]

    freq_au = np.fft.rfftfreq(len(d), d=dt)
    strength = np.abs(np.fft.rfft(d)) ** 2
    freq_eV = (freq_au * 27.2114).tolist()

    del data, d; gc.collect()
    return {"frequency_eV": freq_eV, "oscillator_strength": strength.tolist()}
```

---

## 6. Aggregated MCP Tool: `parse_octopus_results`

This is the primary MCP tool to add to `docker/workspace/server.py`:

```python
@mcp.tool()
async def parse_octopus_results(run_dir: str) -> dict:
    """
    Parses all available Octopus output for a completed GS run.
    Returns structured JSON safe to forward directly to the LangGraph node.
    """
    static_dir = os.path.join(run_dir, "static")
    result: dict = {"run_dir": run_dir, "mode": "gs"}

    # 1. Parse static/info
    info_path = os.path.join(static_dir, "info")
    if os.path.exists(info_path):
        result["info"] = parse_static_info(info_path)

    # 2. Parse convergence
    conv_path = os.path.join(static_dir, "convergence")
    if os.path.exists(conv_path):
        result["convergence"] = parse_convergence(conv_path)

    # 3. List and parse first wavefunction (1D slice)
    available_states = list_available_wavefunctions(run_dir)
    result["available_states"] = available_states
    if available_states:
        result["wavefunction_state1"] = parse_wavefunction_1d(run_dir, available_states[0])

    # 4. Probe NetCDF density if present (metadata only — never load full 3D)
    nc_path = os.path.join(static_dir, "density.nc")
    if os.path.exists(nc_path):
        result["density_metadata"] = probe_density_metadata(nc_path)
        # Only extract 1D slice if grid is tractable
        meta = result["density_metadata"]
        if meta["n_points_total"] < 50_000:
            result["density_1d_slice"] = parse_density_1d_slice(nc_path)

    gc.collect()
    return result
```

---

## 7. HDF5 / `.obf` Binary Files (Advanced)

Octopus `.obf` files are proprietary binary restart files — they are **not** for direct parsing.  
Use the Python `oct-convert` utility inside the Docker container:

```bash
# Inside Docker: convert OBF to NetCDF for easier parsing
oct-convert -i restart/gs/density.obf -o /workspace/output/density_converted.nc
```

For HDF5 outputs (when `OutputFormat = hdf5`):

```python
import h5py, gc

def parse_hdf5_density(h5_path: str) -> dict:
    with h5py.File(h5_path, "r") as f:
        # Standard key for density in Octopus HDF5 output
        rho = f["density"][:]          # shape: (Nz, Ny, Nx) — note reverse order
        # Extract central axis slice
        iz, iy = rho.shape[0] // 2, rho.shape[1] // 2
        slice_1d = rho[iz, iy, :].tolist()
    del rho; gc.collect()
    return {"density_central_axis": slice_1d}
```

---

## 8. Output Summary JSON Schema (TypeScript)

The following Zod schema should be used in `src/langgraph_agent.ts` to type the MCP response:

```typescript
import { z } from "zod";

const EigenvalueSchema = z.object({
  state: z.number().int(),
  spin: z.string(),
  eigenvalue_hartree: z.number(),
  occupation: z.number(),
});

const ParsedResultsSchema = z.object({
  run_dir: z.string(),
  mode: z.enum(["gs", "td"]),
  info: z.object({
    converged: z.boolean(),
    scf_iterations: z.number().int().nullable(),
    total_energy_hartree: z.number().nullable(),
    eigenvalues: z.array(EigenvalueSchema),
    homo_hartree: z.number().nullable(),
    lumo_hartree: z.number().nullable(),
    homo_lumo_gap_eV: z.number().nullable(),
    dipole_debye: z.array(z.number()).length(3).nullable(),
  }).optional(),
  convergence: z.object({
    iterations: z.array(z.number()),
    energy_diff: z.array(z.number()),
    abs_dens: z.array(z.number()),
  }).optional(),
  available_states: z.array(z.number().int()),
  wavefunction_state1: z.object({
    x_bohr: z.array(z.number()),
    wf_real: z.array(z.number()),
    wf_imag: z.array(z.number()),
    probability_density: z.array(z.number()),
  }).optional(),
  density_metadata: z.object({
    shape: z.array(z.number().int()),
    dims: z.array(z.string()),
    min: z.number(),
    max: z.number(),
    n_points_total: z.number().int(),
  }).optional(),
  density_1d_slice: z.object({
    x_bohr: z.array(z.number()),
    density: z.array(z.number()),
  }).optional(),
});

export type ParsedOctopusResults = z.infer<typeof ParsedResultsSchema>;
```
