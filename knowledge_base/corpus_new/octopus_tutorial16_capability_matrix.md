# Octopus Tutorial 16 — Capability Matrix

> **Generated**: 2026-04-16 (re-extracted from official site)
> **Source**: https://www.octopus-code.org/documentation/16/
> **Version**: Octopus 16 (confirmed from container: `octopus 16.0 (git commit 7e864b450a)`)
> **Evidence Policy**: `manual_curation` (2026-04-16 correction: original `playwright_full_click_and_extract` was unverified)

## Tutorial Coverage Summary

| Category | Tutorials | Code Examples | Data Files | Priority |
|----------|----------:|-------------:|----------:|---------:|
| basics | 8 | 7 | 0 | **P0** |
| periodic_systems | 8 | 7 | 0 | **P0** |
| response | 7 | 6 | 0 | **P0** |
| model | 8 | 7 | 0 | P1 |
| hpc | 8 | 7 | 0 | P1 |
| unsorted | 20 | 19 | 0 | P1 |
| maxwell | 6 | 5 | 0 | P2 |
| multisystem | 5 | 4 | 0 | P2 |
| cecam_2024 | 1 | 0 | 0 | P2 |
| courses | 3 | 2 | 2 | P2 |
| landing | 1 | 0 | 0 | P2 |

**Total**: 75 tutorials across 11 categories.

## P0 Capabilities (Required for Core DFT/TDDFT Benchmarks)

### basics
| Tutorial | URL | Artifacts | Status |
|----------|-----|-----------|--------|
| Getting started | `/tutorial/basics/getting_started/` | code_block | ✅ |
| Basic input options | `/tutorial/basics/basic_input_options/` | code_block | ✅ |
| Total energy convergence | `/tutorial/basics/total_energy_convergence/` | code_block, image | ✅ **VERIFIED** |
| Time-dependent propagation | `/tutorial/basics/time-dependent_propagation/` | code_block, image | ✅ |
| Centering a geometry | `/tutorial/basics/centering_a_geometry/` | code_block | ✅ |
| Visualization | `/tutorial/basics/visualization/` | code_block, video | ✅ |
| Recipe | `/tutorial/basics/recipe/` | code_block, image | ✅ |

### periodic_systems
| Tutorial | URL | Artifacts | Status |
|----------|-----|-----------|--------|
| Getting started with periodic systems | `/tutorial/periodic_systems/periodic_systems/` | code_block, image | ✅ |
| Optical spectra of solids | `/tutorial/periodic_systems/optical_spectra_of_solids/` | code_block, image | ✅ |
| Band structure unfolding | `/tutorial/periodic_systems/unfolding/` | code_block, image | ✅ |
| Cell relaxation | `/tutorial/periodic_systems/cell_relax/` | code_block | ✅ |
| Sternheimer | `/tutorial/periodic_systems/sternheimer/` | code_block | ✅ |
| Wires and slabs | `/tutorial/periodic_systems/wires_and_slabs/` | code_block, image | ✅ |
| High-harmonic generation | `/tutorial/periodic_systems/hhg_1d_chain/` | code_block, image | ✅ |

### response
| Tutorial | URL | Artifacts | Status |
|----------|-----|-----------|--------|
| Optical spectra from time-propagation | `/tutorial/response/optical_spectra_from_time-propagation/` | code_block | ✅ |
| Optical spectra from Casida | `/tutorial/response/optical_spectra_from_casida/` | code_block | ✅ |
| Convergence of optical spectra | `/tutorial/response/convergence_of_the_optical_spectra/` | code_block | ✅ |
| Triplet excitations | `/tutorial/response/triplet_excitations/` | code_block | ✅ |
| Use of symmetries | `/tutorial/response/use_of_symmetries_in_optical_spectra_from_time-propagation/` | code_block | ✅ |
| Optical spectra from Sternheimer | `/tutorial/response/optical_spectra_from_sternheimer/` | code_block | ✅ |

## Verified Reference Cases from Capability Matrix

| Case ID | Category | Source Tutorial | Reference Values |
|---------|----------|-----------------|------------------|
| `n_atom_gs_official` | basics | Total energy convergence | E(spacing=0.18Å) = -262.24120934 Ha |
| `ch4_gs_reference` | basics | Total energy convergence | E(spacing=0.18Å) = -218.27963068 Ha |
| `h2o_tddft_absorption` | response | Optical spectra (inferred) | First peak ~7.5 eV |
| `si_bandgap_sanity` | periodic_systems | Optical spectra of solids | LDA gap ~0.5 eV; exp ~1.1 eV |

## Missing Capabilities (P2)

| Category | Gap |
|----------|-----|
| maxwell | Maxwell wave propagation tutorials exist but not integrated into DFT/TDDFT pipeline |
| multisystem | Multi-system coupling not yet benchmarked |
| cecam_2024 | No canonical cases selected |

## Notes

- All URLs use the base `https://www.octopus-code.org/documentation/16/`
- Image links have been corrected from double-slash (`//16/`) to single-slash (`/16/`) paths
- The "basic_input_options" tutorial contains the N atom pseudopotential example used in `n_atom_gs_official`
