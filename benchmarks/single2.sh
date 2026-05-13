#!/bin/bash
#PBS -N octopus_single
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=02:00:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/single_output.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/single_error.log

source /data/apps/intel/2018u3/env.sh

WORKDIR="/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench"
cd "$WORKDIR"

# 使用最快参数
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
  "" \
  "%Output" \
  "  density" \
  "%" \
  > inp

echo "Input:"
cat inp

# 运行 (纯态并行 64)
export OMP_NUM_THREADS=1
export OCTOPUS_PAR_STATES=64
export OCTOPUS_PAR_DOMAINS=1
export OCTOPUS_PAR_KPOINTS=1

echo ""
echo "=== Running Octopus (mpirun -np 64) at $(date) ==="

/data/home/zju321/.local/bin/udocker run \
    --workdir=/tmp \
    --volume="$WORKDIR:/tmp:ro" \
    --env=OMP_NUM_THREADS \
    --env=OCTOPUS_PAR_STATES \
    --env=OCTOPUS_PAR_DOMAINS \
    --env=OCTOPUS_PAR_KPOINTS \
    --env=LD_LIBRARY_PATH \
    bench_octopus \
    mpirun -np 64 octopus > octopus.stdout 2>&1
echo "=== Done at $(date), exit code: $? ==="
