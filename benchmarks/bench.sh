#!/bin/bash
#==============================================================================
# Octopus 并行化基准测试 - 单作业版本
# 在单个 PBS 作业内顺序测试 7 种并行配置
#
# 存放位置: Dirac 项目 run/bench/ 目录
#==============================================================================
#PBS -N octopus_bench
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=04:00:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/bench_output.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/bench_error.log

set -e
source /data/apps/intel/2018u3/env.sh

# 使用项目目录，而非 HOME 散落文件
WORKDIR="/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

# H 原子基态测试输入 (快速参数，不输出避免 OutputFormat 问题)
printf '%s\n' \
  "CalculationMode = gs" \
  "" \
  "%Coordinates" \
  '  "H" | 0 | 0 | 0' \
  "%" \
  "" \
  "Radius = 5.0*angstrom" \
  "Spacing = 0.5*angstrom" \
  "XCFunctional = LDA" \
  > inp

# 配置列表: (名称, ParStates, ParDomains, ParKPoints, OMP线程)
CONFIGS=(
    "ParStates=64,Dom=1,KP=1,OMP=1"
    "ParStates=32,Dom=1,KP=1,OMP=2"
    "ParStates=16,Dom=1,KP=1,OMP=4"
    "ParStates=32,Dom=2,KP=1,OMP=2"
    "ParStates=16,Dom=4,KP=1,OMP=1"
    "ParStates=2,Dom=1,KP=32,OMP=1"
    "ParStates=4,Dom=1,KP=16,OMP=1"
)

echo "=============================================="
echo "Octopus 并行化基准测试"
echo "节点: 64 核 | 测试用例: H 原子基态"
echo "开始时间: $(date)"
echo "=============================================="

# 写入 CSV 头部
echo "config_name,par_states,par_domains,par_kpoints,omp_threads,mpirun_np,walltime_sec,total_energy,converged,exit_code" > benchmark_results.csv

for i in "${!CONFIGS[@]}"; do
    config="${CONFIGS[$i]}"

    # 解析参数值
    unset ps_val pd_val pk_val omp_val
    IFS=',' read -ra parts <<< "$config"
    for part in "${parts[@]}"; do
        key="${part%%=*}"
        val="${part#*=}"
        case "$key" in
            ParStates) ps_val="$val" ;;
            Dom) pd_val="$val" ;;
            KP) pk_val="$val" ;;
            OMP) omp_val="$val" ;;
        esac
    done
    np_val=$((64 / omp_val))

    echo ""
    echo "--- [$((i+1))/7] $config ---"
    echo "  ParStates=$ps_val, ParDomains=$pd_val, ParKPoints=$pk_val, OMP=$omp_val"
    echo "  mpirun -np $np_val"

    # 设置环境变量
    export OMP_NUM_THREADS=$omp_val
    export OCTOPUS_PAR_STATES=$ps_val
    export OCTOPUS_PAR_DOMAINS=$pd_val
    export OCTOPUS_PAR_KPOINTS=$pk_val

    # 清理旧输出
    rm -f octopus.stdout octopus.stderr

    # 记录开始时间
    start_time=$(date +%s)

    # 运行 Octopus
    # 使用容器名 bench_octopus (已创建好 F3 execmode)，--workdir=/tmp 有效
    # Volume 挂载 WORKDIR 到 /tmp (read-only)，使 inp 可被访问
    /data/home/zju321/.local/bin/udocker run \
        --workdir=/tmp \
        --volume="$WORKDIR:/tmp:ro" \
        --env=OMP_NUM_THREADS \
        --env=OCTOPUS_PAR_STATES \
        --env=OCTOPUS_PAR_DOMAINS \
        --env=OCTOPUS_PAR_KPOINTS \
        --env=LD_LIBRARY_PATH \
        bench_octopus \
        mpirun -np $np_val octopus > octopus.stdout 2>&1

    # 记录结束时间
    end_time=$(date +%s)
    walltime=$((end_time - start_time))

    # 解析结果 - 提取最后的 etot 值
    # Octopus 输出格式: etot  = -1.78598053E-01
    total_energy=$(grep "etot  =" octopus.stdout | tail -1 | awk '{print $3}')
    converged=$(grep -i "converged" octopus.stdout | tail -1 || echo "not converged")
    exit_code=$?

    echo "  完成: walltime=${walltime}s, energy=${total_energy:-N/A}, converged=${converged:-N/A}"

    # 写入 CSV
    echo "$config,$ps_val,$pd_val,$pk_val,$omp_val,$np_val,$walltime,${total_energy:-NA},${converged:-NA},$exit_code" >> benchmark_results.csv
done

echo ""
echo "=============================================="
echo "基准测试完成: $(date)"
echo "=============================================="
echo ""
echo "结果汇总 (按 walltime 排序):"
echo ""
awk -F',' 'NR==1{next} {print $1": "$6"s"}' benchmark_results.csv | sort -t: -k2 -n
echo ""
echo "最优配置:"
best=$(tail -n +2 benchmark_results.csv | sort -t, -k6 -n | head -1)
echo "  $best"
echo ""
echo "详细结果: $WORKDIR/benchmark_results.csv"
