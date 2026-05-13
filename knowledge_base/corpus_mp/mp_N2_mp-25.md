# N2 — Materials Project DFT Reference

**Formula**: N2  
**Material ID**: mp-25  
**Source**: [Materials Project](https://materialsproject.org/materials/mp-25)  
**Last Updated**: 2026-04-27T03:01:07.446371Z  
**Type**: Experimental  

## Provenance

- source: Materials Project (https://materialsproject.org/materials/mp-25)
- accessed: 2026-04-27T03:01:07.446355Z
- software: VASP (PAW pseudopotentials, PBE functional)
- theoretical: False
- material_id: mp-25
- formation_energy_per_atom: 0.0018 eV/atom
- e_above_hull: 0.0018 eV/atom (stability)
- structure_type: experimental

## Electronic Structure

- **Band gap**: 7.3685 eV (indirect)
- **Conductor type**: Semiconductor/Insulator
- **Fermi level**: -6.8339 eV
- **CBM**: 0.4510 eV | **VBM**: -6.9175 eV
- **Is metal**: False
- **Magnetic**: No
- **Functional**: PBE (GGA) — standard MP functional

## Thermodynamic Stability

- **Formation energy**: 0.0018 eV/atom
  → Thermodynamically unstable (positive formation energy)
- **Energy above hull**: 0.0018 eV/atom
  → Ground state / very stable

## Total Energy

- **Energy per atom**: -9.126968 eV/atom
- **Volume**: 171.9276 Angstrom^3
- **Density**: 1.0823 g/cm^3

## Crystal Structure

Lattice (Angstrom): a=5.5605, b=5.5605, c=5.5605
Lattice angles: alpha=90.00, beta=90.00, gamma=90.00 deg
Space group: Pa-3 (IT No. 205)
Sites (8):
   N: [0.057397, 0.057397, 0.057397]
   N: [0.442603, 0.942603, 0.557397]
   N: [0.557397, 0.442603, 0.942603]
   N: [0.942603, 0.557397, 0.442603]
   N: [0.942603, 0.942603, 0.942603]
   N: [0.557397, 0.057397, 0.442603]
   N: [0.442603, 0.557397, 0.057397]
   N: [0.057397, 0.442603, 0.557397]

## Physical Interpretation for Dirac/Octopus Comparison


## Comparison with Octopus Calculations

| Property | MP (VASP) | Octopus (this repo) | Notes |
|---|---|---|---|
| Band gap (eV) | 7.3685 | TBD (your run) | MP uses PAW; Octopus uses norm-conserving PP |
| Formation energy (eV/atom) | 0.0018 | TBD (your run) | Cross-check thermodynamic stability |
| Energy per atom (eV/atom) | -9.1270 | TBD (your run) | Per-atom comparison most robust |

## References

- Materials Project entry: https://materialsproject.org/materials/mp-25
- Methodology: https://docs.materialsproject.org/methodology/materials-methodology/calculation-details
