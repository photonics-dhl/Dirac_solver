#!/bin/bash
#PBS -N test_ch4_n1
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=01:00:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/test_ch4_n1_out.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/test_ch4_n1_err.log

source /data/apps/intel/2018u3/env.sh
WORKDIR=/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench
cd "$WORKDIR"

# CH4 PP Mode - species_pseudo 格式
printf '%s\n'   'CalculationMode = gs'   'UnitsOutput = eV_Angstrom'   ''   '%Species'   '  "C" | species_pseudo | set | standard | lmax | 1 | lloc | 0'   '  "H" | species_pseudo | set | standard | lmax | 1 | lloc | 0'   '%'   ''   '%Coordinates'   '  "C"  |  0.000000  |  0.000000  |  0.000000'   '  "H"  |  0.629118  |  0.629118  |  0.629118'   '  "H"  | -0.629118  | -0.629118  |  0.629118'   '  "H"  | -0.629118  |  0.629118  | -0.629118'   '  "H"  |  0.629118  | -0.629118  | -0.629118'   '%'   ''   'Radius = 10.0*angstrom'   'Spacing = 0.18*angstrom'   'XCFunctional = gga_x_pbe+gga_c_pbe'   'BoxShape = sphere'   'MaxSCFIterations = 500'   'SCFTolerance = 1e-6'   > inp

echo 'Input:'
cat inp
echo ''

export OMP_NUM_THREADS=1
export OCTOPUS_PAR_STATES=1
export OCTOPUS_PAR_DOMAINS=1
export OCTOPUS_PAR_KPOINTS=1

echo 'Running mpirun -np 1...'

/data/home/zju321/.local/bin/udocker run     --workdir=/tmp     --volume="$WORKDIR:/tmp:ro"     --env=OMP_NUM_THREADS     --env=OCTOPUS_PAR_STATES     --env=OCTOPUS_PAR_DOMAINS     --env=OCTOPUS_PAR_KPOINTS     --env=LD_LIBRARY_PATH     bench_octopus     mpirun -np 1 octopus > octopus.stdout 2>&1

echo 'Exit code: '$?
echo 'Output:'
tail -30 octopus.stdout
