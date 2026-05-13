# Octopus 知识参考手册

> **用途：** Octopus 输入文件语法、XC 泛函表、输出文件解析代码模板的快速查阅  
> **主指南：** 完整使用流程、模式选择、收敛验证、并行化配置请查阅 [octopus_user_guide.md](octopus_user_guide.md)  
> **版本：** Octopus 16.3

---

## 目录

1. [输入文件语法速查](#1-输入文件语法速查)
2. [XC 泛函参考表](#2-xc-泛函参考表)
3. [计算模式](#3-计算模式)
4. [输出文件解析代码](#4-输出文件解析代码)
5. [实用程序命令](#5-实用程序命令)

---

## 1. 输入文件语法速查

### 1.1 基础结构

```octopus
# 注释用 # 或 !
CalculationMode = gs          # 模式
UnitsOutput = eV_Angstrom    # 单位（可选）

# 块结构用 % 包裹
%Species
  "C" | species_pseudo | set | standard | lmax | 1 | lloc | 0
  "H" | species_pseudo | set | standard | lmax | 1 | lloc | 0
%

%Coordinates
  "C"  |  0.000000  |  0.000000  |  0.000000
  "H"  |  0.629118  |  0.629118  |  0.629118
%

Spacing = 0.18*angstrom
Radius = 10.0*angstrom
XCFunctional = gga_x_pbe+gga_c_pbe
BoxShape = sphere
MaxSCFIterations = 500
SCFTolerance = 1e-6
```

### 1.2 长度单位

> ⚠️ **默认单位是 Bohr（原子单位），不是 Å！**  
> 始终加 `*angstrom` 后缀，或在调用 API 时传 `{"octopus_length_unit": "angstrom"}`

```
1 Bohr = 0.529 Å
Spacing = 0.18 会被当作 0.18 Bohr = 0.095 Å → 结果完全错误
```

### 1.3 Species 块格式

#### PP Mode（伪势模式）
```octopus
%Species
  "C" | species_pseudo | set | standard | lmax | 1 | lloc | 0
  "H" | species_pseudo | set | standard | lmax | 1 | lloc | 0
%
```
**不要写 UPF 文件路径！** `species_pseudo | set | standard` 告诉 Octopus 自动查找 UPF 文件。

#### Formula Mode（模型势）
```octopus
%Species
  "H" | species_user_defined | potential_formula | "-1/sqrt(r^2+0.01)" | valence | 1
  "He" | species_user_defined | potential_formula | "-2/sqrt(r^2+0.01)" | valence | 2
%
```

#### All-Electron Mode（全电子）
```octopus
AllElectronType = all_electron_anc
```

### 1.4 周期性系统

```octopus
PeriodicDimensions = 3

#LatticeVectors
%LatticeVectors
  0.0   | 5.132 | 5.132
  5.132 | 0.0   | 5.132
  5.132 | 5.132 | 0.0
%

# 约化坐标
%ReducedCoordinates
  "Si" | 0.0  | 0.0  | 0.0
  "Si" | 0.25 | 0.25 | 0.25
%

# K 点网格
%KPointsGrid
  4 | 4 | 4
%
```

### 1.5 网格参数

| 参数 | 说明 | 典型值 |
|------|------|-------|
| `Spacing` | 网格间距（Bohr 或 angstrom）| 0.10–0.30 Bohr |
| `Radius` | 球形盒子半径 | 5–20 Bohr |
| `BoxShape` | 盒子形状 | sphere / minimum / parallelepiped / cylinder |
| `Lsize` | 平行六面体半长（各轴）| — |

```octopus
BoxShape = sphere          # 球形（默认）
BoxShape = minimum         # 各原子周围球形叠加（分子推荐）
BoxShape = parallelepiped  # 长方体（周期系统必须用）
```

### 1.6 并行化参数

```octopus
ParStates = 64     # KS 态并行
ParDomains = 1     # 域并行
ParKPoints = 1     # k 点并行
# MPI 进程数由 mpirun -np 控制
# 总核数 = mpirun_np × OMP_NUM_THREADS
```

---

## 2. XC 泛函参考表

### 2.1 LDA（第一阶梯）

| libxc 字符串 | 全名 | 备注 |
|:-------------|:----|:----|
| `lda_x+lda_c_pz` | LDA-PZ (Perdew-Zunger 1981) | **默认**，原子/分子均可靠 |
| `lda_x+lda_c_pw` | LDA-PW (Perdew-Wang 1992) | 稍高精度 |
| `lda_x+lda_c_vwn` | LDA-VWN5 | Gaussian 中常用 |

### 2.2 GGA（第二阶梯）

| libxc 字符串 | 全名 | 备注 |
|:-------------|:----|:----|
| `gga_x_pbe+gga_c_pbe` | PBE | **固态物理标准** |
| `gga_x_b88+gga_c_lyp` | BLYP | 有机化学热化学 |
| `gga_x_pbe_sol+gga_c_pbe_sol` | PBEsol | 固体晶格常数更准 |
| `gga_x_rpbe+gga_c_pbe` | RPBE | 化学吸附、表面反应 |

### 2.3 Meta-GGA（第三阶梯）

| libxc 字符串 | 全名 | 备注 |
|:-------------|:----|:----|
| `mgga_x_scan+mgga_c_scan` | SCAN | **最新最佳**，满足所有已知约束 |
| `mgga_x_tpss+mgga_c_tpss` | TPSS | 过渡金属、磁性系统 |
| `mgga_x_m06l+mgga_c_m06l` | M06-L | 主族热化学、活化能 |

### 2.4 杂化泛函（第四阶梯）

| libxc 字符串 | 全名 | HF 占比 | 备注 |
|:-------------|:----|:------:|:----|
| `hyb_gga_xc_b3lyp` | B3LYP | 20% | 有机化学引用最多 |
| `hyb_gga_xc_pbeh` | PBE0/PBEH | 25% | 固态+分子综合 |
| `hyb_gga_xc_hse06` | HSE06 | 25%（短程）| **半导体/带隙最佳** |

### 2.5 精确交换 / Hartree-Fock

```octopus
# ⚠️ 不能用 XCFunctional = hartree_fock（会报 hf_x undefined 错误）
# 正确方式：在 API 中传 xc_functional = "hartree_fock"
# server.py 会自动用 TheoryLevel = hartree_fock 处理
```

### 2.6 vdW 修正

```octopus
VDWCorrection = vdw_d3     # Grimme DFT-D3
VDWCorrection = vdw_ts     # Tkatchenko-Scheffler
```

---

## 3. 计算模式

| 值 | 描述 | 前置条件 |
|:---|:-----|:---------|
| `gs` | 基态 SCF | 无 |
| `td` | 含时 TDDFT | 收敛的 GS in `restart/gs/` |
| `unocc` | 未占据态 | 收敛的 GS |
| `opt` | 几何优化 | 无 |
| `em` | 线性响应 | 收敛的 GS |
| `vib` | 振动模式 | 收敛的 GS + opt |
| `casida` | Casida TDDFT | 收敛的 GS + unocc |

---

## 4. 输出文件解析代码

> 以下代码均假设 Docker 内 Octopus 输出在 `/workspace/output/`（宿主机挂载到 `docker/workspace/output/`）

### 4.1 `static/info` — 综合结果

```python
import re
from typing import TypedDict, Optional

class EigenvalueEntry(TypedDict):
    state: int
    spin: str
    eigenvalue_hartree: float
    occupation: float

class StaticInfoResult(TypedDict):
    converged: bool
    scf_iterations: Optional[int]
    total_energy_hartree: Optional[float]
    eigenvalues: list[EigenvalueEntry]
    homo_hartree: Optional[float]
    lumo_hartree: Optional[float]
    homo_lumo_gap_eV: Optional[float]
    dipole_debye: Optional[list[float]]

def parse_static_info(path: str) -> StaticInfoResult:
    with open(path, "r") as f:
        text = f.read()

    # 收敛状态
    conv_match = re.search(r"SCF converged in\s+(\d+)\s+iterations", text)
    converged = conv_match is not None
    scf_iter = int(conv_match.group(1)) if conv_match else None

    # 总能量
    energy_match = re.search(r"Total\s*=\s*([-\d.eE+]+)", text)
    total_energy = float(energy_match.group(1)) if energy_match else None

    # 本征值
    ev_block = re.search(
        r"#st\s+Spin\s+Eigenvalue\s+\[H\]\s+Occupation([\s\S]+?)(?:\n\n|\Z)",
        text
    )
    eigenvalues: list[EigenvalueEntry] = []
    if ev_block:
        for row in re.finditer(
            r"^\s*(\d+)\s+(\S+)\s+([-\d.eE+]+)\s+([\d.]+)",
            ev_block.group(1), re.MULTILINE
        ):
            eigenvalues.append({
                "state": int(row.group(1)),
                "spin": row.group(2),
                "eigenvalue_hartree": float(row.group(3)),
                "occupation": float(row.group(4)),
            })

    # HOMO / LUMO
    occupied = [e for e in eigenvalues if e["occupation"] > 0.5]
    unoccupied = [e for e in eigenvalues if e["occupation"] < 0.5]
    homo = occupied[-1]["eigenvalue_hartree"] if occupied else None
    lumo = unoccupied[0]["eigenvalue_hartree"] if unoccupied else None
    gap_eV = (lumo - homo) * 27.2114 if homo is not None and lumo is not None else None

    # 偶极矩
    dip_match = re.search(
        r"Dipole\s*(?:\[Debye\])?\s*[:=]?\s*"
        r"\(\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*\)",
        text
    )
    dipole = [float(dip_match.group(i)) for i in (1, 2, 3)] if dip_match else None

    return {
        "converged": converged,
        "scf_iterations": scf_iter,
        "total_energy_hartree": total_energy,
        "eigenvalues": eigenvalues,
        "homo_hartree": homo,
        "lumo_hartree": lumo,
        "homo_lumo_gap_eV": gap_eV,
        "dipole_debye": dipole,
    }
```

### 4.2 快速收敛判断

```python
def quick_convergence_check(info_path: str) -> tuple[bool, int]:
    """返回 (converged, num_iterations)。用于 retry 决策。"""
    with open(info_path, "r") as f:
        text = f.read()
    m = re.search(r"SCF converged in\s+(\d+)\s+iterations", text)
    return (m is not None, int(m.group(1)) if m else 0)
```

### 4.3 `static/convergence` — 收敛历史

```python
import numpy as np

def parse_convergence(path: str) -> dict:
    """列: iter, energy_diff, abs_dens, rel_dens"""
    data = np.loadtxt(path, comments="#")
    if data.ndim == 1:
        data = data.reshape(1, -1)
    return {
        "iterations": data[:, 0].tolist(),
        "energy_diff": data[:, 1].tolist(),
        "abs_dens": data[:, 2].tolist() if data.shape[1] > 2 else [],
    }
```

### 4.4 `static/wf-stNNNNN.y=0,z=0` — 1D 波函数切片

```python
import numpy as np, os, re, gc

def parse_wavefunction_1d(run_dir: str, state_index: int = 1) -> dict:
    filename = f"wf-st{state_index:05d}.y=0,z=0"
    path = os.path.join(run_dir, "static", filename)
    data = np.loadtxt(path, comments="#")
    return {
        "x_bohr": data[:, 0].tolist(),
        "wf_real": data[:, 1].tolist(),
        "wf_imag": data[:, 2].tolist() if data.shape[1] > 2 else [0.0] * len(data),
        "probability_density": (data[:, 1]**2 + (data[:, 2]**2 if data.shape[1] > 2 else 0)).tolist(),
    }
    del data; gc.collect()

def list_available_wavefunctions(run_dir: str) -> list[int]:
    static_dir = os.path.join(run_dir, "static")
    states = []
    for f in os.listdir(static_dir):
        m = re.match(r"wf-st(\d+)\.y=0,z=0", f)
        if m:
            states.append(int(m.group(1)))
    return sorted(states)
```

### 4.5 NetCDF 密度文件（防 OOM）

```python
# ⚠️ 永远不要返回完整 3D 数组到 Node.js！
import xarray as xr, gc

def parse_density_1d_slice(nc_path: str) -> dict:
    """提取 y=0, z=0 的 1D 密度剖面，不加载完整体积。"""
    ds = xr.open_dataset(nc_path, engine="scipy")
    try:
        rho = ds["density"].sel(y=0.0, z=0.0, method="nearest")
        return {
            "x_bohr": rho.coords["x"].values.tolist(),
            "density": rho.values.tolist(),
        }
    finally:
        ds.close()
        gc.collect()

def probe_density_metadata(nc_path: str) -> dict:
    """只返回 shape/min/max，不加载数据。先调用此方法确认网格大小。"""
    ds = xr.open_dataset(nc_path, engine="scipy")
    try:
        d = ds["density"]
        return {
            "shape": list(d.shape),
            "dims": list(d.dims),
            "min": float(d.min()),
            "max": float(d.max()),
            "n_points_total": int(d.size),
        }
    finally:
        ds.close()
        gc.collect()
```

### 4.6 TD 偶极矩与吸收谱

```python
import numpy as np, gc

def parse_td_dipole(path: str) -> dict:
    """列: t, dx, dy, dz（原子单位）"""
    data = np.loadtxt(path, comments="#")
    return {
        "time_au": data[:, 0].tolist(),
        "dipole_x": data[:, 1].tolist(),
        "dipole_y": data[:, 2].tolist(),
        "dipole_z": data[:, 3].tolist(),
    }
    del data; gc.collect()

def compute_absorption_spectrum(dipole_path: str, polarization: str = "x") -> dict:
    """通过 FFT 计算光吸收谱。"""
    data = np.loadtxt(dipole_path, comments="#")
    time = data[:, 0]
    col_map = {"x": 1, "y": 2, "z": 3}
    d = data[:, col_map[polarization]]
    dt = time[1] - time[0]
    freq_au = np.fft.rfftfreq(len(d), d=dt)
    strength = np.abs(np.fft.rfft(d)) ** 2
    return {
        "frequency_eV": (freq_au * 27.2114).tolist(),
        "oscillator_strength": strength.tolist(),
    }
    del data, d; gc.collect()
```

### 4.7 HDF5 / `.obf` 二进制文件

`.obf` 文件是 Octopus 私有二进制格式，不能直接解析。用容器内工具转换：

```bash
# 转换为 NetCDF（可用 xarray 解析）
oct-convert -i restart/gs/density.obf -o /workspace/output/density_converted.nc
```

### 4.8 TypeScript Zod Schema

```typescript
import { z } from "zod";

const EigenvalueSchema = z.object({
  state: z.number().int(),
  spin: z.string(),
  eigenvalue_hartree: z.number(),
  occupation: z.number(),
});

const ParsedResultsSchema = z.object({
  run_dir: z.string(),
  mode: z.enum(["gs", "td"]),
  info: z.object({
    converged: z.boolean(),
    scf_iterations: z.number().int().nullable(),
    total_energy_hartree: z.number().nullable(),
    eigenvalues: z.array(EigenvalueSchema),
    homo_hartree: z.number().nullable(),
    lumo_hartree: z.number().nullable(),
    homo_lumo_gap_eV: z.number().nullable(),
    dipole_debye: z.array(z.number()).length(3).nullable(),
  }).optional(),
  convergence: z.object({
    iterations: z.array(z.number()),
    energy_diff: z.array(z.number()),
    abs_dens: z.array(z.number()),
  }).optional(),
  available_states: z.array(z.number().int()),
  wavefunction_state1: z.object({
    x_bohr: z.array(z.number()),
    wf_real: z.array(z.number()),
    wf_imag: z.array(z.number()),
    probability_density: z.array(z.number()),
  }).optional(),
  density_metadata: z.object({
    shape: z.array(z.number().int()),
    dims: z.array(z.string()),
    min: z.number(),
    max: z.number(),
    n_points_total: z.number().int(),
  }).optional(),
  density_1d_slice: z.object({
    x_bohr: z.array(z.number()),
    density: z.array(z.number()),
  }).optional(),
});

export type ParsedOctopusResults = z.infer<typeof ParsedResultsSchema>;
```

---

## 5. 实用程序命令

| 命令 | 用途 | 示例 |
|:----|:----|:-----|
| `oct-propagation_spectrum` | TD 偶极矩 → FT → 吸收截面 | `oct-propagation_spectrum` |
| `oct-casida_spectrum` | Casida 光谱处理 | `oct-casida_spectrum` |
| `oct-convert` | 格式转换（cube/vtu/netcdf）| `oct-convert -i in.obf -o out.nc` |
| `oct-harmonic-spectrum` | 高次谐波（HHG）| `oct-harmonic-spectrum` |
| `oct-vibrational_spectrum` | 振动模式与红外光谱 | `oct-vibrational_spectrum` |
| `oct-analyze_projections` | TD 态投影分析 | `oct-analyze_projections` |
| `oct-conductivity` | 电导率（TD 电流）| `oct-conductivity` |
| `oct-dielectric-function` | 介电函数 | `oct-dielectric-function` |
| `oct-photoelectron_spectrum` | 光电子能谱（PES）| `oct-photoelectron_spectrum` |
| `oct-wannier90` | Wannier90 接口 | `oct-wannier90` |
| `oct-help` | 查询输入变量帮助 | `oct-help ParStates` |
