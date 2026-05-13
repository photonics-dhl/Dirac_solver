# Si — Materials Project DFT Reference

**Formula**: Si  
**Material ID**: mp-109  
**Source**: [Materials Project](https://materialsproject.org/materials/mp-109)  
**Last Updated**: 2026-04-27T03:01:03.959626Z  
**Type**: Theoretical (DFT)  

## Provenance

- source: Materials Project (https://materialsproject.org/materials/mp-109)
- accessed: 2026-04-27T03:01:03.959608Z
- software: VASP (PAW pseudopotentials, PBE functional)
- theoretical: True
- material_id: mp-109
- formation_energy_per_atom: 0.2956 eV/atom
- e_above_hull: 0.2956 eV/atom (stability)
- structure_type: theoretical

## Electronic Structure

- **Band gap**: 0.0 eV (metallic)
- **Conductor type**: Metal
- **Fermi level**: 8.5379 eV
- **Is metal**: True
- **Magnetic**: No
- **Functional**: PBE (GGA) — standard MP functional

## Thermodynamic Stability

- **Formation energy**: 0.2956 eV/atom
  → Thermodynamically unstable (positive formation energy)
- **Energy above hull**: 0.2956 eV/atom

## Total Energy

- **Energy per atom**: -8.478145 eV/atom
- **Volume**: 59.8327 Angstrom^3
- **Density**: 3.1178 g/cm^3

## Crystal Structure

Lattice (Angstrom): a=3.5976, b=3.5976, c=5.2371
Lattice angles: alpha=108.14, beta=108.14, gamma=95.35 deg
Space group: Fmmm (IT No. 69)
Sites (4):
  Si: [0.727394, 0.272606, 0.000000]
  Si: [0.272606, 0.727394, 0.000000]
  Si: [0.779769, 0.779769, 0.559539]
  Si: [0.220231, 0.220231, 0.440461]

## Physical Interpretation for Dirac/Octopus Comparison

Si is the canonical semiconductor test case from Octopus Tutorial 16 (periodic systems / optical spectra).
  Direct comparison: Octopus Tutorial 16 reports LDA bandgap ~0.5 eV.

## Comparison with Octopus Calculations

| Property | MP (VASP) | Octopus (this repo) | Notes |
|---|---|---|---|
| Band gap (eV) | 0.0000 | TBD (your run) | MP uses PAW; Octopus uses norm-conserving PP |
| Formation energy (eV/atom) | 0.2956 | TBD (your run) | Cross-check thermodynamic stability |
| Energy per atom (eV/atom) | -8.4781 | TBD (your run) | Per-atom comparison most robust |

## References

- Materials Project entry: https://materialsproject.org/materials/mp-109
- Methodology: https://docs.materialsproject.org/methodology/materials-methodology/calculation-details
