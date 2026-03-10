# Dirac Solver — UI User Guide

> This guide explains every panel in the web interface, what each approximation method means, and how to perform post-processing visualizations step by step.

---

## Table of Contents
1. [Workflow Overview](#1-workflow-overview)
2. [System Configuration](#2-system-configuration)
3. [Periodic System Settings](#3-periodic-system-settings)
4. [Mesh & Box Settings (including non-uniform grid)](#4-mesh--box-settings)
5. [DFT Settings — XC Functional Reference](#5-dft-settings--xc-functional-reference)
6. [TD Propagation Settings](#6-td-propagation-settings)
7. [Post-Processing & Visualization](#7-post-processing--visualization)
8. [Common Workflows](#8-common-workflows)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Workflow Overview

```
Configure panels → Initiate Computation → Wait for logs → View Results
```

**Standard GS → TD workflow:**
1. Set molecule, XC functional, grid spacing
2. Run **Ground State** (`gs`) — verifies convergence, shows KS levels, wavefunction slices
3. Switch calc mode to **Time-Dependent** (`td`) — reads the GS restart files automatically  
4. Run TD — shows optical absorption spectrum and dipole moment time series  
5. All previous GS/TD results persist in the Results panel until page reload

> **Tip:** The Results panel remembers all past computation modes. After running GS then TD, you can still view GS wavefunctions alongside the TD optical spectrum.

---

## 2. System Configuration

### Dimensionality
| Value | Meaning |
|-------|---------|
| `1D` | Model system with analytic potential (Harmonic, Square Well…) |
| `2D` | Molecular geometry projected onto xy-plane |
| `3D` | Full 3D real-space molecular DFT (primary production mode) |

### Calculation Mode
| Mode | What it does |
|------|-------------|
| `gs` | Ground state DFT — SCF, eigenvalues, density, wavefunctions |
| `td` | TDDFT propagation — delta-kick, dipole spectrum → optical absorption |
| `unocc` | Diagonalizes unoccupied (virtual) KS states for deeper level analysis |
| `opt` | Geometry optimization — relaxes atomic positions to minimum energy |
| `em` | Electromagnetic / linear response (Casida TDDFT) |
| `vib` | Vibrational modes via finite differences (IR spectra) |

### Molecule Library

| Symbol | System | Notes |
|--------|--------|-------|
| H, He, Li, Na | Isolated atoms | Single-site pseudo-atom |
| H₂, LiH, CO, N₂ | Diatomics | Bond lengths in Bohr |
| H₂O, NH₃, CH₄, C₂H₄ | Polyatomics | Equilibrium geometry, Bohr coords |
| C₆H₆ (Benzene) | Aromatic | Planar D₆h, soft-core potentials |
| Si | FCC diamond crystal | Requires PeriodicDimensions = 3, auto-set |
| Al₂O₃ | Corundum (sapphire) | Requires PeriodicDimensions = 3, auto-set |

---

## 3. Periodic System Settings

**Periodic Dimensions** controls Bloch boundary conditions:

| Value | BCs | Use case |
|-------|-----|---------|
| 0 | Dirichlet (isolated) | Molecules, atoms |
| 1 | Periodic in x only | 1D chains / nanowires |
| 2 | Periodic in xy | 2D slabs / surfaces |
| 3 | Fully periodic | Bulk crystals |

**Lattice constants a, b, c** — primitive lattice vectors in Bohr. For Si (FCC diamond), defaults are pre-filled.

**K-Points Grid** — Monkhorst-Pack sampling, e.g. `4 4 4`. Use `1 1 1` for molecules (Γ-point only). More k-points = higher accuracy but slower.

> For periodic crystals (Si, Al₂O₃), selecting the molecule auto-sets `PeriodicDimensions = 3`.

---

## 4. Mesh & Box Settings

### Grid Spacing
The fundamental resolution parameter. **Smaller = more accurate, more RAM.**

| System | Recommended spacing |
|--------|-------------------|
| Isolated atom (H, He) | 0.40 Bohr |
| Small molecule (H₂O, NH₃) | 0.25–0.30 Bohr |
| Larger molecule (Benzene) | 0.20–0.25 Bohr |
| Si bulk crystal | 0.15–0.20 Bohr |
| High-accuracy benchmark | 0.10–0.15 Bohr |

RAM estimate: N ≈ (2×Radius/Spacing)³. For Radius=5, Spacing=0.3 → N ≈ 4913 grid points. Budget ≈ N × 8 bytes × num_states.

### Box Radius (Bohr)
Half-width of the simulation box. Must be large enough that the wavefunction decays to zero at the boundary.

| Molecule | Minimum radius |
|---------|---------------|
| H atom | 5 Bohr |
| H₂ | 5–7 Bohr |
| Benzene | 8–10 Bohr |
| Periodic (Si) | Determined by LatticeVectors |

### Box Shape
| Shape | Notes |
|-------|-------|
| Sphere | Default, uniform accuracy |
| Cylinder | Good for linear molecules |
| Parallelepiped | Required for periodic systems |
| Minimum | Overlapping spheres around each atom — smallest volume, efficient |

### FD Derivatives Order
Controls the finite-difference stencil accuracy.

| Order | When to use |
|-------|------------|
| 4 (default) | Standard calculations |
| 6 | Publications, bond lengths < 1 Bohr |
| 8 | Benchmark accuracy, forces |

### Non-Uniform Mesh (Curvilinear) — Gygi Method
The Gygi curvilinear transformation concentrates grid points near atomic nuclei where the wavefunction varies rapidly, while keeping fewer points in the interstitial region.

**When to use:**
- Systems where hard cores (C, N, O) demand fine grids but outer regions are smooth
- Reducing total grid count while maintaining accuracy near nuclei

**Gygi α parameter:** `0.1–1.0` (typical: `0.3–0.5`)
- Higher α = stronger concentration near nuclei
- `0.5` is a good starting point; increase if SCF converges poorly with uniform grid

**Note:** Does not replace `DerivativesOrder` — both settings work together.

### Double Grid
Enables a secondary fine grid for better evaluation of the ionic pseudopotential projectors. Recommended when using hard pseudopotentials (e.g. 1st-row atoms: C, N, O, F). Adds ~30% overhead.

---

## 5. DFT Settings — XC Functional Reference

The exchange-correlation (XC) functional is the key approximation in DFT. Selector is tiered: **Category → Preset → Optional override**.

### LDA — Local Density Approximation

| Preset | Full name | When to use |
|--------|----------|-------------|
| `PZ81` (default) | Perdew-Zunger 1981 | Quick tests, atoms |
| `PW92` | Perdew-Wang 1992 | Marginally more accurate LDA |
| `VWN5` | Vosko-Wilk-Nusair | Standard in solid-state codes |
| `X-only LDA` | Exchange only, no correlation | Diagnostic / special studies |

**Accuracy:** LDA systematically underestimates band gaps and lattice constants by ~5–10%.

### GGA — Generalized Gradient Approximation

| Preset | Use case |
|--------|---------|
| **PBE** (recommended) | General-purpose, very widely validated |
| **BLYP** | Molecular chemistry, thermochemistry |
| **PBEsol** | Solids and surfaces (better lattice constants) |
| **RPBE** | Chemisorption and surface reactions |

**Accuracy:** GGA corrects many LDA failures. PBE is the community default for solids; BLYP for molecules.

### Meta-GGA — 3rd Rung

| Preset | Strength |
|--------|---------|
| **SCAN** | State-of-the-art; respects all exact constraints |
| **TPSS** | Transition metals, magnetic systems |
| **M06-L** | Main-group thermochemistry, barriers |

**Accuracy:** Meta-GGA improves atomization energies and band gaps over GGA. SCAN is often a first choice if you want beyond-GGA without the cost of hybrids.

### Hybrid — Exact HF Exchange Mix

| Preset | HF fraction | Typical use |
|--------|------------|-------------|
| **B3LYP** | 20% | Organic chemistry, thermochemistry — most cited functional |
| **PBE0 (PBEH)** | 25% | General solid state + molecules |
| **HSE06** | 25% (screened) | Large-gap semiconductors; O(N) cost at large cell |

**Note:** Hybrids require exact-exchange evaluation — roughly 5–30× slower than GGA. Use for final accurate results, not exploratory runs.

### Exact Exchange / OEP
| Preset | Description |
|--------|------------|
| **Hartree-Fock** | Pure exchange, no correlation; reference for error analysis |
| **KLI approximation** | Krieger-Li-Iafrate OEP; local version of exact exchange |
| **Slater approximation** | Slater local approximation of exchange |

**Note:** OEP and HF are mapped internally to valid Octopus variables (`OEPLevel`). If you receive a parser error, use the manual override field with the exact libxc string.

### Manual Override
Enter any valid libxc functional string directly, e.g.:
```
gga_x_pbe+gga_c_pbe
mgga_x_scan+mgga_c_scan
hyb_gga_xc_b3lyp
```
Leave blank to use the preset above. Active functional is displayed below the override box.

---

## 6. TD Propagation Settings (calcMode = `td`)

| Parameter | Meaning | Typical value |
|-----------|---------|--------------|
| Max Steps | Number of TD time steps | 200 (DEV) → 3000+ (production) |
| Time Step | Δt in atomic units | 0.05 a.u. (stable) |
| Propagator | Numerical integration scheme | AETRS (recommended) |

### Propagator options
| Name | Description |
|------|-------------|
| AETRS | Approximated Enforced Time-Reversal Symmetry — best general choice |
| ETRS | Exact time-reversal enforced — more expensive but very accurate |
| exp0 | Simple exponential, 1st order — fast but less stable |

### What TD mode computes
1. Runs GS first (if not already converged) to get ground-state KS orbitals
2. Applies a delta-kick perturbation (direction: x by default)
3. Propagates KS equations in time
4. Parses `td.general/multipoles` → dipole moment `d(t)`
5. FFT of `d(t)` → optical absorption `σ(ω)` via `oct-propagation_spectrum`

---

## 7. Post-Processing & Visualization

### Persistent History
All computations (GS, TD, unocc…) are stored in session history. The Results panel uses all available data:
- After GS: shows KS level diagram, wavefunction slices, SCF convergence, density, DOS
- After TD: additionally shows optical absorption spectrum and TD dipole panels
- Both GS and TD panels remain visible even after switching modes

### KS Energy Level Diagram
Shows Kohn-Sham orbital energies. HOMO is green, LUMO is red. The gap box is cyan-shaded.

### SCF Convergence Chart
log₁₀(ΔE) per iteration. A well-converged calculation shows a steep monotonic descent to below -5 or -6.

### Wavefunction Slice ψₙ(x)
1D cut along the x-axis at y=0, z=0. Generated by `OutputFormat = axis_x` in Octopus.
- To view a different state: use the state selector buttons

### Electron Density n(x)
Summed density from all occupied KS states, plotted as n(x) along x-axis.

### Density of States (DOS)
Broadened eigenvalue spectrum. HOMO position marked as dashed green line.

### Optical Absorption Spectrum (TD mode)
σ(ω) in Å²/eV plotted vs. photon energy (eV). Peaks correspond to optical transition frequencies.

### TD Dipole Moment d(t)
Time-domain dipole response after delta-kick. Use axis selector (dₓ/d_y/d_z) to view different polarization components.

### Band Structure (periodic systems)
E(k) bands plotted along k-path. Fermi energy shown as dashed line. Available after GS or unocc calculation on periodic systems.

### Charge Density Difference Δρ(x)
Δρ = ρ_molecule − Σρ_atoms. Positive (green) = charge accumulation; negative (red) = depletion. Shows bonding character.

### 3D Visualization via VisIt

**Prerequisites:**
- VisIt 3.4.2 installed at `D:\Softwares_new\VisIt\LLNL\VisIt3.4.2\visit.exe` (as configured in `.env`)
- A successful GS calculation must have been run first (produces `wf-st00001.y=0,z=0`, `density.y=0,z=0` in `@Octopus_docs/output/`)

**Plot types:**
| Type | Input file | Notes |
|------|-----------|-------|
| Wavefunction 1D | `wf-st00001.y=0,z=0` | Fast matplotlib render |
| Density 2D slice | `density.y=0,z=0` | Fast matplotlib render |
| Density 3D isosurface | `density.y=0,z=0` | VisIt required |

**Steps:**
1. Run a GS calculation first 
2. Verify `static/info` shows "SCF converged"
3. In the Results panel, scroll to the VisIt section
4. Select a plot type and click **▶ Render**
5. Wait for the PNG image to appear (~3–10 seconds)

**Troubleshooting VisIt:**
- `Data file not found` → Run a GS calculation first
- `VisIt not found` → Check `VISIT_EXE` in `.env`
- `not_available` → VisIt executable path is wrong or VisIt is not installed

---

## 8. Common Workflows

### H₂ Ground State
1. Molecule: H₂, Mode: gs, XC: LDA-PZ81
2. Grid Spacing: 0.3, Radius: 6.0, Shape: Sphere
3. Derivatives: 4th order, Mesh: Uniform
4. Extra States: 2
5. Click **Initiate Computation** → should converge in ~6–10 SCF iterations

### H₂ Optical Spectrum (TD)
1. First run H₂ GS and confirm convergence
2. Switch Mode to **td**, set Max Steps: 1000, Time Step: 0.05, Propagator: AETRS
3. Click **Initiate Computation** — Octopus restarts from GS, propagates, then computes spectrum
4. View optical absorption σ(ω) in the TD panel

### H₂O Geometry Optimization
1. Molecule: H₂O, Mode: opt, XC: GGA-PBE  
2. Grid Spacing: 0.25, Radius: 7.0
3. Run → relaxed geometry is printed in stdout log

### Si Band Structure (Bulk)
1. Molecule: Si (auto-sets PeriodicDimensions=3 and FCC lattice vectors)
2. Mode: gs, XC: GGA-PBE
3. K-points: 4 4 4, Spacing: 0.2
4. Run → band structure data available in Results if `unocc` or `band` output is configured

---

## 9. Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Parser error: symbol 'oep_slater' used before being defined` | OEP XC names need Octopus OEPLevel syntax | Upgrade to latest server.py (auto-handled) — or use the Override field to enter `lda_x` |
| `SCF did not converge in 0 iterations` | XC functional error or bad parameters | Fix XC functional; check Spacing ≤ 0.4 |
| `Data file not found: wf-st00001.y=0,z=0` | GS not yet run or failed | Run a GS calculation first; verify "SCF converged" in logs |
| `Memory error` / Octopus OOM | Grid too fine or box too large | Increase Spacing (e.g. 0.3→0.4) or decrease Radius |
| `VisIt not found` | VISIT_EXE env var wrong | Set `VISIT_EXE=<path>` in `.env` |
| `Computation complete` but 0 eigenvalues | GS failed before parsing | Check full log for Octopus error message |
| Results panel empty after TD | TD ran but had no previous GS | Always run GS mode before TD |
