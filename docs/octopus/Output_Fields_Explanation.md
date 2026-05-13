# Octopus 输出文件深度解析指南 (Output Analysis Guide)

本文档旨在详细解释 Octopus 计算完成后 `output` 文件夹中各文件的物理含义及数据格式。

## 1. `static/info` (核心结果摘要)
这是分析计算是否成功、物理量是否合理的首选文件。

### 1.1 网格与环境 (Grid)
- **Spacing**: 空间离散步长（Bohr）。值越小，计算越精确，但内存消耗呈立方增长。
- **Grid Cutoff**: 动能截断。衡量网格能够描述的最高电子动能。

### 1.2 本征值表格 (Eigenvalues)
| 字段 | 含义 | 备注 |
| :--- | :--- | :--- |
| **#st** | 能级序号 | 从基态开始排序。 |
| **Eigenvalue** | 轨道能量 (Hartree) | 能量越负表示束缚越紧。1 H ≈ 27.2114 eV。 |
| **Occupation** | 占据数 | 2.0 代表闭壳层占据；0.0 代表空轨道。 |

### 1.3 能量组成 (Energy breakdown)
- **Total Energy**: 体系的总能量。
- **Kinetic**: 电子动能（始终为正）。
- **External**: 电子与原子核之间的势能（始终为负）。
- **Hartree**: 电子间的静电排斥能。
- **Exchange/Correlation**: 交换相关能（量子力学修正）。

---

## 2. `static/convergence` (收敛曲线数据)
该文件记录了迭代过程，若计算未收敛，需通过此文件排查：
- **energy_diff**: 相邻两步的能量差。
- **abs_dens**: 电荷密度的变化。
- **提示**: 如果迭代步数达到上限但 `energy_diff` 仍很大，说明需要调整 `Spacing` 或增加 `LSCFCalculateMixingLimit`。

---

## 3. `total-dos.dat` (态密度)
- **横轴 (Energy)**: 能量，通常以费米能级为中心参考。
- **纵轴 (DOS)**: 状态密度。
- **用途**: 峰值位置反映电子最可能存在的能量区间。若两个峰之间有很宽的 0 区域，说明存在能隙 (Band Gap)。

---

## 4. 后处理建议流程
1. 检查 `info` 文件开头的 **"SCF converged!"** 标志。
2. 查看 `Eigenvalues` 确认 HOMO (最高占据轨道) 和 LUMO (最低未占据轨道) 的能量。
3. 如果是 TD 计算，请查阅 `td.general/dipole` 以获取动力学信息。
