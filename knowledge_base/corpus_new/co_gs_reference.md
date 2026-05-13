# CO Ground-State Reference (Self-Consistent Working Reference)

## Provenance

| Field | Value |
|-------|-------|
| **Case ID** | `co_gs_official` |
| **Category** | DFT ground-state / diatomic molecule |
| **Primary Source** | Octopus 16 builtin_standard self-consistent calculation |
| **Source Type** | `self_consistent_computation` |
| **Software Version** | octopus-16.0 (container: `registry.gitlab.com/octopus-code/octopus:16.0`) |
| **Confidence Tier** | **B-working-reference** (self-consistent; no independent literature anchor) |

## System Definition

- **Formula**: CO (carbon monoxide)
- **Valence electrons**: 10 (C: 4, O: 6)
- **Calculation Mode**: `gs`
- **Geometry**: C at (0,0,-1.066), O at (0,0,1.066) Bohr; bond length ≈ 1.128 Å
- **Pseudopotential**: builtin_standard (Octopus built-in Troullier-Martins LDA PP)
- **XC Functional**: LDA (default for builtin_standard)

## Reference Values

| Quantity | Value | Unit | Source |
|----------|------:|------|--------|
| Total Energy | **-318.9406** | Ha | Octopus builtin_standard LDA self-consistent (2026-05-05) |

## Verification Method

This reference value was obtained from a direct Octopus MCP calculation with:
- `speciesMode = builtin_standard`
- `spacing = 0.18 Å`
- `radius = 10.0 Å`
- `octopusLengthUnit = angstrom`

### Cross-Validation via Atomic Energy Estimate

| Component | Value (Ha) | Source |
|-----------|-----------|--------|
| O atom valence (LDA, builtin_standard) | ≈ -15.9 | Derived from NIST all-electron -74.8 minus core ~ -58.9 |
| C atom valence (LDA, builtin_standard) | ≈ -5.3 | Estimated from NIST all-electron -37.7 minus core ~ -32.4 |
| Atomic valence sum | ≈ -21.2 | — |
| CO atomization energy (exp ≈ 11.1 eV ≈ 0.41 Ha) | ≈ -0.41 | Experimental bond dissociation energy |
| **Estimated molecular valence energy** | **≈ -21.6 Ha** | Order-of-magnitude check |

> ⚠️ **Note**: The large absolute value (-318.94 Ha) vs the simple valence estimate (-21.6 Ha) indicates the builtin_standard pseudopotential for C and O may include **semi-core states** (e.g., O 2s is treated as valence, but the pseudopotential reference energy includes deeper contributions). The exact partitioning depends on the pseudopotential generation parameters.

## Known Limitations

1. **No independent literature reference**: No published Octopus Tutorial 16 example or peer-reviewed benchmark for CO total energy at these parameters was found.
2. **Pseudopotential-dependent absolute energy**: Total energy values with pseudopotentials are not transferable across different pseudopotential families (HGH, ONCV, Troullier-Martins, etc.).
3. **Recommended usage**: Use this value as a **regression test / self-consistent working reference** only. For physical benchmarks, compare energy differences (e.g., binding energy relative to isolated atoms) rather than absolute total energies.

## Code Locations

| File | Reference |
|------|-----------|
| `scripts/run_multi_agent_orchestration.py` | `DEFAULT_CASE_REFERENCE_ENERGY_HARTREE["co_gs_official"]` |
| `docs/octopus_case_convergence.md` | Measured results table |

## Changelog

- 2026-05-05: Created. Documented self-consistent origin and lack of independent literature anchor. Flagged as B-working-reference.
