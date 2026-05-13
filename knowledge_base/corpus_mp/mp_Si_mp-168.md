# Si — Materials Project DFT Reference

**Formula**: Si  
**Material ID**: mp-168  
**Source**: [Materials Project](https://materialsproject.org/materials/mp-168)  
**Last Updated**: 2026-04-27T03:01:03.670070Z  
**Type**: Experimental  

## Provenance

- source: Materials Project (https://materialsproject.org/materials/mp-168)
- accessed: 2026-04-27T03:01:03.670052Z
- software: VASP (PAW pseudopotentials, PBE functional)
- theoretical: False
- material_id: mp-168
- formation_energy_per_atom: 0.1600 eV/atom
- e_above_hull: 0.1600 eV/atom (stability)
- structure_type: experimental

## Electronic Structure

- **Band gap**: 0.0 eV (metallic)
- **Conductor type**: Metal
- **Fermi level**: 7.1148 eV
- **Is metal**: True
- **Magnetic**: No
- **Functional**: PBE (GGA) — standard MP functional

## Thermodynamic Stability

- **Formation energy**: 0.1600 eV/atom
  → Thermodynamically unstable (positive formation energy)
- **Energy above hull**: 0.1600 eV/atom

## Total Energy

- **Energy per atom**: -8.613744 eV/atom
- **Volume**: 147.4149 Angstrom^3
- **Density**: 2.5309 g/cm^3

## Crystal Structure

Lattice (Angstrom): a=5.7640, b=5.7640, c=5.7640
Lattice angles: alpha=109.47, beta=109.47, gamma=109.47 deg
Space group: Ia-3 (IT No. 206)
Sites (8):
  Si: [0.203114, 0.000000, 0.000000]
  Si: [0.000000, 0.703114, 0.500000]
  Si: [0.500000, 0.500000, 0.203114]
  Si: [0.296886, 0.796886, 0.296886]
  Si: [0.796886, 0.000000, 0.000000]
  Si: [0.000000, 0.296886, 0.500000]
  Si: [0.500000, 0.500000, 0.796886]
  Si: [0.703114, 0.203114, 0.703114]

## Physical Interpretation for Dirac/Octopus Comparison

Si is the canonical semiconductor test case from Octopus Tutorial 16 (periodic systems / optical spectra).
  Direct comparison: Octopus Tutorial 16 reports LDA bandgap ~0.5 eV.

## Comparison with Octopus Calculations

| Property | MP (VASP) | Octopus (this repo) | Notes |
|---|---|---|---|
| Band gap (eV) | 0.0000 | TBD (your run) | MP uses PAW; Octopus uses norm-conserving PP |
| Formation energy (eV/atom) | 0.1600 | TBD (your run) | Cross-check thermodynamic stability |
| Energy per atom (eV/atom) | -8.6137 | TBD (your run) | Per-atom comparison most robust |

## References

- Materials Project entry: https://materialsproject.org/materials/mp-168
- Methodology: https://docs.materialsproject.org/methodology/materials-methodology/calculation-details
