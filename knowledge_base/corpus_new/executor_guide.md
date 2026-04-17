# Octopus Tutorial 16 — Executor Guidance

> **Purpose**: Guide the executor agent to reproduce Octopus calculations from official tutorial parameters.
> **Source**: [Octopus Tutorial 16](https://www.octopus-code.org/documentation/16/)
> **Last Verified**: 2026-04-16

---

## Case 1: N Atom — Ground State Convergence

### Source
**URL**: `https://www.octopus-code.org/documentation/16/tutorial/basics/total_energy_convergence/`

### System Parameters
- Element: N (Nitrogen, Z=7)
- Pseudopotential: `species_pseudo | set | standard` (5 valence electrons)
- Calculation Mode: `gs`
- Box: sphere (default for atoms)
- Units: **Hartree (Ha)** by default

### Convergence Study Script
```bash
#!/bin/bash
# Spacing convergence for N atom (spacing in Angstrom)
# Conversion: spacing_Bohr = spacing_A * 1.889726

cat > inp << EOF
CalculationMode = gs
Nitrogen_mass = 14.0
%Species
  "N" | species_pseudo | set | standard | lmax | 1 | lloc | 0 | mass | Nitrogen_mass
%
%Coordinates
  "N" | 0 | 0 | 0
%
BoxShape = sphere
Radius = 10.0*angstrom
Spacing = {{SPACING}}*angstrom
ExtraStates = 1
%Occupations
  2 | 1 | 1 | 1
%
EOF

# Run with each spacing
for SPACING in 0.26 0.24 0.22 0.20 0.18 0.16 0.14; do
  rm -rf restart
  export OCT_Spacing=$(echo "$SPACING * 1.889726" | bc)
  octopus < out-$SPACING
  energy=$(grep "Total =" static/info | head -1 | awk '{print $3}')
  s_eigen=$(grep "1 --" static/info | head -1 | awk '{print $3}')
  p_eigen=$(grep "2 --" static/info | head -1 | awk '{print $3}')
  echo "$SPACING $energy $s_eigen $p_eigen"
done
```

### Verified Results at spacing = 0.18 Å

| Quantity | Ha | eV |
|----------|-----:|-----:|
| Total Energy | -262.24120934 | -7135.95 |
| s eigenvalue | -18.282871 | -497.50 |
| p eigenvalue | -7.302321 | -198.71 |

### Executor Checklist
- [ ] Generate inp file with `Spacing = 0.18*angstrom`
- [ ] Run Octopus ground state
- [ ] Extract `Total Energy` from `static/info`
- [ ] Extract `1 --` (s eigenvalue) and `2 --` (p eigenvalue) from eigenvalues block
- [ ] Compare with reference: E = -262.24 Ha ± 1%
- [ ] Report job_id, spacing, ncpus in artifact

---

## Case 2: CH₄ — Ground State Convergence

### Source
**URL**: `https://www.octopus-code.org/documentation/16/tutorial/basics/total_energy_convergence/`

### System Parameters
- Molecule: CH₄ (tetrahedral; C at origin; CH bond = 1.2 Å)
- Pseudopotential: Default (no explicit %Species block)
- Calculation Mode: `gs`
- Units: **eV** (because `UnitsOutput = eV_Angstrom` is set)

### Octopus Input (spacing = 0.18 Å)
```bash
CalculationMode = gs
UnitsOutput = eV_Angstrom
FromScratch = yes
Radius = 3.5*angstrom
Spacing = 0.18*angstrom
CH = 1.2*angstrom
%Coordinates
  "C" | 0 | 0 | 0
  "H" | CH/sqrt(3) | CH/sqrt(3) | CH/sqrt(3)
  "H" | -CH/sqrt(3) | -CH/sqrt(3) | CH/sqrt(3)
  "H" | CH/sqrt(3) | -CH/sqrt(3) | -CH/sqrt(3)
  "H" | -CH/sqrt(3) | CH/sqrt(3) | -CH/sqrt(3)
%
EigenSolver = chebyshev_filter
ExtraStates = 4
```

### Verified Results at spacing = 0.18 Å

| Quantity | Value | Unit |
|----------|------:|------|
| Total Energy | -218.27963068 | eV |
| Total Energy | -8.0216 | Ha |

### Executor Checklist
- [ ] Generate inp with CH₄ geometry and `Spacing = 0.18*angstrom`
- [ ] Run Octopus (from scratch)
- [ ] Extract `Total =` from `static/info` — unit is eV
- [ ] Compare: E = -218.28 eV ± 1%
- [ ] Note: No pseudopotential block → Octopus uses default

---

## Case 3: Si — Optical Spectra of Solids (Band Structure)

### Source
**URL**: `https://www.octopus-code.org/documentation/16/tutorial/periodic_systems/optical_spectra_of_solids/`

### System Parameters
- Material: Crystalline silicon (bulk; primitive cell with 2 Si atoms)
- Calculation: GS → TD (optical conductivity)
- Periodicity: 3D periodic
- Spacing: 0.5 (Bohr)
- k-points: 2×2×2 Monkhorst-Pack grid
- k-points for TD: 2×2×2 with symmetry breaking along x

### GS Input
```bash
CalculationMode = gs
PeriodicDimensions = 3
Spacing = 0.5
%LatticeVectors
  0.0 | 0.5 | 0.5
  0.5 | 0.0 | 0.5
  0.5 | 0.5 | 0.0
%
a = 10.18
#LatticeParameters
#  a | a | a
%ReducedCoordinates
  "Si" | 0.0 | 0.0 | 0.0
  "Si" | 1/4 | 1/4 | 1/4
%
nk = 2
%KPointsGrid
  nk | nk | nk
  0.5 | 0.5 | 0.5
  0.5 | 0.0 | 0.0
  0.0 | 0.5 | 0.0
  0.0 | 0.0 | 0.5
%
KPointsUseSymmetries = yes
%SymmetryBreakDir
  1 | 0 | 0
%
Eigensolver = chebyshev_filter
ExtraStates = 4
```

### Known Band Gap References

| XC Functional | Band Gap (eV) | Notes |
|---------------|-------------:|-------|
| LDA | ~0.5 | Known to underestimate |
| GGA (PBE) | ~0.7 | Still underestimates |
| Experiment | ~1.1 | Room temperature |

> **Status**: These are textbook/guideline values from Octopus documentation; the specific computed value from this tutorial page was not extracted in this pass. Use as sanity check only.

### Executor Checklist
- [ ] Run GS with above input
- [ ] Verify band structure from `static/eigenvalues` or `static/band_structure`
- [ ] Compute band gap (Γ-Γ or relevant high-symmetry points)
- [ ] Compare with LDA ~0.5 eV range
- [ ] Report k-point mesh and functional explicitly

---

## Case 4: H₂O — TDDFT Absorption (Partially Verified)

### Source
**URL**: Inferred from UI_User_Guide; specific Tutorial 16 page not yet verified

### System Parameters
- Molecule: H₂O (equilibrium geometry; neutral singlet)
- Calculation: `gs` → `td`
- XC Functional: LDA
- Spectrum type: Optical absorption (dipole)

### Reference Peak (from UI_User_Guide — ⚠️ B-tier)

| Quantity | Value | Unit |
|----------|------:|------|
| First peak center | ~7.5 | eV |
| Window | [7.0, 8.0] | eV |
| LDA bias | ~0.5 | eV (underestimates) |

> **Verification needed**: Confirm specific Tutorial 16 URL containing H₂O example.

### Executor Input (Known Parameters)
```bash
CalculationMode = gs
UnitsOutput = eV_Angstrom
Radius = 3.5*angstrom
Spacing = 0.18*angstrom
# (Add H2O coordinates from tutorial)
%Coordinates
  "O" | 0 | 0 | 0
  "H" | ... | ... | ...
%
```

---

## Key Parameters for Executor

### Unit Conventions in Octopus Tutorial 16
| Variable | Default Unit | Tutorial Override |
|----------|------------|-----------------|
| Energy | Ha | `UnitsOutput = eV_Angstrom` → eV |
| Length | Bohr | `angstrom` suffix → Å |
| Spacing | Bohr | `*angstrom` suffix → Å |

### Convergence Workflow (Standard Pattern)
1. Start with `Spacing = 0.22*angstrom`
2. Scan: 0.22 → 0.20 → 0.18 → 0.16 → 0.14 (for molecules)
3. For atoms: use 0.26 → 0.24 → ... → 0.14
4. Check ΔE between adjacent spacings < 0.1 eV
5. Use the spacing where criterion is first met (usually 0.18 Å)

### Radius Convergence (after spacing)
1. Fix spacing at converged value (e.g., 0.18 Å)
2. Scan Radius: 2.5 → 3.0 → 3.5 → ... → 10.0 Å
3. Check ΔE < 0.1 eV
4. Typical converged Radius for small molecules: 3.5–5.0 Å
