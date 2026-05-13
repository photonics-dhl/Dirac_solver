# Si — Materials Project DFT Reference

**Formula**: Si  
**Material ID**: mp-165  
**Source**: [Materials Project](https://materialsproject.org/materials/mp-165)  
**Last Updated**: 2026-04-27T03:01:03.600958Z  
**Type**: Experimental  

## Provenance

- source: Materials Project (https://materialsproject.org/materials/mp-165)
- accessed: 2026-04-27T03:01:03.600939Z
- software: VASP (PAW pseudopotentials, PBE functional)
- theoretical: False
- material_id: mp-165
- formation_energy_per_atom: 0.0136 eV/atom
- e_above_hull: 0.0136 eV/atom (stability)
- structure_type: experimental

## Electronic Structure

- **Band gap**: 0.4389 eV (indirect)
- **Conductor type**: Semiconductor/Insulator
- **Fermi level**: 5.8958 eV
- **CBM**: 6.3138 eV | **VBM**: 5.8749 eV
- **Is metal**: False
- **Magnetic**: No
- **Functional**: PBE (GGA) — standard MP functional

## Thermodynamic Stability

- **Formation energy**: 0.0136 eV/atom
  → Thermodynamically unstable (positive formation energy)
- **Energy above hull**: 0.0136 eV/atom
  → Near ground state

## Total Energy

- **Energy per atom**: -8.760158 eV/atom
- **Volume**: 80.5028 Angstrom^3
- **Density**: 2.3173 g/cm^3

## Crystal Structure

Lattice (Angstrom): a=3.8313, b=3.8313, c=6.3326
Lattice angles: alpha=90.00, beta=90.00, gamma=120.00 deg
Space group: P6_3/mmc (IT No. 194)
Sites (4):
  Si: [0.666683, 0.333317, 0.500012]
  Si: [0.000015, 0.999985, 0.000009]
  Si: [0.666683, 0.333318, 0.873993]
  Si: [0.000020, 0.999981, 0.373986]

## Physical Interpretation for Dirac/Octopus Comparison

Si is the canonical semiconductor test case from Octopus Tutorial 16 (periodic systems / optical spectra).
  MP LDA bandgap 0.439 eV vs experimental 1.1 eV — similar LDA underestimation to Octopus.
  Direct comparison: Octopus Tutorial 16 reports LDA bandgap ~0.5 eV.

## Comparison with Octopus Calculations

| Property | MP (VASP) | Octopus (this repo) | Notes |
|---|---|---|---|
| Band gap (eV) | 0.4389 | TBD (your run) | MP uses PAW; Octopus uses norm-conserving PP |
| Formation energy (eV/atom) | 0.0136 | TBD (your run) | Cross-check thermodynamic stability |
| Energy per atom (eV/atom) | -8.7602 | TBD (your run) | Per-atom comparison most robust |

## References

- Materials Project entry: https://materialsproject.org/materials/mp-165
- Methodology: https://docs.materialsproject.org/methodology/materials-methodology/calculation-details
