# HANDOFF.md

> Cross-session decision handoff. Update after key decisions, long-running tasks, or context resets.
> Pattern: Document & Clear — write here → `/clear` → new session reads this.

---

## Current Session Context (updated: 2026-05-15)

### Active Task
**DONE: H2O Casida PBE apple-to-apple** — 48 excitations, 17 KS states, PBE XC matched with TDDFT. Key agreement: Casida 8.95 eV ↔ TDDFT 8.83 eV (−0.12 eV). All 4 tasks complete.
**NEXT: None urgent.** Frontend spectrum already wired. Server running with all fixes applied.

### Key Decisions Made
- HANDOFF.md 由我主动维护，每次关键进度变更加立即写入，不等待 /clear
- 双保险：memory 文件兜底
- H2O ΔSCF 方法修正：O atom 通过 API 重算（job 150974, −15.734841 Ha）
- builtin_standard xcFunctional 限制：所有 builtin_standard 强制 LDA
- **server.py engine 字符串修正**: 5处 `"octopus-14.0"` → `"octopus-16.0"`（硬编码 bug，容器实际是 16.0）
- **H2O TDDFT 传播时间不足**: 350 steps × 0.005 a.u. = 1.75 a.u. (42 as) → 分辨率 98 eV。需 ≥17k steps
- **Casida mode added to server.py** (2026-05-14): new calcMode="casida", generate_inp is_casida branch, parse_octopus_casida(), API schema updated
- **Casida is PRIMARY method for finite molecules** (Octopus Tutorial 16 standard). Time-propagation is secondary cross-validation.
- **H2O Casida 1st excitation = 6.674 eV** — supersedes previous estimate (~7-8 eV B-tier) and hardcoded "6.570 eV" in plot script

### Blockers / Open Questions
- ~~PBE (pseudo) vs LDA (builtin_standard) XC mismatch~~ **RESOLVED**: PBE Casida run complete, apple-to-apple comparison done (8.95 ↔ 8.83 eV, −0.12 eV)
- ~~qstat exit_code bug~~ **FIXED**: server-side purge + PBS script rm -f (belt-and-suspenders)
- ~~Frontend TDDFT/Casida spectrum display~~ **VERIFIED**: already fully wired (CasidaSticks overlay in ResultsPanel.tsx)
- Find published H2O TDDFT benchmarks from literature (equivalent to Matsuzawa et al. for CH4) — still open
- `casida_executed: false` in API response despite valid Casida data — minor bug, not yet fixed

### H2O Casida PBE Results (2026-05-15)
- **48 excitations**, 17 KS states (CasidaKohnShamStates="1-16", ExtraStates=13)
- GS energy: −17.228019 Ha (PBE), SCF: 25 iter, converged
- 1st excitation: 6.953 eV (HOMO-LUMO gap match)
- **PBE Casida ↔ PBE TDDFT**: 8.946 eV ↔ 8.83 eV (−0.12 eV, excellent)
- PBE blue-shifts vs LDA: +0.28 eV (1st excitation)
- Data: `docs/tddft/data/h2o_casida_pbe_results.json`
- Docs updated: `octopus_case_convergence.md`, `octopus_user_guide.md`, `h2o_tddft_casida_reference.md`

### Server Fixes Applied (2026-05-15)
1. **PBE XC auto-selection** (line ~848): When `speciesMode="pseudo"`, auto-select `xc_functional="gga_x_pbe+gga_c_pbe"` unless user explicitly set XCFunctional.
2. **Stale exit_code poisoning** (line ~2012): PBS script cleans `octopus.exitcode` before execution.
3. **qstat exit_code bug FIXED** (line ~2076): Server-side purge of `octopus.exitcode` before polling loop. Belt-and-suspenders with PBS script fix.
4. **Casida eps_diff parsing** (line ~1482): Searches 4 candidate paths, auto-detects format, Hartree→eV conversion.
5. **Casida ExtraStates computation** (line ~1162): Derived from CasidaKohnShamStates range max instead of hardcoded 8.

### Server Fixes Applied (2026-05-14)
1. **TDTimeStep: NO compensation needed** (line ~1062): Octopus 16.0 interprets TDTimeStep correctly in a.u. ×27.2114 compensation was wrong.
2. **Configurable PBS walltime** (line ~1744-1787): `pbsWalltime` parameter + `_td_walltime_to_seconds()`.
3. **TD server timeout** (line ~2528): Matches PBS timeout. Min 3600s.
4. **ExtraStates floor softened** (line ~996): floor=4 (TD)/1 (GS).
5. **Casida mode**: `calcMode="casida"` — input generation, output parsing, API schema.
6. **_parse_length fixes** (×6): `float("10*angstrom")` crash resolved.
7. **Molecule case-insensitive lookup** (line ~677): `H2O` vs `h2o` → no longer defaults to H₂.
8. **ExtraStates for TD** (line ~1005): Now in common section, applies to GS/TD/Casida.

### Files Touched (cumulative)
- HANDOFF.md
- docker/workspace/server.py (Casida mode + _parse_length fixes + PBE XC auto-select + exit_code fix + case-insensitive molecule lookup + ExtraStates common section)
- docs/tddft/data/h2o_casida_results.json (A-tier LDA Casida reference)
- docs/tddft/data/h2o_casida_pbe_results.json (NEW — A-tier PBE Casida, 48 excitations)
- docs/tddft/data/h2o_tddft_timeprop_results.json (B-tier TDDFT cross-validation)
- docs/octopus_case_convergence.md (H2O Casida LDA + PBE entries)
- docs/octopus_user_guide.md (Casida H2O data + calcMode API)
- knowledge_base/corpus_new/h2o_tddft_casida_reference.md (PBE section added)
- knowledge_base/corpus_new/h2o_gs_pseudopotential_reference.md
- memory/learning/h2o_tddft_timeprop_cross_validation_20260515.md
- memory/learning/h2o_casida_pbe_cross_validation_20260515.md (NEW)
- memory/learning/h2o_pseudo_pbe_xc_fix_20260515.md
- memory/project/current_phase_20260514.md
- memory/MEMORY.md

### Next Step
1. ~~Run Casida with PBE XC~~ **DONE** — 48 excitations, 17 KS states
2. ~~Fix qstat exit_code bug~~ **DONE** — server purge + PBS script rm -f
3. ~~Wire frontend spectrum component~~ **VERIFIED** — already wired (CasidaSticks, TD+Casida overlay in ResultsPanel.tsx)
4. ~~Restart server.py~~ **RUNNING** — server.py PID 23739, all fixes active

---

## Session Archive

### 2026-05-14 — CLAUDE.md Progressive Disclosure Refactor
- **Decision**: Split 345-line CLAUDE.md into pointer-based ~140-line CLAUDE.md + 5 new rules/ files
- **What moved**:
  - Orchestration flow → `rules/orchestration.md`
  - Architecture details → `rules/architecture.md`
  - Common commands → `rules/commands.md`
  - Octopus 16.0 behavior → `rules/octopus-behavior.md`
  - VASP config → `rules/vasp-config.md`
- **Result**: CLAUDE.md reduced from 345 → ~140 lines. Body text in rules/, detailed workflows in docs/.
- **Rationale**: DataCamp + SitePoint progressive disclosure pattern — CLAUDE.md as pointer table, not encyclopedia.

### 2026-05-14 — Session Stall Root Cause Diagnosis
- **Finding**: Primary cause is Puppeteer MCP Chrome process leak (15 orphan processes, 1.2GB). Secondary: npx cold-start chain blocking, dead semantic-scholar MCP, DeepSeek API compatibility gaps.
- **Context**: DeepSeek v4-pro has 1M token context window — NOT the bottleneck. Project startup overhead ~55K tokens (5.5%).
- **Not fixed**: User explicitly forbade modifying settings.json, MCP config, or fixing API key leaks.
- **Relevant memory**: Session-stall diagnosis details in conversation transcript.
