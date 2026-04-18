# 开发经验与问题记录

> 2026-04-18 | Dirac_solver + Octopus MCP 开发过程中遇到的问题及解决方案

---

## 一、参数类 Bug（已修复）

### 1. `xc_functional` 参数被忽略（一直默认 LDA）

**症状：** 无论传 `PBE` / `HF`，始终用 LDA
**根因：** server.py 读取 `xcFunctional`（camelCase），但 MCP client 发 `xc_functional`（snake_case），Python dict key 严格区分大小写
**修复：**

```python
# server.py:816
xc_functional = config.get("xcFunctional", config.get("xc_functional", "lda_x+lda_c_pz"))
```

---

### 2. `softCoreAlpha` float 值被忽略

**症状：** `{"softCoreAlpha": 0.005}` 无任何效果，能量不变
**根因：** Octopus 要求 dict 格式 `{"_default": 0.1}`，直接传 float 被跳过
**修复：**

```python
_alpha_raw = config.get("softCoreAlpha", config.get("soft_core_alpha", None))
if _alpha_raw is not None:
    if isinstance(_alpha_raw, (int, float)):
        soft_core_alpha = {"_default": float(_alpha_raw)}  # float → dict
    else:
        soft_core_alpha = _alpha_raw
```

---

### 3. Hartree-Fock 报错 `symbol 'hf_x' used before being defined`

**症状：** `hartree_fock` 作为 `XCFunctional` 值传入 → Parser error
**根因：** `hartree_fock` 不是合法的 `XCFunctional` 标识符；正确方式是 `TheoryLevel = hartree_fock`
**修复：** HF 时单独处理，不走 XCFunctional 分支

---

### 4. PP Mode 缺少 `%Species` 块

**症状：** N 原子 PP Mode 计算失败
**根因：** PP mode 分支缺少 `%Species` 块生成代码（Formula mode 不需要）
**修复：** 新增 `_build_pseudo_species_block()` 函数

---

### 5. `molecule='N'` 未映射到 `'N_atom'`

**症状：** N 原子查不到 MOLECULES 字典
**修复：** 添加 `{"N": "N_atom"}` 映射

---

## 二、运行类问题（暂未解决）

### 6. PBS 作业调度异常（He 原子特有问题）

**症状：** He 原子 PP Mode 作业提交后始终报错 `"PBS job XXX never reported exec_vnode; job may not have run on a compute node"`
**对比：** H 原子 PP 和 N 原子 PP 均正常，唯独 He 反复失败
**已试方案：**
- 重试 10+ 次（间隔 5s~120s）
- 缩小 radius 8.0 Å
- 改大 spacing 0.20 Å
- 均无效
**待查：** PBS 配置是否对 He 原子有特殊限制？是否与 UDOCKER 容器内 He UPF 文件有关？
**临时方案：** 继续用 Formula Mode 做参数扫描，PP Mode 等 HPC 资源恢复

### 7. PBS 作业超时（exit code 231, signal 15）

**症状：** He 原子 PP Mode 作业被 HPC 调度系统强制 kill
**原因：** PBS 作业配置的最大 walltime 到期，实际计算还未完成
**临时方案：** 重试 / 减小体系规模 / 错峰提交

---

### 7. UDOCKER 容器内 GLIBC 不兼容

**症状：** playwright 在 HPC 上截图失败（GLIBC 2.25+ required, 实际 <2.25）
**影响：** 不影响 Octopus MCP 计算，只影响 UI 自动化测试
**方案：** HTTP 方式验证正常，playwright 作为 fallback

---

## 三、经验教训

### 1. `engineMode` 必须显式指定

- 默认值是 `"local1D"`（1D 简化模型），**结果完全错误**
- 任何 3D 计算必须传 `engineMode="octopus3D"`

### 2. PP Mode vs Formula Mode 不可混比

- Formula Mode 使用模型势 V(r) = -Z/√(r²+α)，能量与真实原子有系统性偏差
- N 原子 PP Mode 总能量 -264 eV vs Formula Mode -2.5 Ha，不是同一个量纲
- XC functional 的**相对顺序**（LDA < PBE < BLYP < HF）在两种模式下都符合物理预期，可用于收敛性验证

### 3. α 参数越小 → 越接近真实势，但收敛越慢

- α=0.1: sp=0.18Å 就收敛（快但不准）
- α=0.01: sp=0.10Å 才能收敛（慢但准）

### 4. 飞书通知有助于追踪异步 HPC 作业

- PBS 作业提交后无同步反馈，通过飞书通知各阶段状态可有效判断卡点位置

### 5. Octopus 长度单位默认是 Bohr，不是 Å

- 不显式标注单位时，spacing=0.18 会被当作 0.18 Bohr = 0.095 Å，差距巨大
- **始终设置** `octopus_length_unit="angstrom"` 或在输入文件加 `*angstrom`

### 6. Octopus 特征值比总能量更可靠

- PP Mode N 原子：s eigenvalue 误差 0.4%，总能量误差 0.7%
- 赝势误差对特征值影响更小

---

## 四、待解决问题

| # | 问题 | 优先级 | 备注 |
|---|------|--------|------|
| P1 | He 原子 PP Mode PBS 超时 | 高 | 需验证 UPF 文件是否可用 |
| P2 | PP Mode spacing 收敛扫描 | 高 | 尚未系统测试 0.18→0.14→0.12Å |
| P3 | Knowledge Base chromadb 未安装 | 中 | `/kb/query` 返回 HTTP 500 |
| P4 | All-Electron Mode 尚未测试 | 中 | 需要 `AllElectronType` 配置 |
| P5 | TDDFT / Casida 模式未测试 | 低 | 需确认 kernel 限制（GGA/HF只能用 LDA kernel）|
