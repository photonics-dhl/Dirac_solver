#!/bin/bash
#PBS -N octopus_single_test
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=01:00:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/single_output.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/single_error.log

set -e
source /data/apps/intel/2018u3/env.sh

WORKDIR="/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench"
cd "$WORKDIR"

echo "=== 开始测试: $(date) ==="

# 清理旧文件
rm -f inp octopus.stdout octopus.stderr

# 创建输入文件
cat > inp << 'EOF'
CalculationMode = gs

%Coordinates
  "H" | 0 | 0 | 0
%

Radius = 10.0*angstrom
Spacing = 0.18*angstrom
XCFunctional = LDA

%Output
  density
%

OutputFormat = oct_binary
EOF

echo "Input file:"
cat inp
echo ""

# 设置环境
export OMP_NUM_THREADS=1
export OCTOPUS_PAR_STATES=64
export OCTOPUS_PAR_DOMAINS=1
export OCTOPUS_PAR_KPOINTS=1

# 运行 (单进程测试)
echo "=== 运行 Octopus (mpirun -np 1) ==="
/data/home/zju321/.local/bin/udocker run \
    --workdir=/tmp \
    --volume="$WORKDIR:/tmp:ro" \
    --env=OMP_NUM_THREADS \
    --env=OCTOPUS_PAR_STATES \
    --env=OCTOPUS_PAR_DOMAINS \
    --env=OCTOPUS_PAR_KPOINTS \
    --env=LD_LIBRARY_PATH \
    bench_octopus \
    mpirun -np 1 octopus > octopus.stdout 2>&1

echo "=== 完成: $(date) ==="
echo "Exit code: $?"
