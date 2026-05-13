#!/bin/bash
#PBS -N he_ae
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=00:10:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/he_ae_out.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/he_ae_err.log
source /data/apps/intel/2018u3/env.sh
WORKDIR="/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench"
cd "$WORKDIR"
printf '%s\n' 'CalculationMode = gs' '' '%Coordinates' '  "He" | 0 | 0 | 0' '%' '' 'Radius = 5.0*angstrom' 'Spacing = 0.5*angstrom' 'XCFunctional = LDA' > inp
echo "input written:"
cat inp
export OMP_NUM_THREADS=1
export OCTOPUS_PAR_STATES=64
export OCTOPUS_PAR_DOMAINS=1
export OCTOPUS_PAR_KPOINTS=1
rm -rf restart
/data/home/zju321/.local/bin/udocker run --workdir=/tmp --volume="$WORKDIR:/tmp:ro" --env=OMP_NUM_THREADS --env=OCTOPUS_PAR_STATES --env=OCTOPUS_PAR_DOMAINS --env=OCTOPUS_PAR_KPOINTS --env=LD_LIBRARY_PATH bench_octopus mpirun -np 64 octopus 2>&1 | tee octopus_ae.txt
echo "EXIT:$?"
