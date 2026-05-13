#!/bin/bash
#PBS -N octopus_he_pp
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=02:00:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/he_pp_out.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/he_pp_err.log

source /data/apps/intel/2018u3/env.sh

WORKDIR="/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench"
PP_CONT="/app/share/octopus"
PP_HOST="/data/home/zju321/.udocker/containers/580a2f75-3048-3052-8412-1b29c7bc2ada/ROOT/app/share/octopus"

cd "$WORKDIR"

# 尝试 HGH 格式 PP（纯文本，比 UPF 更稳定）
# HGH 路径: $PP_CONT/pseudopotentials/HGH/lda/He.hgh
printf '%s\n' \
  "CalculationMode = gs" \
  "" \
  "%Species" \
  "  \"He\" | species_pseudo | set | ${PP_CONT}/pseudopotentials/HGH/lda/He.hgh | hgh" \
  "%" \
  "" \
  "%Coordinates" \
  '  "He" | 0 | 0 | 0' \
  "%" \
  "" \
  "Radius = 5.0*angstrom" \
  "Spacing = 0.5*angstrom" \
  "XCFunctional = LDA" \
  > inp

echo "He PP (HGH) input:"
cat inp

export OMP_NUM_THREADS=1
export OCTOPUS_PAR_STATES=64
export OCTOPUS_PAR_DOMAINS=1
export OCTOPUS_PAR_KPOINTS=1

rm -f octopus.stdout
rm -rf restart

/data/home/zju321/.local/bin/udocker run \
    --workdir=/tmp \
    --volume="$WORKDIR:/tmp:ro" \
    --volume="$PP_HOST:$PP_CONT:ro" \
    --env=OMP_NUM_THREADS \
    --env=OCTOPUS_PAR_STATES \
    --env=OCTOPUS_PAR_DOMAINS \
    --env=OCTOPUS_PAR_KPOINTS \
    --env=LD_LIBRARY_PATH \
    bench_octopus \
    mpirun -np 64 octopus > octopus.stdout 2>&1
rc=$?

echo ""
echo "Exit code: $rc"
echo ""
echo "=== stdout tail ==="
tail -30 octopus.stdout
echo ""
echo "=== grep fatal/error ==="
grep -i 'error\|fatal\|Species\|zatom' octopus.stdout | head -10