# HANDOFF.md

> Cross-session decision handoff. **Auto-update before /clear.**
> Keep ≤ 80 lines. Only Current + Previous session. Archive older to `HANDOFF_archive.md`.

---

## Current Session (2026-05-23)

### Electron Cloud Stale Render Fix — Playwright E2E Verified

**User complaint**: 切换分子 preset 后电子云不变。

**Root cause**: Preset 按钮只改 config 参数，不清 `result` state → VisIt 面板继续显示旧分子的 render_snapshots。

**Fix**: `App.tsx` preset onClick handler 加 `setResult(null)` + `setLogs([preset msg])` 清除旧结果面板。

**Playwright E2E (ALL PASS)**:

| Step | Result | Detail |
|------|--------|--------|
| H₂O GS → render shows | ✅ | alt="渲染: H2O", 60218 bytes |
| Click CH₄ preset → render clears | ✅ | img count = 0 (result cleared) |
| Click H₂O GS preset → still clear | ✅ | img count = 0 (no stale data) |
| CH₄ GS → render shows | ✅ | alt="渲染: CH4", 32514 bytes |

**Code change**: `frontend/src/App.tsx` line ~1227 (preset onClick)

### Previous useMemo Fix Still Working
- `ResultsPanel.tsx` useMemo derivation (autoPng/manualPng/pngBase64) confirmed functional
- H2O 3D (48472 bytes) ≠ CH4 3D (30596 bytes) — renders are molecularly distinct

### Pending
- Professor UX evaluation
- Consider PBE TDDFT preset for better peak positions (7-10 eV range)

---

## Key Decisions (cumulative)
- HANDOFF.md **必须** 在 /clear 前自动更新
- Casida → LDA only (Octopus 16.0)
- E2E must run sequentially (concurrent collides on `octopus_latest`)
- `builtin_standard` → LDA XC; external PP → PBE XC
- UnitsOutput=eV_Angstrom changes ALL output units — parser must detect
- useMemo > useEffect for derived display state (stale closure elimination)
- **Preset click must clear result** — no stale cross-molecule renders
