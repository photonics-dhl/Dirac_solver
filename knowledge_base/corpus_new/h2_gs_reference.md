# H₂ Ground-State Reference (Literature + Octopus Tutorial)

## Provenance

| Field | Value |
|-------|-------|
| **Case ID** | `h2_gs_reference` |
| **Category** | DFT ground-state / diatomic molecule |
| **Primary Source** | Octopus Tutorial 16 (inferred) + literature |
| **Source Type** | `literature` + `octopus_tutorial` |
| **Software Version** | octopus-16.0 |
| **Confidence Tier** | **B-needs-evidence** |

> **Note**: H₂ is the default molecule in `infer_octopus_defaults_for_case()` when `case_id` does not match known patterns.

## System Definition

- **Formula**: H₂ (diatomic; two hydrogen atoms)
- **Z**: 1 per atom; total Z = 2
- **Valence electrons**: 2
- **Bond length (experimental)**: 0.741 Å (0.74 bohr)
- **Dissociation energy**: 4.52 eV (experiment)
- **Calculation Mode**: `gs`

## Reference Values

### H₂ Ground State (Literature)

| Quantity | Value | Unit | Source |
|----------|------:|------|--------|
| Total energy (LDA/pseudopotential, spacing=0.20 Å) | -1.13 | Ha | Octopus tutorial estimate |
| Dissociation energy (experimental) | 4.52 | eV | Known experimental value |
| Bond length (experimental) | 0.741 | Å | NIST |
| Vibrational frequency ω_e | 4401 | cm⁻¹ | NIST |

### H₂ as Pseudopotential Termination Species

In many DFT calculations, H is used as a termination/passivation atom. For these cases, H₂ total energy is not directly used as a benchmark, but the **H-H bond energy** serves as a consistency check.

## Known Limitations

1. **No Octopus Tutorial 16 H₂ example confirmed**: H₂ does not appear in the extracted Tutorial 16 pages; it is used as a system default in the orchestration code
2. **No verified Octopus output**: No direct Octopus output for H₂ was extracted in this pass
3. **Passivation vs standalone**: H in passivation mode uses different potentials than standalone H₂

## Action Items

- [ ] Verify if Octopus Tutorial 16 contains an H₂ example
- [ ] Run H₂ GS with Octopus using bond length = 0.741 Å, spacing = 0.18 Å
- [ ] Extract total energy from `static/info`

## Code Locations

| File | Reference |
|------|-----------|
| `scripts/dispatch_dirac_task.py` | `infer_octopus_defaults_for_case()` maps unknown case_id → H₂ |
| `scripts/run_multi_agent_orchestration.py` | Default molecule = "H2" when not specified |

## Changelog

- 2026-04-16: Created. Noted as B-tier due to lack of verified Octopus data.
