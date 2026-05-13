#!/bin/bash
#PBS -N n_test
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=00:10:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/n_test_out.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/n_test_err.log
source /data/apps/intel/2018u3/env.sh
WORKDIR="/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench"
cd "$WORKDIR"
export OMP_NUM_THREADS=1
export OCTOPUS_PAR_STATES=64
export OCTOPUS_PAR_DOMAINS=1
export OCTOPUS_PAR_KPOINTS=1
rm -rf restart inp
printf '%s\n' 'CalculationMode = gs' 'UnitsOutput = eV_Angstrom' '' '%Species' '  "N" | species_pseudo | set | /app/share/octopus/pseudopotentials/quantum-simulation.org/sg15/N_ONCV_PBE-1.2.upf' '%' '' '%Coordinates' '  "N" | 0 | 0 | 0' '%' '' 'Radius = 10.0*angstrom' 'Spacing = 0.18*angstrom' 'XCFunctional = gga_x_pbe+gga_c_pbe' 'BoxShape = sphere' > inp
/data/home/zju321/.local/bin/udocker run --workdir=/tmp --volume="$WORKDIR:/tmp:ro" --env=OMP_NUM_THREADS --env=OCTOPUS_PAR_STATES --env=OCTOPUS_PAR_DOMAINS --env=OCTOPUS_PAR_KPOINTS --env=LD_LIBRARY_PATH bench_octopus mpirun -np 64 octopus 2>&1 | tee octopus_n.txt
echo "EXIT:$?"
