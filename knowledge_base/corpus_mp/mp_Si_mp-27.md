# Si — Materials Project DFT Reference

**Formula**: Si  
**Material ID**: mp-27  
**Source**: [Materials Project](https://materialsproject.org/materials/mp-27)  
**Last Updated**: 2026-04-27T03:01:03.813710Z  
**Type**: Experimental  

## Provenance

- source: Materials Project (https://materialsproject.org/materials/mp-27)
- accessed: 2026-04-27T03:01:03.813692Z
- software: VASP (PAW pseudopotentials, PBE functional)
- theoretical: False
- material_id: mp-27
- formation_energy_per_atom: 0.5316 eV/atom
- e_above_hull: 0.5316 eV/atom (stability)
- structure_type: experimental

## Electronic Structure

- **Band gap**: 0.0 eV (metallic)
- **Conductor type**: Metal
- **Fermi level**: 9.1939 eV
- **Is metal**: True
- **Magnetic**: No
- **Functional**: PBE (GGA) — standard MP functional

## Thermodynamic Stability

- **Formation energy**: 0.5316 eV/atom
  → Thermodynamically unstable (positive formation energy)
- **Energy above hull**: 0.5316 eV/atom

## Total Energy

- **Energy per atom**: -8.242199 eV/atom
- **Volume**: 13.9539 Angstrom^3
- **Density**: 3.3422 g/cm^3

## Crystal Structure

Lattice (Angstrom): a=2.7023, b=2.7023, c=2.7023
Lattice angles: alpha=60.00, beta=60.00, gamma=60.00 deg
Space group: Fm-3m (IT No. 225)
Sites (1):
  Si: [0.000000, 0.000000, -0.000000]

## Physical Interpretation for Dirac/Octopus Comparison

Si is the canonical semiconductor test case from Octopus Tutorial 16 (periodic systems / optical spectra).
  Direct comparison: Octopus Tutorial 16 reports LDA bandgap ~0.5 eV.

## Comparison with Octopus Calculations

| Property | MP (VASP) | Octopus (this repo) | Notes |
|---|---|---|---|
| Band gap (eV) | 0.0000 | TBD (your run) | MP uses PAW; Octopus uses norm-conserving PP |
| Formation energy (eV/atom) | 0.5316 | TBD (your run) | Cross-check thermodynamic stability |
| Energy per atom (eV/atom) | -8.2422 | TBD (your run) | Per-atom comparison most robust |

## References

- Materials Project entry: https://materialsproject.org/materials/mp-27
- Methodology: https://docs.materialsproject.org/methodology/materials-methodology/calculation-details
