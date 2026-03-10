# Octopus 16 Knowledge Base 🐙

This document serves as the technical reference for generating Octopus input files (`inp`) based on user-defined parameters.

## 1. Core Syntax and Structural Concepts

### Input File Structure (`inp`)
- **Key-Value Pairs**: `Variable = Value` (e.g., `CalculationMode = gs`).
- **Blocks**: Used for multi-column data like coordinates or species.
  ```octopus
  %BlockName
    Value1 | Value2 | Value3
  %
  ```
- **Delimiters**: Columns in blocks are separated by the pipe `|`.
- **Case Insensitivity**: Variable names are generally case-insensitive.
- **Unit Handling**: Octopus defaults to **Atomic Units** (Hartree/Bohr). Values can be explicitly scaled: `0.1 / eV` or `2.0 / Angstrom`.

---

## 2. Essential Input Variables

### Execution Control
| Variable | Description | Common Values |
| :--- | :--- | :--- |
| `CalculationMode` | Primary task for Octopus | `gs` (Ground State), `td` (Time Dependent), `unocc` (Unoccupied states), `opt` (Geometry optimization) |
| `Dimensions` | Dimensionality of the model | `1`, `2`, or `3` |
| `PeriodicDimensions` | Number of periodic directions | `0`, `1`, `2`, or `3` |

### Grid and Box Configuration
| Variable | Description | Notes |
| :--- | :--- | :--- |
| `Spacing` | Grid resolution | Dense grids (~0.1-0.2 Bohr) are needed for high accuracy. |
| `Radius` | Size of the simulation box | Half the extent for box shapes like `sphere` or `cylinder`. |
| `BoxShape` | Geometric constraints of the grid | `sphere`, `minimum`, `parallelepiped`, `cylinder` |

### Species and Coordinates
- **Standard Species**: Can use element symbols (e.g., "H", "C") if using pseudopotentials.
- **User Defined Species**:
  ```octopus
  %Species
    "MyParticle" | species_user_defined | potential_formula | "0.5*x^2" | valence | 1
  %
  ```
- **Coordinates**:
  ```octopus
  %Coordinates
    "MyParticle" | x | y | z
  %
  ```

---

## 3. Time-Dependent Propagation (TD)

### Basic TD Setup
To run TD, a converged GS must exist in the same directory.
- `CalculationMode = td`
- `TDPropagator = aetrs` (Approximated Enforced Time-Reversal Symmetry)
- `TDTimeStep = 0.05`
- `TDMaxSteps = 1000`

### External Fields (Lasers/Potentials)
Defined via the `%TDExternalFields` block:
```octopus
%TDExternalFields
  electric_field | 1 | 0 | 0 | 1.0 | "envelope_name"
%
```

---

## 4. Output and Data Extraction

### Output Options
Defined in the `%Output` block:
- `wfs`: Wavefunctions.
- `potential`: Total potential field (V_ks).
- `density`: Charge density.
- `OutputFormat`: `axis_x` (for 1D plots), `vtu` (3D visualization), or `netcdf`.

### Directory Structure
- `static/`: Ground state information and converged wavefunctions.
- `td.general/`: Time evolution data (multipoles, currents).
- `restart/`: Required files for continuing or branching calculations.

---

## 5. Automation Strategy (Natural Language to `inp`)

To map natural language to Octopus syntax:
1. **Identify Dimensionality**: `1D`, `2D`, or `3D` determines `Dimensions`.
2. **Determine Potential**: If user says "Harmonic", use `species_user_defined` with formula `"0.5*k*x^2"`.
3. **Parse Box**: "Large domain" implies a larger `Radius`.
4. **Select Mode**: "Evolution" maps to `td`, "Static" maps to `gs`.
5. **Scale Units**: Map "eV" or "Angstrom" to Octopus expressions (e.g., `* eV`).

---

## 6. Advanced Reference Data

### Common Molecular Coordinates
- **H2**: `%Coordinates \n "H" | 0 | 0 | -0.35 | "H" | 0 | 0 | 0.35 \n %`
- **Benzene**: Hexagonal ring in $xy$-plane with $d(C-C) \approx 1.4$ Å.

### Advanced Propagation
- **`TDTimeStep`**: Stability requires small steps (e.g., 0.01-0.05 Bohr/$\hbar$).
- **`TDFunctions`**: Defines time-envelopes (e.g., `tdf_cw`, `tdf_gaussian`).

## 7. Data Flow Logic (UI to Engine)
1. **Frontend**: Send JSON with `potentialType`, `wellWidth`, `moleculeName`, `calcMode`.
2. **Translation**: `server.py` maps these to `%Species` and `%Coordinates`.
## 8. 理解后处理结果 (Result Interpretation)

### 8.1 静态计算 (GS) 关键输出
- **`static/info`**: 这是分析的首选文件。包含：
    - **Total Energy**: 体系的总能量及其各分量。
    - **Eigenvalues**: 占据态和虚拟态的能级轨道能（单位为 Hartree）。
    - **Convergence**: 记录了 SCF 循环是否收敛。
- **`static/convergence`**: 可视化能量随迭代步数的变化，判断收敛稳定性。

### 8.2 时域演化 (TD) 关键输出
- **`td.general/dipole`**: 记录偶极矩随时间的变化。这是计算吸收光谱（UV-Vis）的基础。
- **`td.general/energy`**: 记录演化过程中的全能变化，用于分析非线性响应。
- **波函数与密度**: 在 TD 过程中，可以通过 `%Output` 块定时输出随时间变化的波函数。

---

## 9. 核心支持案例与应用 (Support Cases)

- **孤立原子/分子**:
    - 支持从 H, N 等原子到苯、甲烷等复杂分子的全电子或赝势计算。
    - **自旋极化 (Spin-polarization)**: 对于自由基或开壳层体系，需在 `inp` 中设置 `SpinComponents = spin_polarized`。
- **一维/二维模型体系**:
    - **量子点/人工原子**: 通过 `species_user_defined` 定义复杂的几何势能。
    - **有限势阱**: 模拟电子在限制势下的束缚态。
- **周期性体系**:
    - **超晶格与能带**: 通过定义晶格矢量（`LatticeVectors`）计算固体的电子能带结构。

---

## 10. 标准操作流程 (Standard Operating Procedures)

1. **预处理与准备**:
    - 确保 `inp` 变量逻辑闭环。
    - 使用 `oct-center-geom` 将复杂分子居中。
2. **基态寻优 (Ground State)**:
    - 运行 `octopus`。
    - 观察 `static/convergence`。若能量剧烈震荡，尝试减小 `Spacing` 或增加 `LSCFCalculateMixingLimit`。
3. **激发态/响应计算 (TD/Unocc)**:
    - 在 GS 收敛的基础上，切换 `CalculationMode`。
    - 配置激光场（`%TDExternalFields`）或运行 Unocc 模式获取激发能谱。
4. **数据综合分析**:
## 11. 详解输出文件夹与字段含义 (Output Deep Dive)

### 11.1 `static/info` - 计算摘要
这是评估物理结果最核心的文件，包含以下关键区块：

- **Grid (网格信息)**:
    - **Spacing**: 空间离散化步长。若该值过大，能量本征值将不准确。
    - **Grid Cutoff**: 基于网格步长的动能截断能（Hartree），反映了能量分辨率。
- **Eigenvalues (本征值表格)**:
    - **#st**: 能级序号（从最低能级开始）。
    - **Eigenvalue**: 该轨道的能量（单位：Hartree）。*注意：1 Hartree ≈ 27.2114 eV*。
    - **Occupation**: 该轨道的电子占据数。闭壳层通常为 2.0，空轨道为 0.0。
- **Energy (能量组分)**:
    - **Total**: 体系的总能量（判定化学稳定性）。
    - **Kinetic**: 电子动能。
    - **External**: 电子与原子核之间的吸引势能。
    - **Hartree**: 电子间的库仑排斥能。
- **Dipole (偶极矩)**:
    - 反映体系的电荷中心偏差。`[b]` 为 Bohr 单位，`[Debye]` 为德拜。

### 11.2 `static/convergence` - 收敛轨迹
记录了每一步 SCF (自洽场) 迭代的质量：
- **energy_diff**: 步间总能量差。理想情况下应逐渐减小并达到 `1e-6` 以下。
- **abs_dens / rel_dens**: 电荷密度的绝对/相对变化。如果密度不收敛，说明物理参数（如网格、占据数）可能设置错误。

### 11.3 `total-dos.dat` - 态密度 (Density of States)
- **Column 1 (Energy [H])**: 能量轴。
- **Column 2 (Total DOS)**: 该能量点处的态密度。峰值对应于电子能级的密集区域。
- 应用：通过绘制该文件可直观查看体系的能隙 (Band Gap) 或能带结构。

### 11.4 其他文件说明
- **`static/coordinates`**: 计算过程中实际使用的原子坐标（包含对称性处理后的结果）。
- **`exec/parser.log`**: 如果程序报错，检查该文件以确认 Octopus 是否正确解析了你的 `inp` 参数。

---

## 12. 进阶物理模型深度解析 (Advanced Physics Models)

### 12.1 自旋轨道耦合 (SOC)
- **原理**: 电子的自旋与轨道角动量相互作用，在重原子（如金、钨）和低维材料中至关重要。
- **Octopus 实施**:
    - 必须使用 **非共线自旋 (Non-collinear spin)** 设置。
    - 依赖于 **全相对论 (Fully-Relativistic) 赝势**。普通的标量相对论赝势不包含 SOC 效应。
- **能级表现**: 轨道会发生分裂（例如 $p$ 轨道分裂为 $j=1/2$ 和 $j=3/2$）。

### 12.2 DFT+U (Hubbard U) 修正
- **问题**: 标准 LDA/GGA 泛函在处理强相关电子（如过渡金属 $d$ 轨道或稀土 $f$ 轨道）时会产生过大的去局域化误差。
- **解决**: 通过 `hubbard_u` 参数引入一个局域惩罚能，强制电子更局域化，从而修正能隙和磁矩。

### 12.3 周期性边界与 K 点采样 (Periodic Systems)
- **布洛赫定理**: 在无限大的晶体中，波函数具有周期性。
- **K 点采样**: 由于在倒空间计算，需要通过一定数量的 K 点来近似 Brillouin 区的积分。
- **Monkhorst-Pack 网格**: Octopus 常用的均匀网格生成方法。网格越密（如 $8 \times 8 \times 8$），对固体的描述越精确。

### 12.4 线性响应与 Casida 方法
- **Time-Propagation (TD)**: “实时演化”。给体系一个脉冲，观察波函数随时间的变化。优点是适用强场、大振幅。
- **Casida 模式**: “频率映射”。直接求解一个激发态矩阵方程。优点是适用于分析特定的低能离散激发。
---

## 13. NetCDF Output Dataset Schema

When `OutputFormat = netcdf` is set, Octopus writes `.nc` files into `static/` or `td.general/` depending on the calculation mode.

### 13.1 Variables Present in Density Files (`density.nc`)

| Variable Name | Dimensions | Unit | Description |
| :--- | :--- | :--- | :--- |
| `density` | `(x, y, z)` | Bohr⁻³ | Total electron charge density |
| `x`, `y`, `z` | `(n)` | Bohr | Coordinate axes (grid points) |
| `density_up` | `(x, y, z)` | Bohr⁻³ | Spin-up density (spin-polarized only) |
| `density_down` | `(x, y, z)` | Bohr⁻³ | Spin-down density (spin-polarized only) |

### 13.2 Variables Present in Wavefunction Files (`wf-stNNNNN.nc`)

| Variable Name | Dimensions | Unit | Description |
| :--- | :--- | :--- | :--- |
| `wf_re` | `(x, y, z)` | Bohr⁻³/² | Real part of the orbital wavefunction |
| `wf_im` | `(x, y, z)` | Bohr⁻³/² | Imaginary part (zero for Γ-point real wavefunctions) |

### 13.3 Safe Extraction Patterns (Anti-OOM Rule)

```python
import xarray as xr, gc, numpy as np

# Pattern A: 1D slice (x-axis scan at y=0, z=0 — default for 1D models)
ds = xr.open_dataset("/workspace/output/static/density.nc", engine="scipy")
rho_1d = ds["density"].sel(y=0.0, z=0.0, method="nearest").values.tolist()
ds.close(); gc.collect()

# Pattern B: 2D cross-section (xy-plane at z=0)
ds = xr.open_dataset("/workspace/output/static/density.nc", engine="scipy")
rho_2d = ds["density"].sel(z=0.0, method="nearest").values.tolist()  # shape: (Nx, Ny)
ds.close(); gc.collect()

# Pattern C: Global min/max without loading full array (metadata probe)
ds = xr.open_dataset("/workspace/output/static/density.nc", engine="scipy")
summary = {
    "min": float(ds["density"].min()),
    "max": float(ds["density"].max()),
    "shape": list(ds["density"].shape),
}
ds.close(); gc.collect()
```

> **Critical**: Pattern C MUST be used before Pattern A or B to verify memory footprint.  
> Never simultaneously hold two open NetCDF datasets in the same Python process.

---

## 14. Advanced TDDFT Setup Reference

### 14.1 Recommended inp for TDDFT (DEV_LOCAL_COARSE profile)

```octopus
CalculationMode = td
Dimensions = 3
Spacing = 0.4      # Coarse grid (DEV profile: >= 0.2 Bohr)
Radius = 4.0       # (DEV profile: <= 5.0 Bohr)

TDPropagator = aetrs
TDTimeStep = 0.05
TDMaxSteps = 200   # (DEV profile: <= 200)

TDOutput = multipoles + energy + td_occup

%TDExternalFields
  electric_field | 1 | 0 | 0 | 0.05 | "my_pulse"
%

%TDFunctions
  "my_pulse" | tdf_gaussian | 1.0 | 0.0 | 10.0
%
```

### 14.2 Output Files Produced by TDDFT

| File | Path | Content |
| :--- | :--- | :--- |
| Dipole moment | `td.general/dipole` | Columns: `t`, `x`, `y`, `z` (all in Bohr/Hartree-time) |
| Total energy | `td.general/energy` | Columns: `t`, `E_total`, `E_kin`, `E_ext`, ... |
| Occupations | `td.general/td_occup` | Time evolution of orbital occupation |
| Absorbed energy | `td.general/absorption` | Frequency-domain spectrum after Fourier transform |

### 14.3 Post-Processing TDDFT: Absorption Spectrum

```python
import numpy as np

dipole = np.loadtxt("td.general/dipole", comments="#")
time = dipole[:, 0]      # Hartree-time units
dx   = dipole[:, 1]      # x-component dipole
dt   = time[1] - time[0]

# Fourier transform to frequency domain → absorption spectrum
freq = np.fft.rfftfreq(len(dx), d=dt)
strength = np.abs(np.fft.rfft(dx)) ** 2  # Oscillator strength proxy
omega_eV = freq * 27.2114               # Convert Hartree-freq to eV
```

---

## 15. Common Failure Patterns & Troubleshooting

| Symptom | Root Cause | Fix |
| :--- | :--- | :--- |
| `SCF not converged` after max iterations | Grid too coarse or mixing unstable | Reduce `Spacing` by 20%, add `MixingScheme = broyden` |
| Energy oscillates without decreasing | Degenerate states near Fermi level | Add `Smearing = 0.01` (Marzari-Vanderbilt) |
| `oct-status-aborted` in `exec/` | Octopus process crashed (OOM or bad inp) | Check `exec/messages` for Fortran traceback |
| `Spacing` warning: cutoff < 20 Hartree | Grid spacing too large for pseudopotential | Use `Spacing ≤ 0.2` for production runs |
| NetCDF file not generated | `OutputFormat` not set to `netcdf` | Add `OutputFormat = netcdf` to inp |
| Wavefunction files missing | `Output` block missing `wfs` | Add `%Output \n wfs \n %` |
| TD run fails at step 1 | GS restart files missing | Re-run GS first with `CalculationMode = gs` |
| Eigenvalue is `NaN` | Numeric overflow (grid too fine + large domain) | Check `Radius` × `Spacing` product — should be < 5000 points per axis |
| Memory OOM in Docker | 3D grid too large for 12 GB limit | Switch to DEV profile: `Spacing ≥ 0.2`, `Radius ≤ 5.0` |
| `parse error` in `exec/parser.log` | Typo in inp variable name | Check exact variable name in Octopus manual (case-insensitive but spelling is exact) |
