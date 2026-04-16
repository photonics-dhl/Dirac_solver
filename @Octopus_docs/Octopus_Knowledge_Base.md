# Octopus 16 — Comprehensive Knowledge Base 🐙

> **Version**: Octopus 16.3 (branch `16.3`) | Last updated: 2026-03. Based on https://octopus-code.org/documentation/16/  
> **Purpose**: Authoritative reference for generating `inp` files, parsing output, and driving the LangGraph → MCP pipeline.

---

## Tree: Octopus Capabilities

```
Octopus
├── I.   Calculation Modes         (CalculationMode)
├── II.  System Definition         (coordinates, species, dimensions, periodicity)
├── III. Grid / Mesh               (box shape, spacing, curvilinear, k-points)
├── IV.  DFT Hamiltonian           (XC functional, Poisson solver, DFT+U, relativistic)
├── V.   SCF Ground State          (eigensolver, mixing, convergence)
├── VI.  Time-Dependent (TDDFT)    (propagators, external fields, absorbing boundaries)
├── VII. Linear Response           (Casida, Sternheimer, polarizabilities, vibrational)
├── VIII.Output & Post-processing  (static output, TD output, utilities)
└── IX.  Execution & Parallelization (MPI, GPU, memory)
```

---

## I. Calculation Modes

`CalculationMode = <value>` — controls what Octopus computes.

| Value | Description | Prerequisites |
|:------|:------------|:--------------|
| `gs` | Ground State SCF — find KS ground state via self-consistent DFT | none |
| `td` | Time-Dependent DFT — propagate electrons under time-dependent Hamiltonian | converged GS in `restart/gs/` |
| `unocc` | Unoccupied States — compute extra (virtual) KS orbitals | converged GS |
| `opt` | Geometry Optimization — minimize forces via BFGS/FIRE | none (runs internal GS loops) |
| `em` | Electromagnetic response — static/frequency-dependent linear response | converged GS |
| `vib` | Vibrational Modes — phonons via finite differences | converged GS + `opt` |
| `casida` | Casida TDDFT — excited states via TDDFT matrix diagonalization | converged GS + `unocc` |
| `invert_ks` | Invert KS potential from density | external density file |

---

## II. System Definition

### 2.1 Dimensionality

```octopus
Dimensions = 3          # 1, 2, or 3
PeriodicDimensions = 0  # 0 = isolated; 1,2,3 = periodic directions
```

### 2.2 Coordinates

Three formats supported:
```octopus
# Inline (Bohr by default in atomic units mode)
%Coordinates
  "H"  | 0.0 | 0.0 | -0.7
  "H"  | 0.0 | 0.0 |  0.7
%

# External XYZ file
XYZCoordinates = "molecule.xyz"

# Reduced (fractional, only for periodic systems)
%ReducedCoordinates
  "Si" | 0.0 | 0.0 | 0.0
  "Si" | 0.25 | 0.25 | 0.25
%
```

**Unit handling**: Default = atomic units (Bohr / Hartree). To use Angstrom/eV:
```octopus
Units = eV_Angstrom
```

### 2.3 Species (Pseudopotentials)

#### 2.3.1 Built-in Pseudopotential Sets

```octopus
PseudopotentialSet = hgh_lda    # Hartwigsen-Goedecker-Hutter, LDA (default)
# Other options (if installed): hgh_lda_sc, pbe, upf, ...
```
When using a pseudopotential set, **omit** the `%Species` block — Octopus finds the PP automatically from the coordinate element symbol.

#### 2.3.2 Manual Species Block (Formula-Based / All-Electron)

```octopus
%Species
  "H"   | species_user_defined | potential_formula | "-1/sqrt(r^2+0.01)" | valence | 1
  "He"  | species_user_defined | potential_formula | "-2/sqrt(r^2+0.01)" | valence | 2
  "C"   | species_user_defined | potential_formula | "-4/sqrt(r^2+0.01)" | valence | 4
  "N"   | species_user_defined | potential_formula | "-5/sqrt(r^2+0.01)" | valence | 5
  "O"   | species_user_defined | potential_formula | "-6/sqrt(r^2+0.01)" | valence | 6
  "Li"  | species_user_defined | potential_formula | "-1/sqrt(r^2+0.01)" | valence | 1
  "Na"  | species_user_defined | potential_formula | "-1/sqrt(r^2+0.04)" | valence | 1
  "Si"  | species_user_defined | potential_formula | "-4/sqrt(r^2+0.01)" | valence | 4
%
```
> **Note**: The softening radius (`0.01`, `0.04`) prevents divergence at `r=0`. Larger values = softer pseudopotential. For heavy elements (Z>10), increasing the softening may be needed.

#### 2.3.3 All-Electron Species

```octopus
AllElectronType = all_electron_exact   # full AE, very expensive
AllElectronType = all_electron_anc     # approximate norm-conserving
```

### 2.4 Molecular Library (Formula-Based, Bohr coordinates)

| Molecule | Formula | 3D Coordinates (Bohr) |
|:---------|:--------|:---------------------|
| H atom | -1/√(r²+0.01) | (0,0,0) |
| He atom | -2/√(r²+0.01) | (0,0,0) |
| Li atom | -1/√(r²+0.01) [1e] | (0,0,0) |
| Na atom | -1/√(r²+0.04) [1e] | (0,0,0) |
| H₂ | H-formula | H@(0,0,±0.7) |
| LiH | Li+H | Li@(0,0,-1.511), H@(0,0,1.511) |
| CO | C+O | C@(0,0,-1.066), O@(0,0,1.066) |
| N₂ | N-formula | N@(0,0,±1.03) |
| H₂O | O+2H | O@(0,0,0), H@(±1.430,0,-1.107) |
| NH₃ | N+3H | N@0, H at pyramid verts |
| CH₄ | C+4H | C@0, H at tetrahedral verts |
| C₂H₄ | C+4H | C@(0,0,±1.261), H@(±1.745,0,±2.332) |
| Benzene | C+6H | Planar hexagon in xy, d(C-C)=2.64 Bohr |
| Si bulk | Si-formula [periodic] | FCC diamond, a=10.263 Bohr |

### 2.5 Periodic Systems

```octopus
PeriodicDimensions = 3

# Lattice vectors (Bohr) — FCC primitive for Si:
%LatticeVectors
  0.0   | 5.132 | 5.132
  5.132 | 0.0   | 5.132
  5.132 | 5.132 | 0.0
%

# Reduced coordinates:
%ReducedCoordinates
  "Si" | 0.0  | 0.0  | 0.0
  "Si" | 0.25 | 0.25 | 0.25
%

# K-point grid (Monkhorst-Pack):
%KPointsGrid
  4 | 4 | 4
%
```

---

## III. Grid / Mesh

### 3.1 Key Variables

| Variable | Description | DEV range | PROD range |
|:---------|:------------|:----------|:-----------|
| `Spacing` | Grid resolution (Bohr) | 0.3–0.5 | 0.1–0.2 |
| `Radius` | Box half-size (Bohr) | 3.0–5.0 | 5.0–20.0 |
| `BoxShape` | `sphere`, `minimum`, `parallelepiped`, `cylinder`, `user_defined` | sphere | minimum |
| `Lsize` | Half-length per axis (for parallelepiped) | — | — |

### 3.2 Box Shapes

```octopus
BoxShape = sphere          # Sphere of given Radius
BoxShape = minimum         # Union of spheres centered on atoms (molecules)
BoxShape = parallelepiped  # Rectangular box, use Lsize
BoxShape = cylinder        # Cylinder, use Radius + Lsize
```

### 3.3 Non-Uniform / Curvilinear Grids

Enable adaptive grid refinement near nuclei:
```octopus
CurvMethod = gygi_bader      # Gygi-Bader adaptive coords (recommended)
CurvGygiA    = 0.5           # Refinement strength
CurvGygiAlpha = 0.5          # Scale parameter
CurvGygiBeta  = 0.5

# Alternative: Modine curvilinear
CurvMethod = modine
```

### 3.4 K-Points (Periodic Systems)

```octopus
# Monkhorst-Pack grid
%KPointsGrid
  4 | 4 | 4
%
KPointsUseSymmetries = yes  # Reduce to irreducible BZ

# Band structure path
%KPointsPath
  10            # points per segment
  0 0 0         # Gamma
  0.5 0 0.5     # X
  0.5 0.25 0.75 # W
%
```

---

## IV. DFT Hamiltonian

### 4.1 XC Functionals (via libxc)

`XCFunctional = <exchange>+<correlation>` — uses libxc functional codes.

#### Category: LDA (Local Density Approximation)
| libxc string | Name | Notes |
|:-------------|:-----|:------|
| `lda_x+lda_c_pz` | LDA-PZ (Perdew-Zunger 1981) | **Default**, reliable for atoms/molecules |
| `lda_x+lda_c_pw` | LDA-PW (Perdew-Wang 1992) | Slightly improved |
| `lda_x+lda_c_vwn` | LDA-VWN5 (Vosko-Wilk-Nusair) | Used in Gaussian |
| `lda_x` | LDA exchange only | Testing |

#### Category: GGA (Generalized Gradient Approximation)
| libxc string | Name | Notes |
|:-------------|:-----|:------|
| `gga_x_pbe+gga_c_pbe` | PBE (Perdew-Burke-Ernzerhof 1996) | Standard for solids |
| `gga_x_b88+gga_c_lyp` | BLYP | Common in chemistry |
| `gga_x_pbe_sol+gga_c_pbe_sol` | PBEsol | Better for solids/surfaces |
| `gga_x_rpbe+gga_c_pbe` | RPBE | Improved adsorption |

#### Category: Meta-GGA (3rd Rung)
| libxc string | Name | Notes |
|:-------------|:-----|:------|
| `mgga_x_scan+mgga_c_scan` | SCAN | State-of-the-art meta-GGA |
| `mgga_x_tpss+mgga_c_tpss` | TPSS | Good for transition metals |
| `mgga_x_m06l+mgga_c_m06l` | M06-L | Kinetics, main-group chemistry |

#### Category: Hybrid (Hartree-Fock Exchange Mix)
| libxc string | Name | Notes |
|:-------------|:-----|:------|
| `hyb_gga_xc_b3lyp` | B3LYP | Most used in chemistry |
| `hyb_gga_xc_pbeh` | PBE0 / PBEH | 25% HF exchange |
| `hyb_gga_xc_hse06` | HSE06 | Range-separated, k-space, best for solids |

#### Category: Exact Exchange / OEP
| libxc string | Override keyword | Notes |
|:-------------|:-----------------|:------|
| `hartree_fock` | — | Full HF, no DFT XC |
| — | `OEPLevel = oep_kli` | KLI approximation to exact exchange |
| — | `OEPLevel = oep_slater` | Slater approximation |

#### Category: vdW Corrections
```octopus
VDWCorrection = vdw_d3     # Grimme DFT-D3 (on top of any functional)
VDWCorrection = vdw_ts     # Tkatchenko-Scheffler
```

### 4.2 Poisson Solver (`PoissonSolver`)

| Value | Description | Use case |
|:------|:------------|:---------|
| `fft` | FFT-based (default for isolated) | Molecules, fast |
| `cgal` | Conjugate-gradient, full BC flexibility | Isolated |
| `multipole` | Multipole expansion | Large isolated systems |
| `isf` | ISF real-space (periodic or mixed) | 2D periodic |
| `psolver` | BigDFT PSolver library | Fully periodic |
| `direct` | Direct Poisson (small systems) | Testing |

```octopus
PoissonSolver = fft                # typical for isolated molecule
PoissonSolverBoundaries = zero     # zero BC (isolated)
# For periodic:
PoissonSolver = psolver
```

### 4.3 DFT+U

For strongly correlated systems (transition metal d/f orbitals):
```octopus
DFTULevel = acbn0        # ACBN0 self-consistent U
# or
DFTULevel = hubbard_u
```

### 4.4 Relativistic Corrections

```octopus
RelativisticCorrection = none           # non-relativistic (default)
RelativisticCorrection = scalar_rel     # scalar relativistic
RelativisticCorrection = spin_orbit     # requires non-collinear spin
```

### 4.5 Spin

```octopus
SpinComponents = unpolarized      # default
SpinComponents = spin_polarized   # collinear, up/down separate
SpinComponents = non_collinear    # 4-component spinor (required for SOC)
```

---

## V. SCF Ground State

### 5.1 Convergence Criteria

```octopus
MaximumIter = 200        # max SCF iterations
ConvAbsDens  = 1e-6     # absolute density convergence (default)
ConvRelDens  = 1e-5     # relative density convergence
ConvEnergy   = 1e-6     # total energy convergence (Hartree)
```

### 5.2 Eigensolver

```octopus
Eigensolver = cg         # Conjugate Gradient (default, robust)
Eigensolver = rmmdiis    # Residual Minimization, fast for large systems
Eigensolver = lobpcg     # Good for metals
EigensolverMaxIter = 25
EigensolverTolerance = 1e-6
```

### 5.3 Density Mixing

```octopus
MixingScheme = broyden        # Broyden (default, recommended)
MixingScheme = diis           # DIIS accelerator
MixingScheme = linear         # simple linear, most robust but slow
Mixing = 0.3                  # Mixing parameter (0.1–0.5)
MixNumberSteps = 7            # History length for Broyden/DIIS
```

### 5.4 Extra States

```octopus
ExtraStates = 4     # Number of extra (unoccupied) KS states to compute
```

---

## VI. Time-Dependent TDDFT

### 6.1 Propagators (`TDPropagator`)

| Value | Description | Recommended |
|:------|:------------|:------------|
| `aetrs` | Approximated Enforced Time-Reversal Symmetry | **Default — most robust** |
| `etrs` | Exact ETRS (iterative) | Higher accuracy, slower |
| `exp_mid` | Exponential midpoint | Fast, good for short pulses |
| `magnus` | Magnus series | High order |
| `runge_kutta` | RK4 | Simple testing |

```octopus
TDPropagator = aetrs
TDMaxSteps   = 1000          # Number of time steps
TDTimeStep   = 0.05          # Δt in atomic units (ℏ/Ha)
TDPropagationTime = 50.0    # Alternative to TDMaxSteps: total time
```

### 6.2 External Fields

#### Delta Kick (Compute Optical Spectrum)
The standard approach for absorption spectra:
```octopus
TDDeltaStrength = 0.01       # kick strength (a.u.) — 0.01 is standard
TDDeltaKickTime = 0.0        # kick at t=0
TDPolarizationDirection = 1  # x=1, y=2, z=3 (run x, y, z then average)
```

#### Monochromatic Laser
```octopus
%TDFunctions
  "laser" | tdf_from_expr | "sin(0.057*t)" | 1.0
%
%TDExternalFields
  electric_field | 1 | 0 | 0 | 0.05 | "laser"
%
```

#### Envelope Functions (for realistic pulses)
```octopus
%TDFunctions
  "env"   | tdf_gaussian | 0.35 | 200.0 | 0.0
  "pulse" | tdf_from_expr | "sin(0.057*t)"   # carrier
%
# Combine: multiply envelope × carrier in TDExternalFields
```

### 6.3 TD Output

```octopus
%TDOutput
  multipoles     # Dipole moment → optical spectrum via FT
  energy         # Total energy vs time
  td_occup       # Time-dependent occupations
%
TDOutputComputeInterval = 10    # write every N steps
```

### 6.4 Absorbing Boundaries (prevent reflection)

```octopus
AbsorbingBoundaries = cap         # complex absorbing potential
ABCapHeight = 0.2                 # imaginary potential strength
ABWidth = 2.0                     # absorbing region width (Bohr)
```

---

## VII. Linear Response

### 7.1 Casida TDDFT (Excited States)

```octopus
CalculationMode = casida
CasidaKohnShamStates = "1-10"    # KS state range for transition space
CasidaTheoryLevel = lda
```
Output: `casida/casida_spectrum.dat` — excitation energies and oscillator strengths.

### 7.2 Sternheimer (Frequency-Domain Response)

```octopus
CalculationMode = em
ResponseMethod = sternheimer
EMFreqs = range(0.0, 1.0, 0.02)  # frequency range in Hartree
```

### 7.3 Vibrational Modes

```octopus
CalculationMode = vib
Displacement = 0.01   # finite displacement in Bohr
```
Output: `vib_modes/` — frequencies in cm⁻¹, normal mode vectors.

---

## VIII. Output & Post-Processing

### 8.1 Output Variables

```octopus
%Output
  wfs           # Wavefunctions ψ_n(r)
  density       # Electron density n(r)
  potential     # KS potential v_ks(r)
  eigenvalues   # KS eigenvalues (also in static/info)
  dos           # Total DOS → static/total-dos.dat
  elf           # Electron Localization Function
  stress        # Stress tensor (periodic)
%

OutputFormat = axis_x         # 1D slice along x → *.y=0,z=0 files
# OutputFormat = vtu          # VTK unstructured (3D visualization)
# OutputFormat = netcdf       # NetCDF (use xarray to read)
# OutputFormat = cube         # Gaussian cube

OutputInterval = 50           # write every 50 TD steps (TD runs)
```

### 8.2 Static Output Files

| File/Dir | Content | Parsing |
|:---------|:--------|:--------|
| `static/info` | SCF summary: eigenvalues, energies, dipole | regex on `#st Spin Eigenvalue Occupation` block |
| `static/convergence` | SCF energy diff per iteration | whitespace-delimited: col0=iter, col2=ΔE |
| `static/total-dos.dat` | DOS vs energy (Hartree) | col0=E[H], col1=DOS |
| `static/wf-st00001.y=0,z=0` | 1D wavefunction slice (axis_x mode) | col0=x, col1=Re(ψ), col2=Im(ψ) |
| `static/density.y=0,z=0` | 1D density slice | col0=x, col1=n(x) |
| `static/vks.y=0,z=0` | KS potential 1D slice | col0=x, col1=V(x) |
| `static/v0.y=0,z=0` | External potential 1D slice | col0=x, col1=V₀(x) |

### 8.3 TD Output Files

| File | Content | Parsing |
|:-----|:--------|:--------|
| `td.general/multipoles` | Dipole vs time | col1=t, col2=dx, col3=dy, col4=dz |
| `td.general/energy` | Total energy vs time | col1=t, col2=E_total |
| `cross_section_vector` | Optical absorption spectrum | 5-col: energy(H), Im(α_xx), Re(α_xx), ... |

### 8.4 Post-Processing Utilities

| Utility | Purpose | Command |
|:--------|:--------|:--------|
| `oct-propagation_spectrum` | FT dipole → cross_section_vector | `oct-propagation_spectrum` (reads inp) |
| `oct-casida_spectrum` | Broaden Casida transitions | `oct-casida_spectrum` |
| `oct-convert` | Convert output formats (cube→vtu, etc.) | `oct-convert` |
| `oct-xyz-anim` | Animate MD trajectory | `oct-xyz-anim` |
| `oct-unfold` | Band unfolding for supercells | `oct-unfold` |
| `oct-wannier90` | Interface to Wannier90 | `oct-wannier90` |

---

## IX. Execution

### 9.1 MPI Parallelization

```octopus
ParDomains  = 4    # Parallelize over real-space domains
ParStates   = 2    # Parallelize over KS states
ParKPoints  = 2    # Parallelize over k-points (periodic)
```

### 9.2 GPU Acceleration

```octopus
AccelDevice = gpu
DisableAccel = no
```

### 9.3 Memory & Restart

```octopus
RestartWrite = yes            # Write restart files
RestartWriteInterval = 100    # Frequency (iterations)
FromScratch = yes             # Ignore existing restart (force fresh start)
```

---

## X. Complete Recipe Templates

### 10.1 H₂ Ground State (DEV mode)
```octopus
CalculationMode = gs
Dimensions = 3
BoxShape = sphere
Radius = 5.0
Spacing = 0.3

%Species
  'H' | species_user_defined | potential_formula | "-1/sqrt(r^2+0.01)" | valence | 1
%
%Coordinates
  'H' | 0 | 0 | -0.7
  'H' | 0 | 0 |  0.7
%

XCFunctional = lda_x+lda_c_pz
MixingScheme = broyden
ExtraStates = 4

%Output
  wfs | density | potential | dos
%
OutputFormat = axis_x
```

### 10.2 H₂ TD Optical Spectrum (DEV mode)
After converging GS above, run:
```octopus
CalculationMode = td
Dimensions = 3
BoxShape = sphere
Radius = 5.0
Spacing = 0.3

%Species
  'H' | species_user_defined | potential_formula | "-1/sqrt(r^2+0.01)" | valence | 1
%
%Coordinates
  'H' | 0 | 0 | -0.7
  'H' | 0 | 0 |  0.7
%

XCFunctional = lda_x+lda_c_pz
TDPropagator = aetrs
TDMaxSteps = 200
TDTimeStep = 0.05
TDDeltaStrength = 0.01
TDDeltaKickTime = 0.0
TDPolarizationDirection = 1

%TDOutput
  multipoles | energy
%
```
Then post-process: `oct-propagation_spectrum -i inp` → `cross_section_vector`

### 10.3 Si Bulk Band Structure (periodic, PROD mode)
```octopus
CalculationMode = gs
Dimensions = 3
PeriodicDimensions = 3

%LatticeVectors
  0.0   | 5.132 | 5.132
  5.132 | 0.0   | 5.132
  5.132 | 5.132 | 0.0
%

%ReducedCoordinates
  "Si" | 0.0  | 0.0  | 0.0
  "Si" | 0.25 | 0.25 | 0.25
%

PseudopotentialSet = hgh_lda
XCFunctional = lda_x+lda_c_pz
Spacing = 0.15
%KPointsGrid
  4 | 4 | 4
%
ExtraStates = 4
%Output
  eigenvalues | dos | density
%
```

---

## XI. Physical Constants & Unit Conversion

| Quantity | Atomic Unit | SI/CGS equivalent |
|:---------|:------------|:-----------------|
| Energy | 1 Hartree (Ha) | 27.2114 eV = 627.51 kcal/mol |
| Length | 1 Bohr (a₀) | 0.52918 Å |
| Time | 1 ℏ/Ha | 24.19 as (attoseconds) |
| Electric field | 1 Ha/e·a₀ | 5.142 × 10¹¹ V/m |
| Frequency | 1 Ha/ℏ | 6.58 × 10¹⁵ Hz |

---

## XII. Known Limitations & Troubleshooting

| Issue | Likely Cause | Fix |
|:------|:-------------|:----|
| `SCF not converged` | Mixing unstable or grid too coarse | Reduce `Mixing` to 0.1, switch to `MixingScheme = linear` |
| Eigenvalue suspiciously positive (unbound) | `Radius` too small, electron escapes box | Increase `Radius` |
| OOM / segfault | Grid too fine for available RAM | Coarsen `Spacing`, reduce `Radius` |
| Negative HOMO (expected) but wrong value | Softening too large in formula potential | Reduce softening: `0.001` for H |
| `species not found` error | Element not in pseudopotential database | Add explicit `%Species` block with formula |
| TD dipole flat (no response) | `TDDeltaStrength = 0` or kick not applied | Check `TDDeltaStrength > 0` and `TDDeltaKickTime = 0` |
| `cross_section_vector` file missing | `oct-propagation_spectrum` not run | Always run utility after TD calculation |

## 1. Core Syntax and Structural Concepts

### Input File Structure (`inp`)
- **Key-Value Pairs**: `Variable = Value` (e.g., `CalculationMode = gs`).
- **Blocks**: Used for multi-column data like coordinates or species.
  ```octopus
  %BlockName
    Value1 | Value2 | Value3
  %
  ```
- **Delimiters**: Columns in blocks are separated by the pipe `|`.
- **Case Insensitivity**: Variable names are generally case-insensitive.
- **Unit Handling**: Octopus defaults to **Atomic Units** (Hartree/Bohr). Values can be explicitly scaled: `0.1 / eV` or `2.0 / Angstrom`.

---

## 2. Essential Input Variables

### Execution Control
| Variable | Description | Common Values |
| :--- | :--- | :--- |
| `CalculationMode` | Primary task for Octopus | `gs` (Ground State), `td` (Time Dependent), `unocc` (Unoccupied states), `opt` (Geometry optimization) |
| `Dimensions` | Dimensionality of the model | `1`, `2`, or `3` |
| `PeriodicDimensions` | Number of periodic directions | `0`, `1`, `2`, or `3` |

### Grid and Box Configuration
| Variable | Description | Notes |
| :--- | :--- | :--- |
| `Spacing` | Grid resolution | Dense grids (~0.1-0.2 Bohr) are needed for high accuracy. |
| `Radius` | Size of the simulation box | Half the extent for box shapes like `sphere` or `cylinder`. |
| `BoxShape` | Geometric constraints of the grid | `sphere`, `minimum`, `parallelepiped`, `cylinder` |

### Species and Coordinates
- **Standard Species**: Can use element symbols (e.g., "H", "C") if using pseudopotentials.
- **User Defined Species**:
  ```octopus
  %Species
    "MyParticle" | species_user_defined | potential_formula | "0.5*x^2" | valence | 1
  %
  ```
- **Coordinates**:
  ```octopus
  %Coordinates
    "MyParticle" | x | y | z
  %
  ```

---

## 3. Time-Dependent Propagation (TD)

### Basic TD Setup
To run TD, a converged GS must exist in the same directory.
- `CalculationMode = td`
- `TDPropagator = aetrs` (Approximated Enforced Time-Reversal Symmetry)
- `TDTimeStep = 0.05`
- `TDMaxSteps = 1000`

### External Fields (Lasers/Potentials)
Defined via the `%TDExternalFields` block:
```octopus
%TDExternalFields
  electric_field | 1 | 0 | 0 | 1.0 | "envelope_name"
%
```

---

## 4. Output and Data Extraction

### Output Options
Defined in the `%Output` block:
- `wfs`: Wavefunctions.
- `potential`: Total potential field (V_ks).
- `density`: Charge density.
- `OutputFormat`: `axis_x` (for 1D plots), `vtu` (3D visualization), or `netcdf`.

### Directory Structure
- `static/`: Ground state information and converged wavefunctions.
- `td.general/`: Time evolution data (multipoles, currents).
- `restart/`: Required files for continuing or branching calculations.

---

## 5. Automation Strategy (Natural Language to `inp`)

To map natural language to Octopus syntax:
1. **Identify Dimensionality**: `1D`, `2D`, or `3D` determines `Dimensions`.
2. **Determine Potential**: If user says "Harmonic", use `species_user_defined` with formula `"0.5*k*x^2"`.
3. **Parse Box**: "Large domain" implies a larger `Radius`.
4. **Select Mode**: "Evolution" maps to `td`, "Static" maps to `gs`.
5. **Scale Units**: Map "eV" or "Angstrom" to Octopus expressions (e.g., `* eV`).

---

## 6. Advanced Reference Data

### Common Molecular Coordinates
- **H2**: `%Coordinates \n "H" | 0 | 0 | -0.35 | "H" | 0 | 0 | 0.35 \n %`
- **Benzene**: Hexagonal ring in $xy$-plane with $d(C-C) \approx 1.4$ Å.

### Advanced Propagation
- **`TDTimeStep`**: Stability requires small steps (e.g., 0.01-0.05 Bohr/$\hbar$).
- **`TDFunctions`**: Defines time-envelopes (e.g., `tdf_cw`, `tdf_gaussian`).

## 7. Data Flow Logic (UI to Engine)
1. **Frontend**: Send JSON with `potentialType`, `wellWidth`, `moleculeName`, `calcMode`.
2. **Translation**: `server.py` maps these to `%Species` and `%Coordinates`.
## 8. 理解后处理结果 (Result Interpretation)

### 8.1 静态计算 (GS) 关键输出
- **`static/info`**: 这是分析的首选文件。包含：
    - **Total Energy**: 体系的总能量及其各分量。
    - **Eigenvalues**: 占据态和虚拟态的能级轨道能（单位为 Hartree）。
    - **Convergence**: 记录了 SCF 循环是否收敛。
- **`static/convergence`**: 可视化能量随迭代步数的变化，判断收敛稳定性。

### 8.2 时域演化 (TD) 关键输出
- **`td.general/dipole`**: 记录偶极矩随时间的变化。这是计算吸收光谱（UV-Vis）的基础。
- **`td.general/energy`**: 记录演化过程中的全能变化，用于分析非线性响应。
- **波函数与密度**: 在 TD 过程中，可以通过 `%Output` 块定时输出随时间变化的波函数。

---

## 9. 核心支持案例与应用 (Support Cases)

- **孤立原子/分子**:
    - 支持从 H, N 等原子到苯、甲烷等复杂分子的全电子或赝势计算。
    - **自旋极化 (Spin-polarization)**: 对于自由基或开壳层体系，需在 `inp` 中设置 `SpinComponents = spin_polarized`。
- **一维/二维模型体系**:
    - **量子点/人工原子**: 通过 `species_user_defined` 定义复杂的几何势能。
    - **有限势阱**: 模拟电子在限制势下的束缚态。
- **周期性体系**:
    - **超晶格与能带**: 通过定义晶格矢量（`LatticeVectors`）计算固体的电子能带结构。

---

## 10. 标准操作流程 (Standard Operating Procedures)

1. **预处理与准备**:
    - 确保 `inp` 变量逻辑闭环。
    - 使用 `oct-center-geom` 将复杂分子居中。
2. **基态寻优 (Ground State)**:
    - 运行 `octopus`。
    - 观察 `static/convergence`。若能量剧烈震荡，尝试减小 `Spacing` 或增加 `LSCFCalculateMixingLimit`。
3. **激发态/响应计算 (TD/Unocc)**:
    - 在 GS 收敛的基础上，切换 `CalculationMode`。
    - 配置激光场（`%TDExternalFields`）或运行 Unocc 模式获取激发能谱。
4. **数据综合分析**:
## 11. 详解输出文件夹与字段含义 (Output Deep Dive)

### 11.1 `static/info` - 计算摘要
这是评估物理结果最核心的文件，包含以下关键区块：

- **Grid (网格信息)**:
    - **Spacing**: 空间离散化步长。若该值过大，能量本征值将不准确。
    - **Grid Cutoff**: 基于网格步长的动能截断能（Hartree），反映了能量分辨率。
- **Eigenvalues (本征值表格)**:
    - **#st**: 能级序号（从最低能级开始）。
    - **Eigenvalue**: 该轨道的能量（单位：Hartree）。*注意：1 Hartree ≈ 27.2114 eV*。
    - **Occupation**: 该轨道的电子占据数。闭壳层通常为 2.0，空轨道为 0.0。
- **Energy (能量组分)**:
    - **Total**: 体系的总能量（判定化学稳定性）。
    - **Kinetic**: 电子动能。
    - **External**: 电子与原子核之间的吸引势能。
    - **Hartree**: 电子间的库仑排斥能。
- **Dipole (偶极矩)**:
    - 反映体系的电荷中心偏差。`[b]` 为 Bohr 单位，`[Debye]` 为德拜。

### 11.2 `static/convergence` - 收敛轨迹
记录了每一步 SCF (自洽场) 迭代的质量：
- **energy_diff**: 步间总能量差。理想情况下应逐渐减小并达到 `1e-6` 以下。
- **abs_dens / rel_dens**: 电荷密度的绝对/相对变化。如果密度不收敛，说明物理参数（如网格、占据数）可能设置错误。

### 11.3 `total-dos.dat` - 态密度 (Density of States)
- **Column 1 (Energy [H])**: 能量轴。
- **Column 2 (Total DOS)**: 该能量点处的态密度。峰值对应于电子能级的密集区域。
- 应用：通过绘制该文件可直观查看体系的能隙 (Band Gap) 或能带结构。

### 11.4 其他文件说明
- **`static/coordinates`**: 计算过程中实际使用的原子坐标（包含对称性处理后的结果）。
- **`exec/parser.log`**: 如果程序报错，检查该文件以确认 Octopus 是否正确解析了你的 `inp` 参数。

---

## 12. 进阶物理模型深度解析 (Advanced Physics Models)

### 12.1 自旋轨道耦合 (SOC)
- **原理**: 电子的自旋与轨道角动量相互作用，在重原子（如金、钨）和低维材料中至关重要。
- **Octopus 实施**:
    - 必须使用 **非共线自旋 (Non-collinear spin)** 设置。
    - 依赖于 **全相对论 (Fully-Relativistic) 赝势**。普通的标量相对论赝势不包含 SOC 效应。
- **能级表现**: 轨道会发生分裂（例如 $p$ 轨道分裂为 $j=1/2$ 和 $j=3/2$）。

### 12.2 DFT+U (Hubbard U) 修正
- **问题**: 标准 LDA/GGA 泛函在处理强相关电子（如过渡金属 $d$ 轨道或稀土 $f$ 轨道）时会产生过大的去局域化误差。
- **解决**: 通过 `hubbard_u` 参数引入一个局域惩罚能，强制电子更局域化，从而修正能隙和磁矩。

### 12.3 周期性边界与 K 点采样 (Periodic Systems)
- **布洛赫定理**: 在无限大的晶体中，波函数具有周期性。
- **K 点采样**: 由于在倒空间计算，需要通过一定数量的 K 点来近似 Brillouin 区的积分。
- **Monkhorst-Pack 网格**: Octopus 常用的均匀网格生成方法。网格越密（如 $8 \times 8 \times 8$），对固体的描述越精确。

### 12.4 线性响应与 Casida 方法
- **Time-Propagation (TD)**: “实时演化”。给体系一个脉冲，观察波函数随时间的变化。优点是适用强场、大振幅。
- **Casida 模式**: “频率映射”。直接求解一个激发态矩阵方程。优点是适用于分析特定的低能离散激发。
---

## 13. NetCDF Output Dataset Schema

When `OutputFormat = netcdf` is set, Octopus writes `.nc` files into `static/` or `td.general/` depending on the calculation mode.

### 13.1 Variables Present in Density Files (`density.nc`)

| Variable Name | Dimensions | Unit | Description |
| :--- | :--- | :--- | :--- |
| `density` | `(x, y, z)` | Bohr⁻³ | Total electron charge density |
| `x`, `y`, `z` | `(n)` | Bohr | Coordinate axes (grid points) |
| `density_up` | `(x, y, z)` | Bohr⁻³ | Spin-up density (spin-polarized only) |
| `density_down` | `(x, y, z)` | Bohr⁻³ | Spin-down density (spin-polarized only) |

### 13.2 Variables Present in Wavefunction Files (`wf-stNNNNN.nc`)

| Variable Name | Dimensions | Unit | Description |
| :--- | :--- | :--- | :--- |
| `wf_re` | `(x, y, z)` | Bohr⁻³/² | Real part of the orbital wavefunction |
| `wf_im` | `(x, y, z)` | Bohr⁻³/² | Imaginary part (zero for Γ-point real wavefunctions) |

### 13.3 Safe Extraction Patterns (Anti-OOM Rule)

```python
import xarray as xr, gc, numpy as np

# Pattern A: 1D slice (x-axis scan at y=0, z=0 — default for 1D models)
ds = xr.open_dataset("/workspace/output/static/density.nc", engine="scipy")
rho_1d = ds["density"].sel(y=0.0, z=0.0, method="nearest").values.tolist()
ds.close(); gc.collect()

# Pattern B: 2D cross-section (xy-plane at z=0)
ds = xr.open_dataset("/workspace/output/static/density.nc", engine="scipy")
rho_2d = ds["density"].sel(z=0.0, method="nearest").values.tolist()  # shape: (Nx, Ny)
ds.close(); gc.collect()

# Pattern C: Global min/max without loading full array (metadata probe)
ds = xr.open_dataset("/workspace/output/static/density.nc", engine="scipy")
summary = {
    "min": float(ds["density"].min()),
    "max": float(ds["density"].max()),
    "shape": list(ds["density"].shape),
}
ds.close(); gc.collect()
```

> **Critical**: Pattern C MUST be used before Pattern A or B to verify memory footprint.  
> Never simultaneously hold two open NetCDF datasets in the same Python process.

---

## 14. Advanced TDDFT Setup Reference

### 14.1 Recommended inp for TDDFT (DEV_LOCAL_COARSE profile)

```octopus
CalculationMode = td
Dimensions = 3
Spacing = 0.4      # Coarse grid (DEV profile: >= 0.2 Bohr)
Radius = 4.0       # (DEV profile: <= 5.0 Bohr)

TDPropagator = aetrs
TDTimeStep = 0.05
TDMaxSteps = 200   # (DEV profile: <= 200)

TDOutput = multipoles + energy + td_occup

%TDExternalFields
  electric_field | 1 | 0 | 0 | 0.05 | "my_pulse"
%

%TDFunctions
  "my_pulse" | tdf_gaussian | 1.0 | 0.0 | 10.0
%
```

### 14.2 Output Files Produced by TDDFT

| File | Path | Content |
| :--- | :--- | :--- |
| Dipole moment | `td.general/dipole` | Columns: `t`, `x`, `y`, `z` (all in Bohr/Hartree-time) |
| Total energy | `td.general/energy` | Columns: `t`, `E_total`, `E_kin`, `E_ext`, ... |
| Occupations | `td.general/td_occup` | Time evolution of orbital occupation |
| Absorbed energy | `td.general/absorption` | Frequency-domain spectrum after Fourier transform |

### 14.3 Post-Processing TDDFT: Absorption Spectrum

```python
import numpy as np

dipole = np.loadtxt("td.general/dipole", comments="#")
time = dipole[:, 0]      # Hartree-time units
dx   = dipole[:, 1]      # x-component dipole
dt   = time[1] - time[0]

# Fourier transform to frequency domain → absorption spectrum
freq = np.fft.rfftfreq(len(dx), d=dt)
strength = np.abs(np.fft.rfft(dx)) ** 2  # Oscillator strength proxy
omega_eV = freq * 27.2114               # Convert Hartree-freq to eV
```

---

## 15. Common Failure Patterns & Troubleshooting

| Symptom | Root Cause | Fix |
| :--- | :--- | :--- |
| `SCF not converged` after max iterations | Grid too coarse or mixing unstable | Reduce `Spacing` by 20%, add `MixingScheme = broyden` |
| Energy oscillates without decreasing | Degenerate states near Fermi level | Add `Smearing = 0.01` (Marzari-Vanderbilt) |
| `oct-status-aborted` in `exec/` | Octopus process crashed (OOM or bad inp) | Check `exec/messages` for Fortran traceback |
| `Spacing` warning: cutoff < 20 Hartree | Grid spacing too large for pseudopotential | Use `Spacing ≤ 0.2` for production runs |
| NetCDF file not generated | `OutputFormat` not set to `netcdf` | Add `OutputFormat = netcdf` to inp |
| Wavefunction files missing | `Output` block missing `wfs` | Add `%Output \n wfs \n %` |
| TD run fails at step 1 | GS restart files missing | Re-run GS first with `CalculationMode = gs` |
| Eigenvalue is `NaN` | Numeric overflow (grid too fine + large domain) | Check `Radius` × `Spacing` product — should be < 5000 points per axis |
| Memory OOM in Docker | 3D grid too large for 12 GB limit | Switch to DEV profile: `Spacing ≥ 0.2`, `Radius ≤ 5.0` |
| `parse error` in `exec/parser.log` | Typo in inp variable name | Check exact variable name in Octopus manual (case-insensitive but spelling is exact) |
