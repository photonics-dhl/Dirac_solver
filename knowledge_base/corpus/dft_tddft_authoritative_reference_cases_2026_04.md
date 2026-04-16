# DFT TDDFT Authoritative Reference Cases (2026-04)

> ⚠️ **Correction log (2026-04-16)**: This file has been reviewed and corrected. Key changes:
> - H2O TDDFT and Si band gap sections: added provenance caveats that `@Octopus_docs/UI_User_Guide.md` is a system user guide, not an official Octopus tutorial or peer-reviewed benchmark
> - 60+ expansion bank: marked as non-existent (forward reference only)

This corpus is restricted to externally attributable references.

## Inclusion policy

A case is included only when at least one of the following exists:

- Official tutorial/manual URL with local evidence copy.
- Published literature identifier (DOI/arXiv) with local PDF/index evidence.
- Explicitly tagged benchmark artifact with reproducibility metadata.

## High-confidence contract (mandatory)

Every authoritative case should satisfy all of the following fields:

- Stable case id (`case_id`) and observable id (`observable_key`).
- Primary source link (`primary_url`) with source type (`official_tutorial` / `paper`).
- Local evidence pointer (`local_evidence_path`) to repository file(s).
- Reference numeric declaration with unit discipline (`reference_value`, `reference_unit`, or window list).
- Reproducibility metadata (`xc`, `pseudo_family`, `grid_or_kmesh`, `geometry_ref`).
- Confidence tier (`A-ready`, `B-needs-evidence`, `C-draft`).

If any mandatory field is missing, the case must not be tagged as `A-ready`.

## Reference Case: H2O TDDFT Absorption (Official tutorial target)

> ⚠️ **Provenance caveat (2026-04-16)**: The `local_evidence` field below points to `@Octopus_docs/UI_User_Guide.md` — a **system user guide** (Chinese language). This is a derivative source, not an official Octopus tutorial or a peer-reviewed benchmark. For strict provenance chains, treat the UI_User_Guide as a secondary/operational reference and always cite the primary official tutorial URL.

Reference source:

- Type: official tutorial (primary) + system user guide (secondary — ⚠️ see caveat above)
- Title (secondary source): Octopus UI User Guide section "H2O optical absorption spectrum"
- Public URL (primary authoritative): https://www.octopus-code.org/documentation/16/
- Local evidence (⚠️ secondary, not authoritative): @Octopus_docs/UI_User_Guide.md

Reference statement extracted (from UI_User_Guide.md):

- Expected first absorption peak is around 7-8 eV.
- UI_User_Guide source text: "第一个吸收峰约在 7–8 eV（H₂O 的 first singlet excitation ~7.5 eV，LDA 低估约 0.5 eV）"

Case usage in reviewer:

- Compare computed first significant peak against [7.0, 8.0] eV window.
- Report peak shift (computed minus reference center 7.5 eV).
- Report peak-energy RMSE when reference peak list is available.
- Keep integrated-intensity bias nullable when source does not provide absolute reference integral.
- Always note in the artifact that the reference is sourced from a UI user guide, not a peer-reviewed benchmark.

## Reference Case: Si band gap sanity anchor (Official tutorial + experiment note)

> ⚠️ **Provenance caveat (2026-04-16)**: Same issue as H2O — the `local_evidence` field points to `@Octopus_docs/UI_User_Guide.md`. The Si band gap values (LDA ~0.5 eV, experiment ~1.1 eV, GGA ~0.7 eV) appear to be textbook-level DFT knowledge but should be sourced from the actual Octopus Tutorial 16 page for strict provenance.

Reference source:

- Type: official tutorial (primary) + system user guide (secondary — ⚠️ see caveat above)
- Public URL (primary authoritative): https://www.octopus-code.org/documentation/16/
- Local evidence (⚠️ secondary, not authoritative): @Octopus_docs/UI_User_Guide.md

Reference statement extracted (from UI_User_Guide.md):

- LDA band gap around 0.5 eV, experiment around 1.1 eV, GGA around 0.7 eV.

Usage note:

- This is a model/systematic-bias sanity anchor, not a strict pass-fail scalar for every setup.

## Literature evidence index (local)

- knowledge_base/metadata/pdf_sources_index.md
- knowledge_base/metadata/pdf_download_status.json

Downloaded items currently include:

- arXiv:1207.0402
- arXiv:1511.05686

These are retained as source evidence assets in KB provenance.

## 60+ expansion bank

> ⚠️ **Correction notice (2026-04-16)**: The file `dft_tddft_authoritative_case_bank_60plus_2026_04.md` referenced below does **not** currently exist in the corpus directory. This is a forward reference only — the expansion bank has not been populated. Do not cite this as an active provenance source.

The addable high-trust expansion catalog is intended to be maintained at:

- `knowledge_base/corpus/dft_tddft_authoritative_case_bank_60plus_2026_04.md`

> ⚠️ **Local evidence caveat**: The file `@Octopus_docs/UI_User_Guide.md` cited as local evidence for the H2O absorption peak and Si band gap is a **system user guide** (Chinese language), not an official Octopus tutorial or a published benchmark document. It may contain values derived from the Octopus UI, not from peer-reviewed benchmarks. When citing these as references, also provide the actual tutorial URL (e.g., `https://www.octopus-code.org/documentation/16/`) as the authoritative provenance chain.
