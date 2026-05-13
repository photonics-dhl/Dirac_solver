---
name: octopus_parallel_perf
description: Use when running Octopus DFT/TDDFT calculations — select optimal mpirun -np and ParStates/ParDomains/OMP configuration for the system size. For new molecules or large systems, run a quick parallel scaling benchmark first.
---

# Octopus Parallel Performance Optimization Skill

## Use When
- Running any Octopus GS/TDDFT calculation on HPC
- System has >10 electrons (smaller systems don't benefit from parallelization)
- Available cores: 64-core node
- Want to minimize walltime per calculation

## Decision Tree: Which mpirun -np?

```
System size (electrons)?
├── < 20 e- (e.g. H, H2, CH4)
│   └── mpirun -np = 1  (多核反而更慢，开销大于并行收益)
│
├── 20-50 e- (e.g. ethanol C2H5OH, N2)
│   └── mpirun -np = 8-16
│
├── 50-200 e- (e.g. small molecules, water dimer)
│   └── mpirun -np = 16-32
│
└── > 200 e- (e.g. (H2O)10, proteins, solids)
    └── mpirun -np = 32  (最优性价比，效率~46%)
         (if time-critical: mpirun -np = 64, 效率~26%)
```

## Key Findings (from benchmark on 64-core node)

| Molecule | Electrons | NP=1 | NP=64 | Speedup | Optimal NP |
|----------|----------:|-----:|------:|--------:|:----------:|
| CH4 | 10 | 38s | N/A | — | **1** (并行无收益) |
| Ethanol | 26 | 125s | 11s | 11.4x | **8-16** |
| (H2O)10 | 320 | 2310s | 137s | 16.9x | **32** |

## PBS Job Template

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

## PP Mode Input: Critical Species Format

```octopus
%Species
  "C" | species_pseudo | set | standard | lmax | 1 | lloc | 0
  "H" | species_pseudo | set | standard | lmax | 1 | lloc | 0
  "O" | species_pseudo | set | standard | lmax | 1 | lloc | 0
%
```
**DO NOT use file paths in Species block** — `species_pseudo | set | standard` tells Octopus to auto-find the UPF file.

## Quick Benchmark Script (7 configs, ~30 min for ethanol)

```bash
# Location: run/bench/run_bench_STRONG_SCALING.sh
# PBS: 04:00:00 walltime
# Configs: NP=1,4,8,16,32,48,64

# Always clean restart between runs:
rm -rf restart

# Parse results:
grep '^[ ]*etot  =' octopus.stdout | awk '{print $3}' | tail -1
```

## Common Pitfalls

1. **restart 缓存污染** — 不同并行配置共用 restart/ 目录会导致后续配置收敛极快（虚假结果）。每次运行前 `rm -rf restart`。

2. **stdin 重定向失效** — `mpirun octopus < /tmp/inp` 在 PBS 环境下失败。用 volume mount: `--volume="$WORKDIR:/tmp:ro"` + `--workdir=/tmp`，Octopus 自动找 `/tmp/inp`。

3. **H 原子 1电子场景** — 不适合并行测例，NP=1 即最优。

4. **NP=64 vs NP=32** — 对 320e- 体系，NP=64 只比 NP=32 快 12%，但浪费 2x 核数。推荐 NP=32。
