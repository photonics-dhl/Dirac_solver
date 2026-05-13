# N2 — Materials Project DFT Reference

**Formula**: N2  
**Material ID**: mp-154  
**Source**: [Materials Project](https://materialsproject.org/materials/mp-154)  
**Last Updated**: 2026-04-27T03:01:07.395853Z  
**Type**: Experimental  

## Provenance

- source: Materials Project (https://materialsproject.org/materials/mp-154)
- accessed: 2026-04-27T03:01:07.395837Z
- software: VASP (PAW pseudopotentials, PBE functional)
- theoretical: False
- material_id: mp-154
- formation_energy_per_atom: 0.0000 eV/atom
- e_above_hull: 0.0000 eV/atom (stability)
- structure_type: experimental

## Electronic Structure

- **Band gap**: 7.3410 eV (indirect)
- **Conductor type**: Semiconductor/Insulator
- **Fermi level**: -6.8463 eV
- **CBM**: 0.4236 eV | **VBM**: -6.9174 eV
- **Is metal**: False
- **Magnetic**: No
- **Functional**: PBE (GGA) — standard MP functional

## Thermodynamic Stability

- **Formation energy**: 0.0000 eV/atom
  → Thermodynamically unstable (positive formation energy)
- **Energy above hull**: 0.0000 eV/atom
  → Ground state / very stable

## Total Energy

- **Energy per atom**: -9.128751 eV/atom
- **Volume**: 196.6400 Angstrom^3
- **Density**: 0.9462 g/cm^3

## Crystal Structure

Lattice (Angstrom): a=5.8151, b=5.8151, c=5.8151
Lattice angles: alpha=90.00, beta=90.00, gamma=90.00 deg
Space group: P2_13 (IT No. 198)
Sites (8):
   N: [0.063901, 0.063901, 0.063901]
   N: [0.436099, 0.936099, 0.563901]
   N: [0.563901, 0.436099, 0.936099]
   N: [0.936099, 0.563901, 0.436099]
   N: [0.954139, 0.954139, 0.954139]
   N: [0.545861, 0.045861, 0.454139]
   N: [0.454139, 0.545861, 0.045861]
   N: [0.045861, 0.454139, 0.545861]

## Physical Interpretation for Dirac/Octopus Comparison


## Comparison with Octopus Calculations

| Property | MP (VASP) | Octopus (this repo) | Notes |
|---|---|---|---|
| Band gap (eV) | 7.3410 | TBD (your run) | MP uses PAW; Octopus uses norm-conserving PP |
| Formation energy (eV/atom) | 0.0000 | TBD (your run) | Cross-check thermodynamic stability |
| Energy per atom (eV/atom) | -9.1288 | TBD (your run) | Per-atom comparison most robust |

## References

- Materials Project entry: https://materialsproject.org/materials/mp-154
- Methodology: https://docs.materialsproject.org/methodology/materials-methodology/calculation-details
