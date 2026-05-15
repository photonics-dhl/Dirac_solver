# HPC Operations & Monitoring

> Extracted from CLAUDE.md — hardware topology, parallel strategy, PBS monitoring.

---

## HPC 硬件拓扑

| Node | CPU | Cores | NUMA nodes | Cores/NUMA |
|------|-----|-------|-----------|------------|
| cn01-cn15 | Intel Xeon Platinum 8369B | 64 | 2 | 32 |
| fat01 | AMD EPYC 7H12 | 128 (64 alloc) | 8 | 16 |

**并行策略**：
- 小体系（~1M grid points, ≤16 KS states）：纯 OMP (np=1, OMP_NUM_THREADS=64) — MPI overhead 不值得
- 大体系（>5M grid points）：`mpirun -np 4` + `OMP_NUM_THREADS=16` + `ParDomains=4`
- Intel Xeon: `--map-by socket --bind-to socket`
- AMD EPYC: `--map-by numa --bind-to numa`

---

## 监控注意事项

- **NFS 输出缓冲**：PBS 脚本 shell 重定向到 NFS 文件可能延迟数小时。用 `wc -l td.general/energy` 追踪进度，不依赖重定向日志
- **PBS CPU vs Walltime**：`qstat` "Time Use" 显示 CPU 时间（user+system），非 walltime。多线程作业 CPU 时间 = 10-20× walltime。用 `qstat -f JOBID | grep walltime` 取真实耗时
- **PBS 目录碰撞**：同时运行的作业共享同一工作目录会相互破坏 input/state。不同计算类型用独立目录

## PBS 作业监控命令

```bash
qstat -f JOBID | grep -E 'walltime|Job_Name|queue'    # 详细状态
qstat | grep $(whoami) | head -10                       # 我的所有作业
tracejob JOBID                                          # 作业生命周期
```
