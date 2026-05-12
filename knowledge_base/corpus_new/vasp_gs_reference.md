# VASP PAW-PBE Ground-State Reference Data

> **Status (2026-05-12)**: Validated. Standard potpaw_PBE.54 library, direct execution via `/solve_vasp` endpoint.

## Methodology

| Field | Value |
|-------|-------|
| **Code** | VASP 6.x (`/data/software/AMD/vasp_std`) |
| **Pseudopotential** | PAW_PBE (standard potpaw_PBE.54, `/data/home/Hzk-14/pot/potpaw_PBE.54/`) |
| **XC Functional** | GGA-PBE (Perdew-Burke-Ernzerhof) |
| **ENCUT** | 520 eV |
| **EDIFF** | 1e-6 eV |
| **PREC** | Accurate |
| **ISMEAR** | 0 (Gaussian), SIGMA = 0.01 eV |
| **K-Points** | Gamma-only (1×1×1) |
| **Box** | 8-10 Å cubic (isolated molecule/atom) |
| **ISTART/ICHARG** | 0/2 (start from atomic charge density) |

---

## Atomic Reference Data

| Atom | Etot (eV) | Etot (Ha) | Mag (μB) | Valence e- | 2s Eigenvalue (eV) | 2p Eigenvalue (eV) | HOMO (eV) |
|------|-----------|-----------|-----------|------------|---------------------|---------------------|------------|
| H | -1.1182 | -0.04110 | 1.00 | 1 | — | — | -7.55 |
| C | -1.2513 | -0.04599 | 2.00 | 4 | -14.54 | -5.99 (3×) | -5.99 |
| N | -3.1241 | -0.11482 | 3.00 | 5 | -19.79 | -8.21 (3×) | -8.21 |
| O | -1.5364 | -0.05647 | 2.00 | 6 | -25.14 | -10.14 (3×) | -10.14 |

**Notes:**
- PAW absolute energies represent VALENCE contributions only (frozen core: H no core, C/N/O 1s² frozen)
- Magnetization values confirm correct ground-state spin multiplicity: H (²S), C (³P), N (⁴S), O (³P)
- All atoms: spin-polarized (ISPIN=2), 8-10 Å cubic box, ENCUT=520, PREC=Accurate

---

## Molecular Reference Data

| Molecule | Etot (eV) | Etot (Ha) | Mag (μB) | Valence e- | HOMO (eV) | LUMO (eV) | Gap (eV) |
|----------|-----------|-----------|-----------|------------|-----------|-----------|----------|
| CH4 | -24.0241 | -0.8830 | 0.00 | 8 | -9.31 | -0.52 | 8.79 |
| H2O | -14.2120 | -0.5224 | 0.00 | 8 | -7.09 | -0.99 | 6.10 |

**Notes:**
- CH4: Td geometry, C at origin, H at tetrahedral positions (C-H = 1.09 Å, from MOLECULES dict)
- H2O: bent geometry, O at origin (O-H = 0.957 Å, HOH = 104.5°, from MOLECULES dict)
- Both: closed-shell (ISPIN=1), gamma-only k-points

---

## Atomization Energies

| Molecule | ΔE (eV) | ΔE (kcal/mol) | Exp. (eV) | Exp. (kcal/mol) | PBE Error |
|----------|---------|---------------|-----------|-----------------|-----------|
| CH4 | 18.31 | 422.1 | 17.02 | 392.4 | +7.6% |
| H2O | 10.44 | 240.8 | 9.51 | 219.3 | +9.8% |

**Formula:**
- CH4: ΔE = Etot(CH4) − [Etot(C) + 4×Etot(H)] = −24.024 − [−1.251 + 4×(−1.118)] = 18.31 eV
- H2O: ΔE = Etot(H2O) − [Etot(O) + 2×Etot(H)] = −14.212 − [−1.536 + 2×(−1.118)] = 10.44 eV

PBE overestimates atomization energies by ~8-10% — well-known behavior (PBE tends to overbind).

**Experimental references:**
- CH4: ATcT D₀ = 392.4 ± 0.2 kcal/mol (Ruscic et al.)
- H2O: ATcT D₀ = 219.3 ± 0.1 kcal/mol

---

## Cross-Engine Comparison: VASP PAW-PBE vs Octopus PP-LDA

> Absolute energies are NOT comparable (different pseudopotential construction: PAW vs Troullier-Martins vs HGH).
> Compare: magnetization, eigenvalue degeneracy, atomization energy trends.

| Property | VASP PAW-PBE | Octopus PP-LDA | Agreement |
|----------|-------------|----------------|-----------|
| H mag (μB) | 1.0 | 1.0 | ✅ Exact |
| C mag (μB) | 2.0 | — | — |
| N mag (μB) | 3.0 | — | — |
| O mag (μB) | 2.0 | — | — |
| CH4 HOMO degeneracy | 3× | — | — |
| H2O HOMO-LUMO gap | 6.10 eV | — | — |

**Interpretation:** Magnetization agrees exactly (spin multiplicity determined by electron count, not pseudopotential). Eigenvalue patterns consistent with molecular symmetry. Atomization energies within expected PBE overbinding range.

---

## Provenance

- **Run date**: 2026-05-12
- **Execution**: Direct VASP on HPC login node (OCTOPUS_EXEC_STRATEGY=direct)
- **Endpoint**: `POST /solve_vasp` on MCP server (port 8000)
- **VASP binary**: `/data/software/AMD/vasp_std`
- **POTCARS**: Standard PAW_PBE.54 at `/data/home/Hzk-14/pot/potpaw_PBE.54/`
- **Validator**: Sunshine

## Code Locations

- `docker/workspace/vasp_backend.py` — INCAR/POSCAR/KPOINTS/POTCAR generation
- `docker/workspace/server.py` — `/solve_vasp` endpoint, `run_vasp_calculation()`
- `frontend/src/App.tsx` — (Phase 5) VASP UI integration

## Changelog

- **2026-05-12**: Created. Initial VASP PAW-PBE reference data for H, C, N, O, CH4, H2O.
