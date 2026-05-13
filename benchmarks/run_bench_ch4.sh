#!/bin/bash
#==============================================================================
# Octopus 并行化基准测试 v2 - CH4 分子
# 使用 CH4 分子 (10电子) + PP Mode 测试 ParStates + ParDomains 组合
#
# 关键设计决策:
#   - CH4 比 H/N 更大，能更好地展示并行化效果
#   - spacing=0.18Å (收敛参数), Radius=10Å
#   - PP Mode: C/H 用 pseudo-dojo.org nc-fr-04_pbe_standard UPF
#   - 使用 printf 生成 inp，再用 volume mount :ro 到容器 /tmp
#
# 用法:
#   qsub run_bench_ch4.sh
#==============================================================================
#PBS -N octopus_bench_ch4_v2
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=04:00:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/bench_ch4_output.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/bench_ch4_error.log

set -e
source /data/apps/intel/2018u3/env.sh

WORKDIR="/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

# UPF 文件路径 (从第一个容器实例获取)
UPF_BASE="/data/home/zju321/.udocker/containers/580a2f75-3048-3052-8412-1b29c7bc2ada/ROOT/app/share/octopus/pseudopotentials/pseudo-dojo.org/nc-fr-04_pbe_standard"

# CH4 PP Mode 输入 (spacing=0.18Å, 已验证收敛)
# 使用 printf 写入 inp 文件（heredoc 会导致变量展开问题）
printf '%s\n' \
  "CalculationMode = gs" \
  "UnitsOutput = eV_Angstrom" \
  "" \
  "%Species" \
  "  'C' | spec | '${UPF_BASE}/C.upf' | pot | from_pspfile" \
  "  'H' | spec | '${UPF_BASE}/H.upf' | pot | from_pspfile" \
  "%" \
  "" \
  "%Coordinates" \
  "  'C'  |  0.000000  |  0.000000  |  0.000000" \
  "  'H'  |  0.629118  |  0.629118  |  0.629118" \
  "  'H'  | -0.629118  | -0.629118  |  0.629118" \
  "  'H'  | -0.629118  |  0.629118  | -0.629118" \
  "  'H'  |  0.629118  | -0.629118  | -0.629118" \
  "%" \
  "" \
  "Radius = 10.0*angstrom" \
  "Spacing = 0.18*angstrom" \
  "XCFunctional = gga_x_pbe+gga_c_pbe" \
  "BoxShape = sphere" \
  "MaxSCFIterations = 500" \
  "SCFTolerance = 1e-6" \
  > inp

# 配置列表: (名称, ParStates, ParDomains, ParKPoints, OMP线程)
CONFIGS=(
    "PS=64,D=1,K=1,O=1"      # 纯态并行, 64 MPI procs
    "PS=32,D=1,K=1,O=2"      # 混合: 32 MPI + 2 OMP
    "PS=16,D=1,K=1,O=4"      # 混合: 16 MPI + 4 OMP
    "PS=8,D=1,K=1,O=8"       # 混合: 8 MPI + 8 OMP
    "PS=32,D=2,K=1,O=1"      # 域分解: 32 states + 2 domains
    "PS=16,D=4,K=1,O=1"      # 域分解: 16 states + 4 domains
    "PS=1,D=1,K=1,O=64"      # 纯 OMP: 1 MPI + 64 OMP
)

echo "=============================================="
echo "Octopus 并行化基准测试 v2"
echo "节点: 64 核 | 测试用例: CH4 分子 (10电子)"
echo "开始时间: $(date)"
echo "=============================================="

# 写入 CSV 头部
echo "config_name,par_states,par_domains,par_kpoints,omp_threads,mpirun_np,walltime_sec,total_energy,converged,exit_code" > benchmark_ch4.csv

# 确认 inp 文件内容
echo "Input file 内容:"
cat inp
echo ""

for i in "${!CONFIGS[@]}"; do
    config="${CONFIGS[$i]}"

    # 解析参数值
    unset ps_val pd_val pk_val omp_val
    IFS=',' read -ra parts <<< "$config"
    for part in "${parts[@]}"; do
        key="${part%%=*}"
        val="${part#*=}"
        case "$key" in
            PS) ps_val="$val" ;;
            D) pd_val="$val" ;;
            K) pk_val="$val" ;;
            O) omp_val="$val" ;;
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
    # 方式: volume mount :ro 把 host 的 WORKDIR 映射到容器内 /tmp
    # 容器内读取 /tmp/inp (即 host 上的 WORKDIR/inp)
    /data/home/zju321/.local/bin/udocker run \
        --workdir=/tmp \
        --volume="$WORKDIR:/tmp:ro" \
        --env=OMP_NUM_THREADS \
        --env=OCTOPUS_PAR_STATES \
        --env=OCTOPUS_PAR_DOMAINS \
        --env=OCTOPUS_PAR_KPOINTS \
        --env=LD_LIBRARY_PATH \
        bench_octopus \
        mpirun -np $np_val octopus < /tmp/inp > octopus.stdout 2>&1

    # 记录结束时间
    end_time=$(date +%s)
    walltime=$((end_time - start_time))

    # 解析结果
    total_energy=$(grep "Total energy" octopus.stdout | grep -v Eigenvalues | awk '{print $3}' | tail -1)
    converged=$(grep -i "converged" octopus.stdout | tail -1 || echo "not converged")
    exit_code=$(grep "EXIT_CODE" octopus.stdout | tail -1 | cut -d= -f2)
    [ -z "$exit_code" ] && exit_code="?"

    echo "  完成: walltime=${walltime}s, energy=${total_energy:-N/A}"
    echo "  收敛: ${converged:-N/A}"

    # 写入 CSV
    echo "$config,$ps_val,$pd_val,$pk_val,$omp_val,$np_val,$walltime,${total_energy:-NA},${converged:-NA},$exit_code" >> benchmark_ch4.csv
done

echo ""
echo "=============================================="
echo "基准测试完成: $(date)"
echo "=============================================="
echo ""
echo "=== 结果汇总 (按 walltime 排序) ==="
echo ""
awk -F',' 'NR==1{next} {print $1": "$6"s  energy="$7"  "$8}' benchmark_ch4.csv | sort -t: -k2 -n
echo ""
echo "=== 最优配置 ==="
best=$(tail -n +2 benchmark_ch4.csv | sort -t, -k6 -n | head -1)
echo "  $best"
echo ""
echo "详细结果: $WORKDIR/benchmark_ch4.csv"