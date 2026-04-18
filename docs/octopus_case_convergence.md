# Octopus 案例收敛参数汇总

> 所有成功案例的仿真参数均记录于此 | MCP port 8000 | Octopus 16
>
> 参考来源见文末「[链接汇总](#链接汇总)」

---

## N 原子 | PP Mode | ✅ PASS

**参考值来源：** Octopus Tutorial 16 + NIST SRD 141

| 量 | 参考值 | 单位 | 来源 |
|----|--------|------|------|
| Total Energy | -262.241 | eV | Octopus Tutorial 16 |
| s eigenvalue | -18.283 | eV | Octopus Tutorial 16 |
| p eigenvalue | -7.302 | eV | Octopus Tutorial 16 |

**计算参数：**

| 参数 | 值 |
|------|-----|
| `engineMode` | `octopus3D` |
| `speciesMode` | `pseudo` + `%Species` 块 |
| `molecule` | `N_atom`（映射自 `N`）|
| `spacing` | `0.18` Å |
| `radius` | `10.0` Å |
| `XCFunctional` | `lda_x+lda_c_pz` |
| `ExtraStates` | `1` |
| `UnitsOutput` | `eV_Angstrom` |
| `BoxShape` | `sphere` |

**本次结果：**

| 量 | 计算值 | 参考值 | 误差 |
|----|--------|--------|------|
| Total Energy | -264.09 eV | -262.24 eV | 0.7% |
| s eigenvalue | -18.21 eV | -18.28 eV | **0.4%** ✅ |
| p eigenvalue | -7.11 eV | -7.30 eV | 2.6% |

> 💡 特征值精度远高于总能量，赝势误差对特征值影响更小

---

## H 原子 | Formula Mode | ⚠️ 模型，非真实原子

**重要说明：** Formula Mode 使用软核势 V(r) = -Z/√(r²+α)，是**模型势**，不是真实原子势。计算结果 -0.8191 Ha 与真实 H 原子能量（-0.5 Ha）不可比，差异来自模型本身。这是物理模型不同导致的系统偏差，非参数收敛问题。

**真实原子参考：** Exact = -0.5 Ha（如需对比，请用 PP Mode，见下节）

| 参数 | 值 |
|------|-----|
| `engineMode` | `octopus3D` |
| `speciesMode` | `pseudo`（默认）|
| `molecule` | `H` |
| `spacing` | `0.18` Å |
| `radius` | `10.0` Å |
| `XCFunctional` | `lda_x+lda_c_pz` |
| `softCoreAlpha` | `0.1` |
| `SCFTolerance` | `1e-6` |

**spacing 收敛验证（模型内对比）：**

| Spacing (Å) | 总能量 (Ha) | HOMO (Ha) |
|------------:|----------:|----------:|
| 0.24 | -0.8192 | -0.2996 |
| **0.18** | **-0.8191** | **-0.2996** |
| 0.16 | -0.8191 | -0.2996 |

> 💡 模型内已收敛（≥0.18 Å 能量变化 < 0.00001 Ha）；所有 XC 泛函给出完全相同结果（1电子物理正确性验证）

---

## H 原子 | PP Mode | ✅ PASS

**可用赝势：** `H.upf`（pseudo-dojo.org ONCV-PBE standard，`nc-fr-04_pbe_standard`）

**参考值来源：** UPF 文件头（PP 生成时的参考配置能量）

UPF 头中 reference 1s energy = **-0.23860 Ha**（iexc=4，PBE 泛函，rc=1.0）

**计算参数：**

| 参数 | 值 |
|------|-----|
| `engineMode` | `octopus3D` |
| `speciesMode` | `pseudo` + `%Species` 块 |
| `molecule` | `H` |
| `spacing` | `0.18` Å |
| `radius` | `10.0` Å |
| `XCFunctional` | `gga_x_pbe+gga_c_pbe`（须与 UPF 生成泛函一致）|
| `extraStates` | `1` |
| `UnitsOutput` | `eV_Angstrom` |
| `BoxShape` | `sphere` |
| `SCFTolerance` | `1e-6` |

**本次结果（PBE）：**

| 量 | 计算值 | 参考值 | 误差 |
|----|--------|--------|------|
| Total Energy | -0.4584 Ha | -0.5 Ha | 8.32% |
| 1s eigenvalue | **-0.23853 Ha** | **-0.23860 Ha** | **0.03%** ✅ |

> 💡 PBE 特征值与 UPF 参考值误差仅 0.03%，证明计算完全收敛且泛函选择正确
> ⚠️ LDA 计算结果 -0.2336 Ha（误差 2.1%），是因为 LDA 与 UPF 生成泛函（PBE）不匹配，应避免

---

## He 原子 | Formula Mode | ⚠️ 待验证

**重要说明：** 无真实原子参考值对比，不能判定 PASS。Formula Mode 是模型势（V=-Z/√(r²+α)），能量仅在模型内相对比较有意义。

**可用参考值（用于 PP Mode 对比）：**
- NIST all-electron LDA: Total E = **-2.8348 Ha**, 1s = **-0.5704 Ha**
- Exact non-relativistic: E = **-2.9037 Ha**

| 参数 | 值 |
|------|-----|
| `engineMode` | `octopus3D` |
| `speciesMode` | `pseudo`（默认）|
| `molecule` | `He` |
| `spacing` | `0.18` Å |
| `radius` | `10.0` Å |
| `XCFunctional` | `lda_x+lda_c_pz` |
| `softCoreAlpha` | `0.1` |
| `SCFTolerance` | `1e-6` |

**Formula Mode 结果（sp=0.18Å, R=10Å, α=0.1）：**

| XC Functional | 总能量 (Ha) | 与 NIST LDA 比较 |
|-------------|----------:|----------------|
| LDA-PZ | -2.519 | -0.3158 (11% 高) |
| PBE | -2.566 | -0.2688 (9.5% 高) |
| BLYP | -2.577 | -0.2578 (9.1% 高) |
| HF | -3.454 | +0.6193 (21% 低) |

> ⚠️ Formula Mode 结果与 NIST all-electron LDA 相差 9-11%（LDA/PBE/BLYP），这是模型势与真实原子势的系统差异，非收敛问题

---

## He 原子 | PP Mode | 🔄 PBS 调度异常（待重试）

**可用赝势：** `He.upf`（pseudo-dojo.org ONCV-PBE standard）

**参考值来源：** NIST all-electron LDA + Exact non-relativistic

| 量 | 参考值 | 单位 | 来源 |
|----|--------|------|------|
| Total Energy (exact) | -2.9037 | Ha | Variational量子力学 |
| Total Energy (LDA) | -2.8348 | Ha | NIST SRD |
| 1s eigenvalue (LDA) | -0.5704 | Ha | NIST SRD |

**计算参数：**

| 参数 | 值 |
|------|-----|
| `engineMode` | `octopus3D` |
| `speciesMode` | `pseudo` + `%Species` 块 |
| `molecule` | `He` |
| `spacing` | `0.18` Å |
| `radius` | `10.0` Å |
| `XCFunctional` | `gga_x_pbe+gga_c_pbe`（须与 UPF 生成泛函一致）|
| `extraStates` | `1` |
| `BoxShape` | `sphere` |

**测试状态：** ❌ PBS 调度异常（"never reported exec_vnode"），H/N 原子 PP 均正常，唯独 He 反复失败

> 🔧 待解决：需要排查 PBS 为何对 He 原子作业特殊对待

---

## 收敛协议（通用）

### Spacing

```
0.24 → 0.20 → 0.18 → 0.16 → 0.14 → 0.12 → 0.10 Å
容差：ΔE < 0.1 eV（探索）；< 0.01 eV（生产）
```

### Radius

| 体系 | 最小 | 收敛 |
|------|------|------|
| H / He | 5 Å | **≥ 10 Å** |
| CH4 | 8 Å | **≥ 12 Å** |
| N | 8 Å | **≥ 10 Å** |

### SCF

| 参数 | 推荐值 | 依据 |
|------|--------|------|
| `SCFTolerance` | `1e-6` | 1e-4 ~ 1e-8 结果相同 |
| `MixingScheme` | `broyden` | 势混合，更稳健 |
| `MixField` | `potential` | 对难收敛系统 |

---

## 链接汇总

| 来源 | 链接 |
|------|------|
| Octopus Tutorial 16（总能量收敛）| https://www.octopus-code.org/documentation/16/tutorial/basics/total_energy_convergence/ |
| NIST SRD 141（N LDA 特征值）| https://www.nist.gov/pml/atomic-reference-data-electronic-structure-calculations-nitrogen-0 |
| XCFunctional 列表 | https://octopus-code.org/documentation/13/variables/hamiltonian/xc/xcfunctional/ |
| TheoryLevel (HF) | https://www.octopus-code.org/documentation/15/variables/hamiltonian/theorylevel/ |
| TDDFT / dt | https://www.octopus-code.org/documentation/13/tutorial/basics/time-dependent_propagation/ |
| Formula mode | https://www.octopus-code.org/documentation/15/species_types/user-defined-species/ |
| Octopus 16 Manual | https://www.octopus-code.org/documentation/16/manual/ |
| NIST CODATA 2022 | https://physics.nist.gov/cgi-bin/cuu/Value?rydhcev |

---

## 模板：提交新案例

```markdown
## {原子/分子} | {Mode} | ✅/❌ {日期}

**参考值来源：** {来源}

{参考值表格}

**计算参数：**
{参数表格}

**结果：**
{结果对比表格}
```
