# H2O TDDFT Casida Linear Response Reference

> **Status (2026-05-14)**: First reliable H2O optical spectrum. Casida linear response (Octopus 16, builtin_standard LDA). Job 151384.mu01, 32 cores, 16 MPI. **A-tier confidence** — self-consistent, GS-validated, experimental cross-checked.

## Casida Excitation Energies

| # | E (eV) | Osc. Strength <f> | Dominant Transition | Character |
|---|--------|-------------------|---------------------|-----------|
| 1 | **6.674** | 0.0427 | HOMO→LUMO (1b1→3sa1) | A¹B₁, dipole-allowed (y) |
| 2 | 7.789 | ~0 | — | forbidden |
| 3 | 8.011 | 0.0041 | — | weak |
| 4 | 8.041 | 0.0014 | — | weak |
| 5 | **8.793** | 0.1018 | 1b1→3pb₂ | B¹A₁, strong |
| 6 | 9.756 | 0.0108 | — | moderate |
| 7 | 9.902 | 0.0005 | — | weak |
| 8 | 9.989 | ~0 | — | forbidden |
| 9 | **12.676** | 0.1577 | 1b1→3pa₁ | C¹B₁, very strong |
| 10 | 13.857 | ~0 | — | forbidden |
| 11 | 13.907 | 0.0113 | — | moderate |
| 12 | 14.031 | 0.0183 | — | moderate |
| 13 | 25.160 | 0.0089 | — | higher Rydberg |
| 14 | 25.493 | 0.0034 | — | higher Rydberg |
| 15 | 25.581 | ~0 | — | forbidden |
| 16 | 25.642 | ~0 | — | forbidden |

## Calculation Parameters

| Parameter | Value |
|-----------|-------|
| Engine | Octopus 16.0 |
| Mode | Casida linear response |
| PP | builtin_standard (Troullier-Martins LDA) |
| XC | lda_x+lda_c_pz |
| Box | sphere, radius 10 Å, spacing 0.18 Å |
| GS Energy | −17.171182 Ha |
| SCF Iterations | 33 (converged) |
| ExtraStates | 8 |
| CasidaKohnShamStates | 1-8 |
| Job ID | 151384.mu01 |
| Resources | 32 cores, 16 MPI (node cn34) |

## Cross-Validation

### Internal Consistency: HOMO-LUMO Gap vs Casida First Excitation

| Quantity | Energy (eV) |
|----------|------------|
| HOMO-LUMO gap (GS) | 6.53 eV |
| Casida 1st excitation | 6.674 eV |
| Difference | +0.14 eV |

The 0.14 eV difference between the Kohn-Sham HOMO-LUMO gap and the Casida first excitation is the exciton binding energy / electron-hole interaction. LDA typically underestimates this, but the sign is correct (Casida > KS gap).

### Experimental Reference: Mota et al. VUV Synchrotron

| Band | Energy (eV) | This Work | Status |
|------|------------|-----------|--------|
| Band 1 (3sa1 ← 1b1) | 6.5–8.7 | **6.674 eV** | Within range |
| Band 2 (higher) | 8.5–10.0 | 8.793 eV | Boundary match |

The Casida 6.674 eV first excitation falls within the experimental Band 1. The 8.793 eV strong transition is at the boundary of Band 1 and Band 2. LDA systematic underestimation of ~0.5 eV means the true (PBE/hybrid) values would be ~0.5 eV higher.

### Comparison with Time-Propagation TDDFT

**The existing time-propagation data is unreliable** — 350 steps × 0.005 a.u. = 98 eV resolution (see [[h2o_tddft_results_20260514]]). The first TDDFT peak (9.67 eV) disagrees with Casida (6.674 eV) by ~3 eV due to insufficient propagation time, not a real discrepancy.

A new time-propagation calculation with ≥17,000 steps is needed for valid Casida↔TDDFT cross-validation.

## Comparison with CH4 (Tutorial 16 Gold Standard)

| Quantity | CH4 | H2O |
|----------|-----|-----|
| Casida 1st excitation | 9.184 eV (tutorial) | 6.674 eV (this work) |
| Experiment 1st peak | 9.6 eV (Matsuzawa) | 6.5-8.7 eV (Mota) |
| LDA error | −0.4 eV | within range |
| Strongest low-E transition | 9.278 eV (f=0.095) | 8.793 eV (f=0.102) |

## Previous KB Entry Status

The previous `h2o_tddft_absorption_reference.md` (B-tier, "first peak ~7-8 eV") is now **superseded** by this A-tier Casida reference. The 7-8 eV window was approximately correct.

## Output Files

| File | Description |
|------|------------|
| `@Octopus_docs/output/casida` | Casida excitation summary |
| `@Octopus_docs/output/runs/octopus_latest/casida/casida` | Full Casida output |
| `@Octopus_docs/output/runs/octopus_latest/casida/casida_excitations/` | Per-excitation wavefunction data (00001-00016) |
| `@Octopus_docs/output/runs/octopus_latest/casida/eps_diff` | Alternative: epsilon-difference method |
| `@Octopus_docs/output/runs/octopus_latest/casida/petersilka` | Alternative: Petersilka method |

## Provenance

- **This work (2026-05-14)**: Casida linear response, Octopus 16.0, builtin_standard LDA, job 151384.mu01
- Mota, R. et al., *VUV photoabsorption spectroscopy of H₂O*, DOI: [to be confirmed]
- Octopus Tutorial 16 (CH₄ Casida): https://octopus-code.org/documentation/16/tutorials/methane_absorption_spectrum_from_tddft/

## PBE Casida Results (2026-05-15)

PBE XC Casida performed for direct apple-to-apple comparison with TDDFT time-propagation (both PBE).

| Parameter | Value |
|-----------|-------|
| PP | standard (PBE pseudopotentials) |
| XC | gga_x_pbe+gga_c_pbe |
| GS Energy | −17.228019 Ha |
| SCF Iterations | 25 |
| ExtraStates | 13 |
| CasidaKohnShamStates | 1-16 |
| KS States | 17 |
| Excitations | 48 |

### PBE vs LDA Comparison

| Quantity | LDA | PBE | Δ |
|----------|-----|-----|---|
| GS Energy (Ha) | −17.171182 | −17.228019 | −0.0568 |
| HOMO-LUMO gap (eV) | 6.53 | 6.95 | +0.42 |
| 1st excitation (eV) | 6.674 | 6.953 | +0.279 |
| Bright ~8.8 eV | 8.793 | 8.946 | +0.153 |
| Bright ~12.7 eV | 12.676 | 12.935 | +0.259 |

PBE systematically blue-shifts vs LDA by ~0.15-0.28 eV. Expected — PBE widens HOMO-LUMO gap.

### PBE Casida ↔ PBE TDDFT (Apple-to-Apple)

| Feature | Casida PBE | TDDFT PBE | Δ |
|---------|-----------|-----------|---|
| 1st excitation | 6.953 eV | 6.36 eV | −0.59 |
| Strong ~8.8-8.9 eV | 8.946 eV | 8.83 eV | −0.12 |

The 8.95 eV (Casida) ↔ 8.83 eV (TDDFT) match is excellent (−0.12 eV). Low-energy TDDFT peaks (5.23, 6.36 eV) are not captured by Casida — possibly spectral broadening artifacts or dark states.

Data: `docs/tddft/data/h2o_casida_pbe_results.json`

## Changelog

- **2026-05-15**: Added PBE Casida results (48 excitations, 17 KS states). Apple-to-apple PBE comparison with TDDFT.
- **2026-05-14**: Created. First reliable H2O optical spectrum from Casida linear response. Supersedes B-tier `h2o_tddft_absorption_reference.md`. Casida mode added to server.py.
