#!/bin/bash
#PBS -N test_ch4_pp
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=01:00:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/test_ch4_out.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/test_ch4_err.log

set -e
source /data/apps/intel/2018u3/env.sh
cd /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench

printf '%s\n'   'CalculationMode = gs'   'UnitsOutput = eV_Angstrom'   '%Coordinates'   '  "C"  |  0.000000  |  0.000000  |  0.000000'   '  "H"  |  0.629118  |  0.629118  |  0.629118'   '  "H"  | -0.629118  | -0.629118  |  0.629118'   '  "H"  | -0.629118  |  0.629118  | -0.629118'   '  "H"  |  0.629118  | -0.629118  | -0.629118'   '%'   ''   'Radius = 10.0*angstrom'   'Spacing = 0.18*angstrom'   'XCFunctional = gga_x_pbe+gga_c_pbe'   'PseudopotentialSet = upf'   'BoxShape = sphere'   'MaxSCFIterations = 500'   'SCFTolerance = 1e-6'   > inp

echo 'Input created:'
cat inp
echo ''
echo 'Running mpirun -np 1...'

/data/home/zju321/.local/bin/udocker run     --workdir=/tmp     --volume=/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench:/tmp:ro     --env=OMP_NUM_THREADS     --env=LD_LIBRARY_PATH     bench_octopus     mpirun -np 1 octopus < /tmp/inp > octopus.stdout 2>&1

echo 'Done. Output:'
tail -20 octopus.stdout
