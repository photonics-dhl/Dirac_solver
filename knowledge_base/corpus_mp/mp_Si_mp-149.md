# Si — Materials Project DFT Reference

**Formula**: Si  
**Material ID**: mp-149  
**Source**: [Materials Project](https://materialsproject.org/materials/mp-149)  
**Last Updated**: 2026-04-27T03:01:03.849681Z  
**Type**: Experimental  

## Provenance

- source: Materials Project (https://materialsproject.org/materials/mp-149)
- accessed: 2026-04-27T03:01:03.849644Z
- software: VASP (PAW pseudopotentials, PBE functional)
- theoretical: False
- material_id: mp-149
- formation_energy_per_atom: 0.0000 eV/atom
- e_above_hull: 0.0000 eV/atom (stability)
- structure_type: experimental

## Electronic Structure

- **Band gap**: 0.6105 eV (indirect)
- **Conductor type**: Semiconductor/Insulator
- **Fermi level**: 5.6302 eV
- **CBM**: 6.2270 eV | **VBM**: 5.6165 eV
- **Is metal**: False
- **Magnetic**: No
- **Functional**: PBE (GGA) — standard MP functional

## Thermodynamic Stability

- **Formation energy**: 0.0000 eV/atom
  → Thermodynamically unstable (positive formation energy)
- **Energy above hull**: 0.0000 eV/atom
  → Ground state / very stable

## Total Energy

- **Energy per atom**: -8.773765 eV/atom
- **Volume**: 40.3295 Angstrom^3
- **Density**: 2.3128 g/cm^3

## Crystal Structure

Lattice (Angstrom): a=3.8493, b=3.8493, c=3.8493
Lattice angles: alpha=60.00, beta=60.00, gamma=60.00 deg
Space group: Fd-3m (IT No. 227)
Sites (2):
  Si: [0.875000, 0.875000, 0.875000]
  Si: [0.125000, 0.125000, 0.125000]

## Physical Interpretation for Dirac/Octopus Comparison

Si is the canonical semiconductor test case from Octopus Tutorial 16 (periodic systems / optical spectra).
  MP LDA bandgap 0.611 eV vs experimental 1.1 eV — similar LDA underestimation to Octopus.
  Direct comparison: Octopus Tutorial 16 reports LDA bandgap ~0.5 eV.

## Comparison with Octopus Calculations

| Property | MP (VASP) | Octopus (this repo) | Notes |
|---|---|---|---|
| Band gap (eV) | 0.6105 | TBD (your run) | MP uses PAW; Octopus uses norm-conserving PP |
| Formation energy (eV/atom) | 0.0000 | TBD (your run) | Cross-check thermodynamic stability |
| Energy per atom (eV/atom) | -8.7738 | TBD (your run) | Per-atom comparison most robust |

## References

- Materials Project entry: https://materialsproject.org/materials/mp-149
- Methodology: https://docs.materialsproject.org/methodology/materials-methodology/calculation-details
