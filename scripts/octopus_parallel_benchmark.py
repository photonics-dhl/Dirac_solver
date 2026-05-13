#!/usr/bin/env python3
"""
Octopus 并行化基准测试脚本
测试不同 ParStates/ParDomains/ParKPoints 配置在 64 核节点上的性能

用法:
    python octopus_parallel_benchmark.py

输出:
    benchmark_results_TIMESTAMP.csv
"""

import os
import subprocess
import time
import csv
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

# ============ 配置 ============
HPC_HOST = "10.72.212.33"
SSH_CMD = f"ssh dirac-key ssh {HPC_HOST}"

# Octopus 测试用例: H 原子基态 (简单快速)
OCTOPUS_INPUT = """
CalculationMode = gs

UnitsOutput = eV

%Species
  'H' | species | "H.BLYP-D3" | pot | from_pspfile
%

Coordinates = [0, 0, 0]*angstrom

Radius = 10.0*angstrom
Spacing = 0.18*angstrom

XCFunctional = LDA

Output = [density, potential, eigenvalues]
""".strip()

# 并行配置列表 (64 核节点)
PARALLEL_CONFIGS = [
    # (name, par_states, par_domains, par_kpoints, omp_threads)
    ("纯态并行-ParStates=64",         64, 1,  1, 1),
    ("纯态并行-ParStates=32,OMP=2",   32, 1,  1, 2),
    ("纯态并行-ParStates=16,OMP=4",  16, 1,  1, 4),
    ("混合并行-ParStates=32,Dom=2,OMP=2",  32, 2, 1, 2),
    ("混合并行-ParStates=16,Dom=4,OMP=1",  16, 4, 1, 1),
    ("k点并行-ParKPoints=32,PS=2",   2,  1, 32, 1),
    ("k点并行-ParKPoints=16,PS=4",   4,  1, 16, 1),
]

PBS_TEMPLATE = """#!/bin/bash
#PBS -N octopus_bench_{config_name}
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=02:00:00
#PBS -o {workdir}/bench_{idx}_out.log
#PBS -e {workdir}/bench_{idx}_err.log

cd {workdir}

source /data/apps/intel/2018u3/env.sh

export OMP_NUM_THREADS={omp_threads}
export OCTOPUS_PAR_STATES={par_states}
export OCTOPUS_PAR_DOMAINS={par_domains}
export OCTOPUS_PAR_KPOINTS={par_kpoints}

# 通过 udocker 运行 Octopus
HOME=/data/home/zju321 /data/home/zju321/.local/bin/udocker run \
    --workdir=/data/home/zju321 \
    --env=HOME \
    --env=OMP_NUM_THREADS \
    --env=OCTOPUS_PAR_STATES \
    --env=OCTOPUS_PAR_DOMAINS \
    --env=OCTOPUS_PAR_KPOINTS \
    --env=LD_LIBRARY_PATH \
    dirac_octopus_udocker \
    mpirun -np {total_procs} octopus < inp.txt > octopus.stdout 2>&1

echo "EXIT_CODE=$?" >> octopus.stdout
"""


def ssh_run(cmd: str, timeout: int = 120) -> tuple[str, str, int]:
    """在 HPC 上执行命令"""
    full_cmd = f"{SSH_CMD} '{cmd}'"
    result = subprocess.run(
        full_cmd, shell=True, capture_output=True, text=True, timeout=timeout
    )
    return result.stdout, result.stderr, result.returncode


def setup_test_dir(workdir: str, config_name: str, idx: int) -> str:
    """准备测试目录和输入文件"""
    ssh_run(f"mkdir -p {workdir}/bench_{idx}")
    ssh_run(f"cat > {workdir}/bench_{idx}/inp.txt << 'EOF'\n{OCTOPUS_INPUT}\nEOF")
    return f"{workdir}/bench_{idx}"


def submit_and_wait(job_script: str, workdir: str) -> tuple[str, float, str]:
    """提交 PBS 作业并等待完成，返回 (job_id, walltime_seconds, stderr)"""
    # 写入作业脚本
    ssh_run(f"cat > {workdir}/run_bench.job << 'JOBSCRIPT'\n{job_script}\nJOBSCRIPT")

    # 提交作业
    stdout, stderr, rc = ssh_run(f"cd {workdir} && qsub run_bench.job")
    if rc != 0:
        return f"QSUB_FAILED: {stderr}", -1, stderr

    job_id = stdout.strip().split()[0]
    print(f"  提交作业: {job_id}")

    # 等待作业完成 (最多 poll 120 次 × 30秒 = 60分钟)
    for poll in range(120):
        time.sleep(30)
        stdout, stderr, rc = ssh_run(f"qstat {job_id}")
        if rc != 0 or "Unknown Job" in stdout or "Job has finished" in stdout:
            break
        if poll % 5 == 0:
            print(f"  等待中... ({poll*30}s)")

    # 获取作业信息
    stdout, stderr, rc = ssh_run(f"qstat -f {job_id}")
    walltime_line = [l for l in stdout.split("\n") if "walltime" in l.lower() or "resources_used.walltime" in l.lower()]
    walltime_str = walltime_line[0].split("=")[-1].strip() if walltime_line else "00:00:00"

    # 解析 walltime
    parts = walltime_str.split(":")
    if len(parts) == 3:
        walltime_sec = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
    elif len(parts) == 2:
        walltime_sec = int(parts[0])*60 + int(parts[1])
    else:
        walltime_sec = -1

    # 读取 stderr
    _, stderr_out, _ = ssh_run(f"cat {workdir}/bench_*/octopus.stderr 2>/dev/null | tail -20")

    return job_id, walltime_sec, stderr_out


def parse_octopus_output(workdir: str, idx: int) -> dict:
    """解析 Octopus 输出"""
    stdout, _, _ = ssh_run(f"cat {workdir}/bench_{idx}/octopus.stdout 2>/dev/null")

    result = {
        "total_energy": None,
        "converged": False,
        "parallel_info": {},
        "exit_code": None,
    }

    for line in stdout.split("\n"):
        if "Total energy" in line and "Eigenvalues" not in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "energy" and i+1 < len(parts):
                    try:
                        result["total_energy"] = float(parts[i+1])
                    except:
                        pass
        if "Converged" in line:
            result["converged"] = "yes" in line.lower() or "true" in line.lower()
        if "Parallelization" in line and ":" in line:
            # 例如: "ParStates = 32"
            for key in ["ParStates", "ParDomains", "ParKPoints"]:
                if key in line:
                    try:
                        val = line.split("=")[-1].strip()
                        result["parallel_info"][key] = int(val)
                    except:
                        pass
        if "EXIT_CODE" in line:
            try:
                result["exit_code"] = int(line.split("=")[-1])
            except:
                pass

    return result


def run_benchmark():
    """运行完整基准测试"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"benchmark_results_{timestamp}.csv"

    # 创建临时测试目录
    base_workdir = f"/data/home/zju321/octopus_bench_{timestamp}"
    ssh_run(f"mkdir -p {base_workdir}")

    print(f"Octopus 并行化基准测试")
    print(f"节点: 64 核 | 测试用例: H 原子基态 | 时间: {timestamp}")
    print("=" * 60)

    results = []

    for idx, (name, ps, pd, pk, omp) in enumerate(PARALLEL_CONFIGS):
        total_procs = 64 // omp  # mpirun 进程数 = 总核数 / OMP线程数
        workdir = f"{base_workdir}/c{idx}"

        print(f"\n[{idx+1}/{len(PARALLEL_CONFIGS)}] {name}")
        print(f"  ParStates={ps}, ParDomains={pd}, ParKPoints={pk}, OMP={omp}")
        print(f"  mpirun -np {total_procs}, 每进程 {omp} 线程")

        # 准备测试目录
        setup_test_dir(base_workdir, name.replace(" ", "_"), idx)

        # 构建 PBS 脚本
        job_script = PBS_TEMPLATE.format(
            config_name=name.replace(" ", "_").replace("=", ""),
            workdir=workdir,
            idx=idx,
            par_states=ps,
            par_domains=pd,
            par_kpoints=pk,
            omp_threads=omp,
            total_procs=total_procs,
        )

        # 提交并等待
        job_id, walltime, stderr = submit_and_wait(job_script, workdir)

        # 解析输出
        output = parse_octopus_output(base_workdir, idx)

        print(f"  完成: job_id={job_id}, walltime={walltime}s")
        print(f"  能量: {output.get('total_energy', 'N/A')}, 收敛: {output.get('converged', 'N/A')}")
        print(f"  并行信息: {output.get('parallel_info', {})}")

        results.append({
            "config_name": name,
            "par_states": ps,
            "par_domains": pd,
            "par_kpoints": pk,
            "omp_threads": omp,
            "mpirun_np": total_procs,
            "job_id": job_id,
            "walltime_sec": walltime,
            "total_energy": output.get("total_energy"),
            "converged": output.get("converged"),
            "exit_code": output.get("exit_code"),
            "parallel_info": output.get("parallel_info", {}),
        })

    # 写结果
    with open(results_file, "w", newline="", encoding="utf-8") as f:
        if results:
            fieldnames = list(results[0].keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

    print(f"\n结果已保存: {results_file}")
    print("\n最优配置:")
    valid_results = [r for r in results if r["walltime_sec"] > 0]
    if valid_results:
        best = min(valid_results, key=lambda x: x["walltime_sec"])
        print(f"  {best['config_name']}: {best['walltime_sec']}s")
        print(f"  参数: ParStates={best['par_states']}, ParDomains={best['par_domains']}, ParKPoints={best['par_kpoints']}, OMP={best['omp_threads']}")

    # 清理
    print("\n清理测试目录...")
    ssh_run(f"rm -rf {base_workdir}")

    return results


if __name__ == "__main__":
    run_benchmark()
