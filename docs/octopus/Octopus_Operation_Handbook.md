# Octopus Operation Handbook (Octopus 操作手册)

本手册旨在指导用户如何正确配置和运行 Octopus DFT 求解器，特别是在 Docker 环境下的使用步骤。

## 1. 核心概念与输入文件 (Core Concepts & Input)

Octopus 的运行核心是一个名为 `inp` 的文本文件。

### 1.1 输入文件规则
- **文件名必须为 `inp`**：Octopus 启动时会默认寻找当前路径下的 `inp` 文件。
- **语法格式**：变量名与数值之间使用 `=` 连接，注释使用 `#` 或 `!`。
- **变量分块**：某些变量（如原子坐标 `Coordinates` 或 种类 `Species`）使用 `%` 包裹的块结构。

### 1.2 常用变量 (Common Variables)
- `CalculationMode` (计算模式): 
    - `gs`: 基态计算 (Ground State)
    - `td`: 时域演化 (Time Dependent)
    - `unocc`: 计算未占据轨道 (Unoccupied)
- `Dimensions` (维度): 1, 2, 或 3。
- `Spacing` (网格间距): 数值越小精度越高，但计算量越大。
- `Radius` (仿真包围球半径): 定义计算区域的大小。
- `PeriodicDimensions` (周期性): `0` 为原子/分子，`1`-`3` 为晶体/超晶格。

### 1.3 高级物理变量 (Physics Advanced)
- **自旋与磁性**:
    - `SpinComponents = spin_polarized`: 开启自旋极化计算。
    - `SpinComponents = noncollinear`: 开启非共线自旋（用于 SOC）。
- **Hubbard U (DFT+U)**: 需要在 `%Species` 块中为特定原子添加 `hubbard_l` 和 `hubbard_u`。
- **自旋轨道耦合 (SOC)**: 需配合全相对论赝势，并设置 `SpinComponents = noncollinear`。

---

## 2. 命令行操作 (Command Line Operations)

### 2.1 核心命令与工具程序 (Core Utilities)
除了主程序 `octopus` 外，系统还包含一系列用于预处理、分析和后处理的辅助程序：

| 命令 (Command) | 描述 (Description - 中文注释) |
| :--- | :--- |
| `octopus` | **主求解器**：执行基态 (GS) 或时域 (TD) 密度泛函计算。 |
| `oct-propagation_spectrum` | **吸收光谱分析**：从 TD 偶极矩演化数据生成激发表。 |
| `oct-convert` | **格式转换**：将输出的网格数据转换为 Cube/XYZ/NetCDF 格式。 |
| `oct-casida_spectrum` | **Casida 光谱处理**：通过线性响应方法计算激发态光谱。 |
| `oct-harmonic-spectrum` | **高次谐波 (HHG)**：从 TD 电流/偶极数据提取 HHG 信号。 |
| `oct-vibrational_spectrum` | **振动分析**：计算分子的振动频率和红外光谱。 |
| `oct-center-geom` | **几何对齐**：将系统坐标平移至质心或网格中心。 |
| `oct-analyze_projections` | **投影分析**：分析 TD 态在 GS 轨道上的投影。 |
| `oct-atomic_occupations` | **原子占据数**：根据电子密度计算原子轨道的分布。 |
| `oct-conductivity` | **电导率**：基于时域电流计算系统的电导特性。 |
| `oct-dielectric-function` | **介电函数**：计算系统的频率相关介电响应。 |
| `oct-photoelectron_spectrum` | **光电子能谱 (PES)**：分析电子从体系中电离出的动力学。 |
| `oct-wannier90` | **Wannier 接口**：与 Wannier90 代码配合构建局域轨道。 |
| `oct-help` | **详细帮助**：查询任意输入变量的定义及其有效取值。 |

---

## 3. Docker 环境下的使用步骤 (Using Octopus with Docker)

### 3.1 环境准备
Octopus 已经在我们的 Docker 镜像 `dirac_octopus_mcp` 中正确安装（基于 Debian/Ubuntu 兼容环境）。

### 3.2 手动调试步骤
如果你需要手动进入 Docker 容器运行 Octopus：
1. **进入容器**:
   ```bash
   docker exec -it dirac_octopus_mcp bash
   ```
2. **定位工作目录**:
   ```bash
   cd /workspace
   ```
3. **运行仿真**:
   ```bash
   octopus
   ```

---

## 4. 输出文件与结果解读 (Output Interpretation)

Octopus 运行后会生成多个子文件夹：

### 4.1 关键输出路径
- `static/info`: **最重要的文件**。包含能量本征值 (Eigenvalues)、总能量 (Total Energy) 和收敛状态 (Convergence)。
- `exec/parser.log`: **调试利器**。记录了 Octopus 读取的所有参数（包括默认参数），用于排查输入错误。
- `restart/`: 存储断点续算信息。如果需要从头开始，可设置 `fromScratch = yes`。

---

## 5. 常见问题与排错 (Troubleshooting)

- **结果为空 (E=[])**:
    - 检查 `static/info` 是否生成。
    - 检查 `inp` 文件中的 `Spacing` 和 `Radius` 是否物理意义合理（例如半径太小会导致无法收敛）。
    - 确保原子坐标 `Coordinates` 没有重叠。
- **权限问题**: 在 Linux 容器中运行时，确保有写入当前目录的权限。
- **端口冲突**: 如果 Docker 服务无法启动，请检查 8000 端口是否被占用。

---

### 3.3 并行化配置 (Parallelization)
当处理大规模体系时，通过以下变量优化性能：
- `ParallelizationStrategy`: 组合并行模式，如 `states + domains`。
- `ParStates`: 分配给能级并行的进程数。
- `ParDomains`: 分配给空间网格分解的进程数。
- `ParKPoints`: 对于多 K 点计算（周期性体系）最有效的并行方式。

---

> [!TIP]
> **提示**：目前我们的系统已实现自动化。当你从 UI 界面点击“Initiate Computation”时，后端会自动执行上述所有步骤，包括生成 `inp`、运行 `octopus` 并解析 `static/info`。

---

## 6. 手动监控与连接验证 (Manual Monitoring & Verification)

如果你怀疑 UI 显示不及时或连接存在问题，可以使用以下命令手动监控：

### 6.1 监控实时日志 (Monitor Real-time Logs)
在 PowerShell 或 Ubuntu 终端运行，查看 Octopus 的实时输出：
```powershell
docker logs -f dirac_octopus_mcp
```

### 6.2 验证 WSL 内部连接 (Verify Internal Connection)
确保 Docker 容器内的 Python 服务器正在运行并监听 8000 端口：
```bash
# 进入容器
docker exec -it dirac_octopus_mcp bash
# 在容器内检查端口
netstat -tulpn | grep 8000
```

### 6.3 手动触发测试计算 (Manually Trigger Test)
可以通过 `curl` 在容器内手动触发一次计算来验证逻辑：
```bash
docker exec -it dirac_octopus_mcp curl -X POST http://localhost:8000/solve \
  -H "Content-Type: application/json" \
  -d '{"engineMode":"octopus3D", "moleculeName":"H2", "calcMode":"gs"}'
```

### 6.4 检查输出文件挂载 (Check Output Persistence)
验证计算结果是否正确同步到了宿主机的 `@Octopus_docs/output` 文件夹：
```powershell
ls "z:\.openclaw\workspace\projects\Dirac\@Octopus_docs\output"
```

---

## 7. 并行化性能优化 (Parallel Performance)

> **基准测试结论（2026-04-21，64核节点）**

### 7.1 体系规模与最优 mpirun -np 选择

| 体系规模 | 电子数 | 推荐 mpirun -np | 理由 |
|---------|:------:|:--------------:|------|
| 小分子（H, CH₄）| ~10 | **1** | 并行开销 > 收益，多核更慢 |
| 中等（乙醇 C₂H₅OH）| ~26 | **8-16** | 性价比最高 |
| 较大（~10水分子）| ~320 | **32** | 加速比 14.8x，效率 46% |
| 极大（蛋白等）| 1000+ | **32-64** | 继续往上效率持续下降 |

### 7.2 实测加速比（强缩放，(H₂O)×10 320电子）

| NP | 墙钟时间 | 加速比 | 并行效率 |
|:--:|--------:|:------:|:--------:|
| 1 | 2310s | 1.0x | 100% |
| 4 | 655s | 3.5x | 88% |
| 8 | 389s | 5.9x | 74% |
| 16 | 232s | 10.0x | 63% |
| 32 | 156s | **14.8x** | 46% |
| 48 | 143s | 16.2x | 34% |
| 64 | 137s | 16.9x | 26% |

**关键结论：**
- NP=32 是最优性价比点（加速比 14.8x，效率 46%）
- NP=64 只比 NP=32 快 12%，但浪费 2x 核数
- 乙醇（26电子）NP=32 后也趋于饱和

### 7.3 PBS 并行化脚本模板

```bash
#!/bin/bash
#PBS -N octopus_calc
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=04:00:00

source /data/apps/intel/2018u3/env.sh
WORKDIR="/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench"
cd "$WORKDIR"

# 每次运行前清理 restart（防止缓存污染时间）
rm -rf restart

export OMP_NUM_THREADS=1
export OCTOPUS_PAR_STATES=64
export OCTOPUS_PAR_DOMAINS=1
export OCTOPUS_PAR_KPOINTS=1

/data/home/zju321/.local/bin/udocker run \
    --workdir=/tmp \
    --volume="$WORKDIR:/tmp:ro" \
    --env=OMP_NUM_THREADS \
    --env=OCTOPUS_PAR_STATES \
    --env=OCTOPUS_PAR_DOMAINS \
    --env=OCTOPUS_PAR_KPOINTS \
    --env=LD_LIBRARY_PATH \
    bench_octopus \
    mpirun -np {NP} octopus > octopus.stdout 2>&1
```

### 7.4 PP Mode Species 块格式（易错！）

```octopus
%Species
  "C" | species_pseudo | set | standard | lmax | 1 | lloc | 0
  "H" | species_pseudo | set | standard | lmax | 1 | lloc | 0
%
```
**不要写 UPF 文件路径！** `species_pseudo | set | standard` 告诉 Octopus 自动查找 UPF 文件。

### 7.5 常见陷阱

1. **restart 缓存污染** — 不同并行配置共用 restart/ 会导致后续配置收敛极快（虚假结果），每次运行前 `rm -rf restart`
2. **stdin 重定向失效** — `mpirun octopus < inp` 在 PBS 环境下失败，用 volume mount + `--workdir=/tmp`
3. **H 原子 1电子场景** — 不适合并行测例，NP=1 即最优
4. **NP=64 vs NP=32** — 对 320e- 体系，NP=64 只快 12%，推荐 NP=32
