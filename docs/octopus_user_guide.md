# Octopus MCP 用户指南

> 如何通过 MCP Server（port 8000）提交 Octopus 计算任务

---

## 一、选择计算模式

### 三种模式对比

| 模式 | 何时用 | 关键参数 |
|------|--------|---------|
| **Formula** | 快速预览、参数扫描、TDDFT 预览 | `softCoreAlpha` |
| **PP** | 需与实验值对比的高精度计算 | `%Species` 块 + UPF 文件 |
| **All-Electron** | 轻元素（H, He, Li）高精度基准 | `allElectronType` |

**决策：**

```
需要和实验值对比吗？
  ├─ 否 → Formula Mode
  └─ 是 → 有 UPF 赝势文件吗？
            ├─ 是 → PP Mode
            └─ 否 → All-Electron Mode
```

> ⚠️ 默认 `engineMode="local1D"` 是 **1D 简化模型**，结果完全错误！任何 3D 计算必须显式指定 `"octopus3D"`

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

## 四、Octopus 长度单位：始终用 Å

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

## 五、如何验证计算是否收敛？

### 5.1 检查返回状态

```python
d = json.loads(resp.read())
print(d.get("status"))      # "success" 或 "error"
print(d.get("converged"))   # True / False
```

### 5.2 Spacing 扫描（推荐做法）

固定 radius=10 Å，扫 spacing：

```
0.24 → 0.20 → 0.18 → 0.16 → 0.14 → 0.12 → 0.10 Å
```

能量变化 < 0.01 eV 即认为收敛。

### 5.3 Radius 扫描

固定 spacing=0.18 Å，扫 radius：

```
5 → 8 → 10 → 12 → 15 → 20 Å
```

10 Å 以上能量不再变化即收敛。

---

## 六、Hartree-Fock 如何正确使用？

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

## 七、常见错误排查

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| 计算结果始终是 1D 量级 | 默认 `engineMode="local1D"` | 显式指定 `"octopus3D"` |
| 能量数量级完全不对 | 忘记设 `octopus_length_unit="angstrom"` | 始终加这个参数 |
| `softCoreAlpha` 无效 | 用了 float 而非 dict | 改 `{"_default": 0.1}` |
| N 原子算不出来 | `molecule="N"` 未映射 | 用 `"N_atom"` 或确认映射已加 |
| HF 报 `hf_x undefined` | `hartree_fock` 不能作 XCFunctional | 用 `"hartree_fock"` 触发 `TheoryLevel` |
| PBS 作业超时 | HPC walltime 到期 | 减小体系规模或重试 |
| 特征值始终不变 | `xc_functional` 被忽略（camelCase bug）| 确认 server.py 已修 |

---

## 八、相关文档

| 文档 | 位置 |
|------|------|
| 案例收敛参数 | [octopus_case_convergence.md](octopus_case_convergence.md) |
| 开发经验与问题记录 | [development_lessons_20260418.md](development_lessons_20260418.md) |
| HPC 完整操作手册 | [hpc-end-to-end-runbook-zh.md](hpc-end-to-end-runbook-zh.md) |
| OpenClaw 工作流总览 | [dirac_openclaw_full_workflow_status_*.md](dirac_openclaw_full_workflow_status_*.md) |
