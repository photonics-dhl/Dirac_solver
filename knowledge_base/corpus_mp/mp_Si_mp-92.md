# Si — Materials Project DFT Reference

**Formula**: Si  
**Material ID**: mp-92  
**Source**: [Materials Project](https://materialsproject.org/materials/mp-92)  
**Last Updated**: 2026-04-27T03:01:03.582471Z  
**Type**: Experimental  

## Provenance

- source: Materials Project (https://materialsproject.org/materials/mp-92)
- accessed: 2026-04-27T03:01:03.582451Z
- software: VASP (PAW pseudopotentials, PBE functional)
- theoretical: False
- material_id: mp-92
- formation_energy_per_atom: 0.2887 eV/atom
- e_above_hull: 0.2887 eV/atom (stability)
- structure_type: experimental

## Electronic Structure

- **Band gap**: 0.0 eV (metallic)
- **Conductor type**: Metal
- **Fermi level**: 8.8779 eV
- **Is metal**: True
- **Magnetic**: No
- **Functional**: PBE (GGA) — standard MP functional

## Thermodynamic Stability

- **Formation energy**: 0.2887 eV/atom
  → Thermodynamically unstable (positive formation energy)
- **Energy above hull**: 0.2887 eV/atom

## Total Energy

- **Energy per atom**: -8.485025 eV/atom
- **Volume**: 29.9000 Angstrom^3
- **Density**: 3.1195 g/cm^3

## Crystal Structure

Lattice (Angstrom): a=2.6585, b=3.6075, c=3.6075
Lattice angles: alpha=82.20, beta=68.38, gamma=68.38 deg
Space group: I4_1/amd (IT No. 141)
Sites (2):
  Si: [0.375000, 0.250000, 0.750000]
  Si: [0.625000, 0.750000, 0.250000]

## Physical Interpretation for Dirac/Octopus Comparison

Si is the canonical semiconductor test case from Octopus Tutorial 16 (periodic systems / optical spectra).
  Direct comparison: Octopus Tutorial 16 reports LDA bandgap ~0.5 eV.

## Comparison with Octopus Calculations

| Property | MP (VASP) | Octopus (this repo) | Notes |
|---|---|---|---|
| Band gap (eV) | 0.0000 | TBD (your run) | MP uses PAW; Octopus uses norm-conserving PP |
| Formation energy (eV/atom) | 0.2887 | TBD (your run) | Cross-check thermodynamic stability |
| Energy per atom (eV/atom) | -8.4850 | TBD (your run) | Per-atom comparison most robust |

## References

- Materials Project entry: https://materialsproject.org/materials/mp-92
- Methodology: https://docs.materialsproject.org/methodology/materials-methodology/calculation-details
