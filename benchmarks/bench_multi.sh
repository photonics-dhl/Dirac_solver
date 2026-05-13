#!/bin/bash
#==============================================================================
# Octopus 多体系并行化基准测试
# 测试 4 种体系 × 7 种并行配置，共 28 组测试
#
# 测试体系:
#   1. H 原子 (1电子)      - 单电子参考
#   2. N 原子 (7电子)      - 稍复杂原子
#   3. H₂O 分子 (8电子)    - 多原子分子
#   4. CH₄ 分子 (10电子)   - 更大分子
#
# 存放位置: Dirac 项目 run/bench/ 目录
#==============================================================================
#PBS -N octopus_bench_multi
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=08:00:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/bench_multi_output.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/bench_multi_error.log

set -e
source /data/apps/intel/2018u3/env.sh

WORKDIR="/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

# 配置列表 (简化版：单 MPI + 不同 OMP 线程数)
CONFIGS=(
    "PS=1,D=1,K=1,O=1"       # 纯 OMP, 1 thread
    "PS=1,D=1,K=1,O=2"       # 纯 OMP, 2 threads
    "PS=1,D=1,K=1,O=4"       # 纯 OMP, 4 threads
    "PS=1,D=1,K=1,O=8"       # 纯 OMP, 8 threads
    "PS=1,D=1,K=1,O=16"      # 纯 OMP, 16 threads
    "PS=1,D=1,K=1,O=32"      # 纯 OMP, 32 threads
    "PS=1,D=1,K=1,O=64"      # 纯 OMP, 64 threads
)

# 测试体系定义
# 每个体系: 名称, 电子数, inp内容
create_inp() {
    local case_name="$1"
    case "$case_name" in
        H_atom)
            cat > inp << 'EOF'
CalculationMode = gs

%Coordinates
  "H" | 0 | 0 | 0
%

Radius = 8.0*angstrom
Spacing = 0.3*angstrom
XCFunctional = LDA
MaxSCFIterations = 500
EOF
            ;;
        N_atom)
            cat > inp << 'EOF'
CalculationMode = gs

%Coordinates
  "N" | 0 | 0 | 0
%

Radius = 8.0*angstrom
Spacing = 0.3*angstrom
XCFunctional = LDA
MaxSCFIterations = 500
EOF
            ;;
        H2O_molecule)
            cat > inp << 'EOF'
CalculationMode = gs

%Coordinates
  "O"  |  0.000000  |  0.000000  |  0.117300
  "H"  |  0.757000  |  0.000000  | -0.469200
  "H"  | -0.757000  |  0.000000  | -0.469200
%

Radius = 8.0*angstrom
Spacing = 0.3*angstrom
XCFunctional = LDA
MaxSCFIterations = 500
EOF
            ;;
        CH4_molecule)
            cat > inp << 'EOF'
CalculationMode = gs

%Coordinates
  "C"  |  0.000000  |  0.000000  |  0.000000
  "H"  |  0.629118  |  0.629118  |  0.629118
  "H"  | -0.629118  | -0.629118  |  0.629118
  "H"  | -0.629118  |  0.629118  | -0.629118
  "H"  |  0.629118  | -0.629118  | -0.629118
%

Radius = 8.0*angstrom
Spacing = 0.3*angstrom
XCFunctional = LDA
MaxSCFIterations = 500
EOF
            ;;
    esac
}

echo "=============================================="
echo "Octopus 多体系并行化基准测试"
echo "节点: 64 核 | 体系: H, N, H2O, CH4"
echo "开始时间: $(date)"
echo "=============================================="

# CSV 头
echo "case_name,config,par_states,par_domains,par_kpoints,omp_threads,mpirun_np,walltime_sec,total_energy,converged,exit_code" > benchmark_multi.csv

# 测试体系列表
CASES=("H_atom" "N_atom" "H2O_molecule" "CH4_molecule")

for case_name in "${CASES[@]}"; do
    echo ""
    echo "=============================================="
    echo "测试体系: $case_name"
    echo "=============================================="

    # 创建该体系的输入文件
    create_inp "$case_name"
    echo "Input file:"
    cat inp
    echo ""

    for i in "${!CONFIGS[@]}"; do
        config="${CONFIGS[$i]}"

        # 解析参数
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

        echo "--- [$case_name] [$((i+1))/7] $config ---"
        echo "  ParStates=$ps_val, ParDomains=$pd_val, ParKPoints=$pk_val, OMP=$omp_val"
        echo "  mpirun -np $np_val"

        # 设置环境
        export OMP_NUM_THREADS=$omp_val
        export OCTOPUS_PAR_STATES=$ps_val
        export OCTOPUS_PAR_DOMAINS=$pd_val
        export OCTOPUS_PAR_KPOINTS=$pk_val

        # 清理
        rm -f octopus.stdout

        # 记录时间
        start_time=$(date +%s)

        # 运行
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

        end_time=$(date +%s)
        walltime=$((end_time - start_time))

        # 解析结果
        total_energy=$(grep "etot  =" octopus.stdout | tail -1 | awk '{print $3}')
        converged=$(grep -i "converged" octopus.stdout | tail -1 || echo "not converged")
        exit_code=$?

        echo "  完成: walltime=${walltime}s, energy=${total_energy:-N/A}"

        # 写入 CSV
        echo "$case_name,$config,$ps_val,$pd_val,$pk_val,$omp_val,$np_val,$walltime,${total_energy:-NA},${converged:-NA},$exit_code" >> benchmark_multi.csv
    done
done

echo ""
echo "=============================================="
echo "基准测试完成: $(date)"
echo "=============================================="

echo ""
echo "=== 结果汇总 (按体系和walltime排序) ==="
echo ""
awk -F',' 'NR==1{next} {print $1": "$2": "$6"s ("$8")"}' benchmark_multi.csv | sort -t: -k3 -n

echo ""
echo "=== 最优配置 (各体系) ==="
for case_name in "${CASES[@]}"; do
    echo ""
    echo "$case_name:"
    best=$(grep "^$case_name," benchmark_multi.csv | sort -t, -k6 -n | head -1)
    echo "  $best"
done

echo ""
echo "详细结果: $WORKDIR/benchmark_multi.csv"
