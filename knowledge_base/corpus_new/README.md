# Dirac Solver Knowledge Base — Corpus README

> **Last Updated**: 2026-04-16T17:15:00+08:00
> **Restructured By**: Sunshine (OpenClaw dirac-planner)
> **Policy**: Strict provenance; no orphaned benchmarks

---

## File Inventory

| File | Case ID | Tier | Status |
|------|---------|------|--------|
| `n_atom_gs_official.md` | `n_atom_gs_official` | **A-ready** | ✅ Verified from raw HTML (PRE table) |
| `ch4_gs_reference.md` | `ch4_gs_reference` | **A-ready** | ✅ Verified from raw HTML (PRE table) |
| `h2o_tddft_absorption_reference.md` | `h2o_tddft_absorption` | **B-tier** | ⚠️ Partial — window verified; tutorial URL not |
| `h2o_gs_reference.md` | `h2o_gs_reference` | **C-draft** | ❌ Provenance broken; DO NOT USE |
| `si_bandgap_reference.md` | `si_bandgap_reference` | **B-tier** | ⚠️ Sanity anchor only; not strict benchmark |
| `octopus_tutorial16_capability_matrix.md` | — | **B** | Capability inventory |
| `executor_guide.md` | — | **A-ready** | ✅ Input templates + verified parameters |

---

## Critical Correction Log (2026-04-16)

### N Atom Data — Units Clarification

**Original issue**: Some confusion about whether N atom energies are in Ha or eV.

**Resolution**: The raw data from the Octopus Tutorial 16 HTML (PRE 4 table) is in **Hartree (Ha)**. The CH₄ data (PRE 9) is in **eV** because the tutorial script explicitly sets `UnitsOutput = eV_Angstrom`. The N atom script does **not** set this variable, so Octopus defaults to **Ha**.

**Correct reference values at spacing = 0.18 Å:**

| Case | Quantity | Ha | eV |
|------|----------|-----:|-----:|
| N atom | Total Energy | **-262.24120934** | -7135.95 |
| N atom | s eigenvalue | **-18.282871** | -497.50 |
| N atom | p eigenvalue | **-7.302321** | -198.71 |
| CH₄ | Total Energy | -8.0216 | **-218.27963068** |

---

## Confidence Tier Definitions

| Tier | Definition | Use in Reviewer |
|------|------------|-----------------|
| **A-ready** | Has verifiable primary source URL + numeric values extracted directly from raw HTML | Full comparison with tolerance |
| **B-tier** | Has source but values need cross-verification, or values come from secondary/derivative source | Range/window check only |
| **C-draft** | Provenance incomplete or incorrect | **BLOCK** — must not be used for strict comparison |

---

## Inclusion Policy

A case is included only when at least one of the following exists:

1. **Official tutorial/manual URL** with numeric values extracted from raw HTML
2. **Published literature identifier** (DOI/arXiv) with local PDF/index evidence
3. **Explicitly tagged benchmark artifact** with reproducibility metadata

### Mandatory Fields for A-ready

- [ ] Stable `case_id` and observable identifier
- [ ] Primary source URL (type: `official_tutorial` or `paper`)
- [ ] Numeric reference value with unit discipline (Ha or eV)
- [ ] XC functional explicitly named (LDA / PBE / GGA / ...)
- [ ] Pseudopotential family or "all-electron" declaration
- [ ] Grid or k-mesh specification
- [ ] Geometry reference (equilibrium structure or coordinates)
- [ ] Confidence tier assigned

---

## Known Gaps (Action Items)

| Gap | Priority | Notes |
|-----|----------|-------|
| H₂O total energy reference | **P0** | Current value -76.4389 Ha is blocked (broken provenance) |
| H₂O TDDFT tutorial URL | P1 | Inferred; not directly verified from tutorial HTML |
| Si band gap computed value | P2 | Only guideline values available; exact tutorial output not extracted |
| H₂O geometry coordinates | P1 | Not yet in KB |
| N atom TDDFT (if needed) | P2 | No tutorial reference found |

---

## How to Add a New Reference Case

1. Create a `.md` file in `corpus_new/`
2. Fill in the provenance table with all mandatory fields
3. Assign confidence tier (A/B/C)
4. Add to `corpus_manifest.json`
5. Rebuild vector store

---

## Previous Errors (Corrected 2026-04-16)

| Error | Correction |
|-------|-----------|
| DOI `10.1063/1.445869` cited for H2O GS | Removed — DOI belongs to unrelated water potential paper |
| `literature-all-electron-reference` as software version | Removed — was fabricated placeholder |
| H2O GS -76.4389 Ha accepted without verification | Reclassified as C-draft; reviewer must block |
| N atom units ambiguous (Ha vs eV) | Confirmed: N atom = Ha (no override); CH4 = eV (UnitsOutput override) |
| 60+ expansion bank file referenced but not existing | Marked as forward reference only |
| executor had no tutorial parameter guidance | Added `executor_guide.md` with actual inp templates |
