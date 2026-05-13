#!/bin/bash
#PBS -N he_ae2
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=00:10:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/he_ae2_out.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/he_ae2_err.log
source /data/apps/intel/2018u3/env.sh
WORKDIR="/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench"
cd "$WORKDIR"
PP_CONT="/app/share/octopus"
PP_HOST="/data/home/zju321/.udocker/containers/580a2f75-3048-3052-8412-1b29c7bc2ada/ROOT/app/share/octopus"
# 强制 all-electron，PP 文件格式用 GTH（Hartwigsen-Goedecker-Hutter）
printf '%s\n'   'CalculationMode = gs'   'AllElectronType = full_all_electron'   ''   '%Species'   "  \"He\" | species_pseudo | set | ${PP_CONT}/pseudopotentials/HGH/lda/He.hgh | hgh"   '%'   ''   '%Coordinates'   '  "He" | 0 | 0 | 0'   '%'   ''   'Radius = 5.0*angstrom'   'Spacing = 0.5*angstrom'   'XCFunctional = LDA'   > inp
echo "input written"
cat inp
export OMP_NUM_THREADS=64
export OCTOPUS_PAR_STATES=64
export OCTOPUS_PAR_DOMAINS=1
export OCTOPUS_PAR_KPOINTS=1
rm -rf restart
/data/home/zju321/.local/bin/udocker run --workdir=/tmp --volume="$WORKDIR:/tmp:ro" --volume="$PP_HOST:$PP_CONT:ro" --env=OMP_NUM_THREADS --env=OCTOPUS_PAR_STATES --env=OCTOPUS_PAR_DOMAINS --env=OCTOPUS_PAR_KPOINTS --env=LD_LIBRARY_PATH bench_octopus mpirun -np 1 octopus 2>&1 | tee octopus_ae2.txt
echo "EXIT:$?"
