# Si — Materials Project DFT Reference

**Formula**: Si  
**Material ID**: mp-16220  
**Source**: [Materials Project](https://materialsproject.org/materials/mp-16220)  
**Last Updated**: 2026-04-27T03:01:03.878502Z  
**Type**: Experimental  

## Provenance

- source: Materials Project (https://materialsproject.org/materials/mp-16220)
- accessed: 2026-04-27T03:01:03.878471Z
- software: VASP (PAW pseudopotentials, PBE functional)
- theoretical: False
- material_id: mp-16220
- formation_energy_per_atom: 0.3932 eV/atom
- e_above_hull: 0.3932 eV/atom (stability)
- structure_type: experimental

## Electronic Structure

- **Band gap**: 0.5334 eV (indirect)
- **Conductor type**: Semiconductor/Insulator
- **Fermi level**: 4.1234 eV
- **CBM**: 4.6059 eV | **VBM**: 4.0725 eV
- **Is metal**: False
- **Magnetic**: No
- **Functional**: PBE (GGA) — standard MP functional

## Thermodynamic Stability

- **Formation energy**: 0.3932 eV/atom
  → Thermodynamically unstable (positive formation energy)
- **Energy above hull**: 0.3932 eV/atom

## Total Energy

- **Energy per atom**: -8.380572 eV/atom
- **Volume**: 790.4309 Angstrom^3
- **Density**: 2.0061 g/cm^3

## Crystal Structure

Lattice (Angstrom): a=10.3783, b=10.3783, c=10.3783
Lattice angles: alpha=60.00, beta=60.00, gamma=60.00 deg
Space group: Fd-3m (IT No. 227)
Sites (34):
  Si: [0.500000, 0.500000, 0.500000]
  Si: [0.750000, 0.750000, 0.750000]
  Si: [0.389257, 0.389257, 0.389257]
  Si: [0.417772, 0.860743, 0.860743]
  Si: [0.860743, 0.417772, 0.860743]
  Si: [0.860743, 0.860743, 0.417772]
  Si: [0.389257, 0.832228, 0.389257]
  Si: [0.389257, 0.389257, 0.832228]
  Si: [0.832228, 0.389257, 0.389257]
  Si: [0.860743, 0.860743, 0.860743]
  ... (24 more sites)

## Physical Interpretation for Dirac/Octopus Comparison

Si is the canonical semiconductor test case from Octopus Tutorial 16 (periodic systems / optical spectra).
  MP LDA bandgap 0.533 eV vs experimental 1.1 eV — similar LDA underestimation to Octopus.
  Direct comparison: Octopus Tutorial 16 reports LDA bandgap ~0.5 eV.

## Comparison with Octopus Calculations

| Property | MP (VASP) | Octopus (this repo) | Notes |
|---|---|---|---|
| Band gap (eV) | 0.5334 | TBD (your run) | MP uses PAW; Octopus uses norm-conserving PP |
| Formation energy (eV/atom) | 0.3932 | TBD (your run) | Cross-check thermodynamic stability |
| Energy per atom (eV/atom) | -8.3806 | TBD (your run) | Per-atom comparison most robust |

## References

- Materials Project entry: https://materialsproject.org/materials/mp-16220
- Methodology: https://docs.materialsproject.org/methodology/materials-methodology/calculation-details
