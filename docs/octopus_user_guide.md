# Dirac Solver 用户指南

> 如何通过 MCP Server（port 8000）提交 Octopus / VASP 计算任务
>
> **更新日期**：2026-05-12 | **计算引擎**：Octopus 16 + VASP 6.x (PAW-PBE)

---

## 一、选择计算模式

### 四种模式对比

| 模式 | 何时用 | 关键参数 |
|------|--------|---------|
| **Formula** | 快速预览、参数扫描、TDDFT 预览 | `softCoreAlpha` |
| **PP** | 需与实验值对比的高精度计算 | `%Species` 块 + UPF 文件 |
| **All-Electron** | 轻元素（H, He, Li）高精度基准 | `allElectronType` |
| **VASP** | 高精度 DFT 计算（PAW-PBE），可与实验对比 | `engineMode: "vasp"`（前端切换） |

**决策（直接 API 调用，Octopus）：**

```
需要和实验值对比吗？
  ├─ 否 → Formula Mode
  └─ 是 → 有 UPF 赝势文件吗？
            ├─ 是 → PP Mode
            └─ 否 → All-Electron Mode
```

**前端引擎切换：**

Web 界面顶部三个引擎按钮：
- **Local 1D** — 1D 简化模型（仅教学，无物理意义）
- **Octopus 3D** — Octopus DFT（Formula / PP / builtin_standard）
- **VASP** — VASP PAW-PBE（高精度，紫色按钮）

> ⚠️ 默认 `engineMode="local1D"` 是 **1D 简化模型**，结果完全错误！任何 3D 计算必须切换引擎。

---

## 二、Formula Mode 操作步骤

### 2.1 最小请求示例

```python
import urllib.request, json

url = "http://127.0.0.1:8000/solve"
payload = json.dumps({
    "case_id": "he_test",
    "engineMode": "octopus3D",
    "speciesMode": "pseudo",
    "molecule": "He",
    "xc_functional": "lda_x+lda_c_pz",
    "spacing": 0.18,
    "radius": 10.0,
    "scf_tolerance": 1e-6,
    "calculation_type": "ground_state",
    "octopus_length_unit": "angstrom",
    "softCoreAlpha": 0.1,
    "extraStates": 10
}).encode()

req = urllib.request.Request(url, data=payload,
    headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=150) as resp:
    d = json.loads(resp.read())
    print("Total energy:", d.get("total_energy"), "Ha")
    print("Eigenvalues:", d.get("eigenvalues"))
```

### 2.2 为什么要设 `softCoreAlpha`？

Octopus Formula Mode 使用软核势：

```
V(r) = -Z / √(r² + α)
```

- **α 作用：** 消除 r=0 处的奇异性，避免数值崩溃
- **α=0.1：** 势较浅 → 收敛快（spacing 0.18 Å 就够）→ **物理精度低**
- **α=0.01：** 势更深 → 更接近真实原子 → 但需要 spacing 0.10 Å 才能收敛
- ⚠️ `softCoreAlpha` 必须是 **dict 格式** `{"_default": 0.1}` 才能生效（float 格式会被忽略）

### 2.3 为什么 `xc_functional` 有时无效？

server.py 读取 camelCase 参数名，但很多客户端发 snake_case：

```python
# 旧写法（可能不生效）
{"xc_functional": "gga_x_pbe+gga_c_pbe"}  # ❌ 被忽略，始终 LDA

# 正确写法（2026-04-18 修复后两种都可以）
{"xcFunctional": "gga_x_pbe+gga_c_pbe"}  # ✅ camelCase
{"xc_functional": "gga_x_pbe+gga_c_pbe"}  # ✅ snake_case
```

---

## 三、PP Mode 操作步骤

### 3.1 为什么需要 `%Species` 块？

PP Mode 使用真实赝势文件（UPF），必须告诉 Octopus：
- 哪些元素用赝势
- 赝势的 lmax、lloc 参数

### 3.2 如何查找可用赝势文件？

```bash
ssh dirac-key
find /data/home/zju321/.udocker -name "*.upf" 2>/dev/null | head -20
```

### 3.3 PP Mode 请求示例

```python
import urllib.request, json

url = "http://127.0.0.1:8000/solve"
payload = json.dumps({
    "case_id": "n_pp_test",
    "engineMode": "octopus3D",
    "speciesMode": "pseudo",
    "molecule": "N",          # 会自动映射到 N_atom
    "xc_functional": "lda_x+lda_c_pz",
    "spacing": 0.18,
    "radius": 10.0,
    "scf_tolerance": 1e-6,
    "calculation_type": "ground_state",
    "octopus_length_unit": "angstrom",
    "extraStates": 1
}).encode()
```

> ⚠️ MCP server 会自动生成 `%Species` 块；如需自定义，可直接修改 `docker/workspace/server.py` 中的 `_build_pseudo_species_block()` 函数

### 3.4 PP Mode vs Formula Mode 能混用吗？

**不能。** 两者物理模型不同：

| 对比项 | Formula Mode | PP Mode |
|--------|-------------|---------|
| 势能模型 | V=-Z/√(r²+α)（模型势）| 真实赝势（UPF）|
| 总能量 | 与真实原子有偏差 ~0.3–1 Ha | 可与实验对比 |
| 特征值 | 模型相关 | 接近真实原子 |
| 收敛速度 | 快 | 慢 |

---

## 四、VASP PAW-PBE 模式

> **引擎**：VASP 6.x (`/data/software/AMD/vasp_std`)
> **赝势库**：标准 potpaw_PBE.54 (`/data/home/Hzk-14/pot/potpaw_PBE.54/`)
> **端点**：`POST /solve_vasp`（port 8000）
> **参考数据**：`knowledge_base/corpus_new/vasp_gs_reference.md`

### 4.1 前端使用（推荐）

Web 界面点击 **VASP** 引擎按钮（紫色），配置面板自动显示 VASP 参数：

**系统配置：** 分子预设下拉（H, He, C, N, O, CH₄, H₂O, CO）、3D 分子预览（Mol3DViewer）、自定义原子坐标（X/Y/Z）

**SCF 控制：** `ENCUT`（截断能，默认 400 eV，高精度 520 eV）、`EDIFF`（SCF 收敛阈值，默认 1e-6 eV）、`NELMIN`（最小迭代步数，默认 5）、`ISMEAR`（展宽，默认 0 = Gaussian）、`SIGMA`（展宽宽度，默认 0.01 eV）

**电子控制：** `NELECT`（总电子数，ΔSCF 时修改）、`NBANDS`（能带数）、K-Points（Gamma-only / Monkhorst-Pack）、Precision（Normal / Accurate）、Box Size（默认 10 Å）

**交换关联：** PBE（默认推荐）、LDA、Hartree-Fock；自旋：Unpolarized / Polarized

### 4.2 直接 API 调用

```python
import urllib.request, json

url = "http://127.0.0.1:8000/solve_vasp"
payload = json.dumps({
    "octopusMolecule": "H2O",
    "molecule": "H2O",
    "xcFunctional": "PBE",
    "spinComponents": "unpolarized",
    "encut": 520,
    "ediff": 1e-6,
    "ismear": 0,
    "sigma": 0.01,
    "kpointsType": "gamma",
    "vaspBox": 10.0,
    "prec": "Accurate"
}).encode()

req = urllib.request.Request(url, data=payload,
    headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=300) as resp:
    d = json.loads(resp.read())
    print("Total energy:", d.get("total_energy_ev"), "eV")
    print("Fermi energy:", d.get("fermi_energy_ev"), "eV")
    print("Magnetization:", d.get("magnetization"))
    print("Eigenvalues:", d.get("eigenvalues_ev"))
```

**返回字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | `"success"` / `"error"` |
| `total_energy_ev` | float | PAW-PBE 总能量 (eV) |
| `fermi_energy_ev` | float | 费米能级 (eV) |
| `magnetization` | float | 磁矩 (μB) |
| `eigenvalues_ev` | float[] | KS 本征值列表 (eV) |
| `occupations` | float[] | 占据数列表 |
| `nelect` | float | 总电子数 |
| `nbands` | int | 能带数 |
| `scf_iterations` | int | SCF 迭代步数 |
| `execution_strategy` | string | `"direct"`（登录节点）或 `"pbs"`（PBS 作业调度）|

### 4.3 核心概念：PAW 绝对能量 ≠ 全电子能量

**这是 DFT 赝势方法的核心特征，不是计算错误。**

| 概念 | 全电子 | PAW 赝势 |
|------|--------|---------|
| H 原子能量 | -13.6 eV (-0.500 Ha) | **-1.1 eV** (-0.041 Ha) |
| 能量零点 | 裸核 + 自由电子 | 赝原子参考态 |

**可比性：**
- ✅ **原子化能**（ΔE）：零点偏移在减法中抵消
- ✅ **磁矩**：由电子占据数决定，与赝势无关
- ✅ **特征值简并模式**：由对称性决定
- ❌ **绝对总能量**：不同赝势零点不同，不可直接比较

> **验证方法**：用原子化能（如 CH₄ → C + 4H）与实验对比。PBE 典型误差 +8–10%（已知过度结合倾向）。

### 4.4 已验证参考数据

**原子（PAW-PBE，ENCUT=520 eV，spin-polarized）：**

| 原子 | Etot (eV) | Mag (μB) | HOMO (eV) | 基态 |
|------|-----------|-----------|-----------|------|
| H | -1.1182 | 1.00 | -7.55 | ²S |
| C | -1.2513 | 2.00 | -5.99 | ³P |
| N | -3.1241 | 3.00 | -8.21 | ⁴S |
| O | -1.5364 | 2.00 | -10.14 | ³P |

**分子（PAW-PBE，gamma-only，闭壳层）：**

| 分子 | Etot (eV) | Mag (μB) | HOMO (eV) | LUMO (eV) | Gap (eV) |
|------|-----------|-----------|-----------|-----------|----------|
| CH₄ | -24.0241 | 0.00 | -9.31 | -0.52 | 8.79 |
| H₂O | -14.2120 | 0.00 | -7.09 | -0.99 | 6.10 |

**二原子分子（PAW-PBE，gamma-only，H₂/N₂ 闭壳层，O₂ 三重态）：**

| 分子 | Etot (eV) | Mag (μB) | HOMO (eV) | LUMO (eV) | Gap (eV) |
|------|-----------|-----------|-----------|-----------|----------|
| H₂ | -6.7693 | 0.00 | -10.36 | -0.17 | 10.19 |
| N₂ | -16.6166 | 0.00 | -10.05 | -1.83 | 8.21 |
| O₂ | -9.8365 | 2.00 | -6.68 | -0.30 | 6.38 |

**原子化能验证：**

| 分子 | ΔE PBE (eV) | 实验 ATcT (eV) | 误差 |
|------|------------|---------------|------|
| CH₄ | 18.31 | 17.02 | +7.6% |
| H₂O | 10.44 | 9.51 | +9.8% |
| H₂ | 4.53 | 4.48 | +1.2% |
| N₂ | 10.37 | 9.76 | +6.3% |
| O₂ | 6.76 | 5.12 | +32.2% |

> ⚠️ O₂ 解离能偏差 +32% 是 GGA 泛函对三重态 ³Σg⁻ 多参考效应的已知系统误差（见 `octopus_case_convergence.md`）。

> 详见 `knowledge_base/corpus_new/vasp_gs_reference.md`。

### 4.5 前端参数 ↔ API 字段对照

| 前端参数 | API 字段 | 默认值 |
|---------|---------|--------|
| ENCUT | `encut` | 400 |
| EDIFF | `ediff` | 1e-6 |
| NELMIN | `nelmin` | 5 |
| ISMEAR | `ismear` | 0 |
| SIGMA | `sigma` | 0.01 |
| NELECT | `nelect` | (不传) |
| K-Points | `kpointsType` | `"gamma"` |
| Precision | `prec` | `"Normal"` |
| Box Size | `vaspBox` | 10.0 |
| XC Functional | `xcFunctional` | `"PBE"` |
| Spin | `spinComponents` | `"unpolarized"` |

---

## 五、Octopus 长度单位：始终用 Å

**默认单位是 Bohr（原子单位），不是 Å！**

```
1 Bohr = 0.529 Å
Spacing = 0.18 会被当作 0.18 Bohr = 0.095 Å → 结果完全错误
```

**正确做法：**

```python
{"octopus_length_unit": "angstrom"}  # ✅ 显式标注
```

或在输入文件加 `*angstrom` 后缀：

```
Spacing = 0.18*angstrom
Radius = 10.0*angstrom
```

---

## 六、如何验证计算是否收敛？

### 6.1 检查返回状态

```python
d = json.loads(resp.read())
print(d.get("status"))      # "success" 或 "error"
print(d.get("converged"))   # True / False
```

### 6.2 Spacing 扫描（推荐做法）

固定 radius=10 Å，扫 spacing：

```
0.24 → 0.20 → 0.18 → 0.16 → 0.14 → 0.12 → 0.10 Å
```

能量变化 < 0.01 eV 即认为收敛。

### 6.3 Radius 扫描

固定 spacing=0.18 Å，扫 radius：

```
5 → 8 → 10 → 12 → 15 → 20 Å
```

10 Å 以上能量不再变化即收敛。

---

## 七、TDDFT 激发态计算

> **引擎**：Octopus（Casida + 实时 TDDFT）
> **验证基准**：CH₄ Casida 第一激发态 9.17 eV vs Tutorial 16 参考 9.278 eV（误差 1.1%）
> **并行策略**：ParDomains 分解实空间网格，详见 benchmark 结果

### 7.1 两种 TDDFT 方法对比

| 方法 | 何时用 | 耗时 | 输出 |
|------|--------|------|------|
| **Casida** | 前几个激发态能量 + 振子强度 | 秒~分钟（单次对角化）| 激发能、振子强度 |
| **实时 TDDFT** | 宽带吸收谱、强场动力学 | 分钟~小时（时间传播）| `cross_section_vector` 吸收谱 |

### 7.2 Casida 方法（线性响应）

**原理**：在 GS 波函数基础上对角化 Casida 方程（电子-空穴对耦合矩阵），一次对角化给出所有激发态。

**请求示例**（先跑 GS，再跑 Casida）：
```python
# Step 1: Ground State
payload = json.dumps({
    "case_id": "ch4_gs",
    "engineMode": "octopus3D",
    "speciesMode": "pseudo",
    "molecule": "CH4",
    "xc_functional": "lda_x+lda_c_pz",
    "spacing": 0.18, "radius": 10.0,
    "octopus_length_unit": "angstrom",
    "calculation_type": "ground_state",
    "extraStates": 8
}).encode()

# Step 2: Casida (uses restart/gs from Step 1)
payload = json.dumps({
    "case_id": "ch4_casida",
    "engineMode": "octopus3D",
    "speciesMode": "pseudo",
    "molecule": "CH4",
    "xc_functional": "lda_x+lda_c_pz",
    "spacing": 0.18, "radius": 10.0,
    "octopus_length_unit": "angstrom",
    "calculation_type": "casida",
    "extraStates": 8
}).encode()
```

**CH₄ 验证结果（LDA，2026-05-12）**：
| 激发态 | 能量 (eV) | 振子强度 | 特征 |
|--------|----------|---------|------|
| 1st | 9.17 | 0.0865 | HOMO(t₂)→LUMO(a₁*) |
| 2nd | 9.89 | 0.0018 | HOMO→virtual t₂* |
| 3rd | 10.34 | 0.0312 | deeper→LUMO |

> **Petersilka 近似**：对角核近似（9.18 eV）与完整 Casida（9.17 eV）几乎一致，简单体系可加速。

### 7.3 实时 TDDFT（Delta-Kick）

**原理**：施加瞬时电场脉冲（delta-kick），实时传播 KS 轨道，傅里叶变换诱导偶极矩得吸收谱。

**关键参数**：
| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `TDTimeStep` | 0.02 a.u. (~0.48 as) | 时间步长 |
| `TDMaxSteps` | 10000 | 总步数（200 a.u. ≈ 4.84 fs）|
| `TDDeltaStrength` | 0.005 a.u. | 脉冲强度（弱场线性响应）|
| `TDPolarizationDirection` | 1 | 偏振方向（1=x, 2=y, 3=z）|
| `TDPropagator` | `aetrs` | 近似强制时间反演对称（推荐）|
| `TaylorExpansionOrder` | 4 | AETRS 展开阶数 |

**并行配置（64核节点，已验证）**：
```
mpirun -np 4 + OMP_NUM_THREADS=16 + ParDomains=4 + ScaLAPACKCompatible=yes
→ 42.9 TD steps/sec（N₂，~1M 格点），1.43x vs 纯 OMP
```

| 体系规模 | 格点数 | 推荐配置 |
|----------|--------|---------|
| 双原子 (N₂) | ~1M | np=4, omp=16 |
| 小分子 (CH₄, H₂O) | ~0.5-1M | np=4, omp=16 |
| 较大分子 | >2M | np=8, omp=8 |
| 超大体系 | >5M | np=16, omp=4 |

> ⚠️ np ≥ 16 时 MPI 通信开销超过收益。np=64（纯 MPI）比纯 OMP 还慢（20 vs 30 steps/sec）。

### 7.4 Udocker 容器复用（关键）

```bash
# ❌ 错误 — 每次创建新容器（~40s tar 解压开销）
udocker run registry.gitlab.com/octopus-code/octopus:16.0 /app/bin/octopus

# ✅ 正确 — 复用已有容器（零开销）
CONTAINER=$(udocker ps | grep octopus | head -1 | awk '{print $1}')
udocker run --volume=/data/home/zju321:/data/home/zju321 \
  --env="OMP_NUM_THREADS=16" $CONTAINER \
  bash -c "cd /workdir && mpirun -np 4 --bind-to core /app/bin/octopus"
```

### 7.5 运行时间估算（10000 步）

| 体系 | 纯 OMP (64核) | 最优 (np=4) |
|------|-------------|------------|
| N₂ (~1M 格点) | ~5.6 min | ~3.9 min |
| CH₄ (~0.8M) | ~4.5 min | ~3.1 min |
| H₂O (~0.5M) | ~3 min | ~2 min |

---

## 八、Hartree-Fock 如何正确使用？

**不能**用 `XCFunctional = hartree_fock`（会报 `hf_x undefined` 错误）

**正确方式：**

```python
# MCP 请求中不需要传 XCFunctional
# server.py 会自动将 HF 映射为 TheoryLevel = hartree_fock
payload = json.dumps({
    "case_id": "he_hf",
    "xc_functional": "hartree_fock",  # 内部用 TheoryLevel 处理
    ...
})
```

原理：Hartree-Fock 是 `TheoryLevel` 而非 `XCFunctional`，LibXC 中不存在 `hf_x` 这个泛函标识符。

---

## 九、常见错误排查

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| 计算结果始终是 1D 量级 | 默认 `engineMode="local1D"` | 显式指定 `"octopus3D"` |
| 能量数量级完全不对 | 忘记设 `octopus_length_unit="angstrom"` | 始终加这个参数 |
| `softCoreAlpha` 无效 | 用了 float 而非 dict | 改 `{"_default": 0.1}` |
| N 原子算不出来 | `molecule="N"` 未映射 | 用 `"N_atom"` 或确认映射已加 |
| HF 报 `hf_x undefined` | `hartree_fock` 不能作 XCFunctional | 用 `"hartree_fock"` 触发 `TheoryLevel` |
| PBS 作业超时 | HPC walltime 到期 | 减小体系规模或重试 |
| 特征值始终不变 | `xc_functional` 被忽略（camelCase bug）| 确认 server.py 已修 |
| VASP 返回 "No POTCAR" | 元素不在 potpaw_PBE.54 库中 | 检查元素符号，仅支持 H/C/N/O 及其组合 |
| VASP SCF 不收敛 | ENCUT 过低或初始电荷密度差 | 提高 ENCUT 到 520 eV，确保 ISTART=0/ICHARG=2 |
| VASP 磁矩错误 | ISPIN 设置不对 | 原子用 `polarized`，闭壳层分子用 `unpolarized` |
| VASP 前端 404 | Vite proxy 配置缺少 `/solve_vasp` | 确认 `vite.config.ts` 包含 `/solve_vasp` 代理到 port 8000 |
| Casida 报 "Previous gs calculation is required" | Casida 需要 GS 重启文件 | 先跑 GS（`FromScratch=yes`），再跑 Casida（`FromScratch=no`）|
| TDDFT 并行性能不升反降 | `ParDomains` ≠ `mpirun -np` 或 np 过大 | np ≤ 8（双原子体系），确保 ParDomains=np |
| 第一次 udocker run 快，后续变慢 | 每次 `udocker run <image>` 创建新容器（~40s tar 开销）| 用 `udocker run <container_id>` 复用已有容器 |
| `ScaLAPACKCompatible = yes` 报 Fatal Error | ScaLAPACKCompatible 是实验性功能 | 必须同时设置 `ExperimentalFeatures = yes` |
| `TDOutput = cross_section_vector` 报 parser error | 该变量不存在，cross_section_vector 自动生成 | 删除 `TDOutput` 行，吸收谱文件会自动输出到 `td.general/cross_section_vector` |
| TDDFT 达不到 64 核线性加速 | 小体系（<2M 格点）轨道数少，并行度受限 | 纯 OMP 比 MPI+OMP 混合更稳定，实际利用率 ~22-45 核 |

---

## 十、相关文档

| 文档 | 位置 |
|------|------|
| 案例收敛参数（Octopus + VASP）| [octopus_case_convergence.md](octopus_case_convergence.md) |
| VASP PAW-PBE 参考数据 | [../knowledge_base/corpus_new/vasp_gs_reference.md](../knowledge_base/corpus_new/vasp_gs_reference.md) |
| 开发经验与问题记录 | [development_lessons_20260418.md](development_lessons_20260418.md) |
| OpenClaw 工作流总览 | [dirac_openclaw_full_workflow_status_*.md](dirac_openclaw_full_workflow_status_*.md) |
| VASP 后端实现 | [../docker/workspace/vasp_backend.py](../docker/workspace/vasp_backend.py) |
| VASP 前端配置 | [../frontend/src/App.tsx](../frontend/src/App.tsx) (engineMode: 'vasp') |
