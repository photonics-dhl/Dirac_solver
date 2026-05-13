#!/bin/bash
#PBS -N octopus_bench_h2o10
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=08:00:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/bench_h2o10_out.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/bench_h2o10_err.log

source /data/apps/intel/2018u3/env.sh
WORKDIR=/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench
cd "$WORKDIR"

# (H2O)10 - 10 water molecules, 320 electrons
printf '%s\n'   'CalculationMode = gs'   'UnitsOutput = eV_Angstrom'   ''   '%Species'   '  "O" | species_pseudo | set | standard | lmax | 1 | lloc | 0'   '  "H" | species_pseudo | set | standard | lmax | 1 | lloc | 0'   '%'   ''   '%Coordinates'   '  "O"  |  0.000000  |  0.000000  |  0.000000'   '  "H"  |  0.979000  |  0.000000  | -0.243000'   '  "H"  | -0.243000  |  0.979000  |  0.000000'   '  "O"  |  4.500000  |  0.000000  |  0.000000'   '  "H"  |  4.979000  |  0.000000  | -0.243000'   '  "H"  |  4.257000  |  0.979000  |  0.000000'   '  "O"  |  0.000000  |  4.500000  |  0.000000'   '  "H"  | -0.243000  |  4.979000  |  0.000000'   '  "H"  |  0.979000  |  4.257000  |  0.000000'   '  "O"  |  0.000000  |  0.000000  |  4.500000'   '  "H"  |  0.979000  |  0.000000  |  4.257000'   '  "H"  |  0.000000  |  0.979000  |  4.257000'   '  "O"  |  4.500000  |  4.500000  |  0.000000'   '  "H"  |  4.979000  |  4.500000  | -0.243000'   '  "H"  |  4.257000  |  4.979000  |  0.000000'   '  "O"  |  4.500000  |  0.000000  |  4.500000'   '  "H"  |  4.979000  |  0.000000  |  4.257000'   '  "H"  |  4.257000  |  0.979000  |  4.500000'   '  "O"  |  0.000000  |  4.500000  |  4.500000'   '  "H"  | -0.243000  |  4.979000  |  4.500000'   '  "H"  |  0.979000  |  4.257000  |  4.500000'   '  "O"  |  4.500000  |  4.500000  |  4.500000'   '  "H"  |  4.979000  |  4.500000  |  4.257000'   '  "H"  |  4.257000  |  4.979000  |  4.500000'   '  "O"  |  9.000000  |  0.000000  |  0.000000'   '  "H"  |  9.979000  |  0.000000  | -0.243000'   '  "H"  |  9.257000  |  0.979000  |  0.000000'   '  "O"  |  9.000000  |  4.500000  |  0.000000'   '  "H"  |  9.479000  |  4.500000  | -0.243000'   '  "H"  |  9.257000  |  4.979000  |  0.000000'   '%'   ''   'Radius = 15.0*angstrom'   'Spacing = 0.18*angstrom'   'XCFunctional = gga_x_pbe+gga_c_pbe'   'BoxShape = sphere'   > inp

echo '(H2O)10 input written'

# 测强缩放: PS=64, NP=1/4/8/16/32/48/64
CONFIGS=(
    "PS=64,D=1,K=1,O=1:NP=1"
    "PS=64,D=1,K=1,O=1:NP=4"
    "PS=64,D=1,K=1,O=1:NP=8"
    "PS=64,D=1,K=1,O=1:NP=16"
    "PS=64,D=1,K=1,O=1:NP=32"
    "PS=64,D=1,K=1,O=1:NP=48"
    "PS=64,D=1,K=1,O=1:NP=64"
)

echo 'config_name,par_states,par_domains,par_kpoints,omp_threads,mpirun_np,walltime_sec,total_energy,converged,exit_code' > benchmark_h2o10.csv

for item in "${CONFIGS[@]}"; do
    config="${item%%:*}"
    np_val="${item##*:}"
    np_val="${np_val#NP=}"

    unset ps_val pd_val pk_val omp_val
    IFS=',' read -ra parts <<< "$config"
    for part in "${parts[@]}"; do
        k="${part%%=*}"
        v="${part#*=}"
        case "$k" in
            PS) ps_val="$v" ;;
            D) pd_val="$v" ;;
            K) pk_val="$v" ;;
            O) omp_val="$v" ;;
        esac
    done

    echo "--- [$config] NP=$np_val ---"

    export OMP_NUM_THREADS=$omp_val
    export OCTOPUS_PAR_STATES=$ps_val
    export OCTOPUS_PAR_DOMAINS=$pd_val
    export OCTOPUS_PAR_KPOINTS=$pk_val

    rm -f octopus.stdout
    rm -rf restart

    start_time=$(date +%s)

    /data/home/zju321/.local/bin/udocker run         --workdir=/tmp         --volume="$WORKDIR:/tmp:ro"         --env=OMP_NUM_THREADS         --env=OCTOPUS_PAR_STATES         --env=OCTOPUS_PAR_DOMAINS         --env=OCTOPUS_PAR_KPOINTS         --env=LD_LIBRARY_PATH         bench_octopus         mpirun -np $np_val octopus > octopus.stdout 2>&1
    rc=$?

    end_time=$(date +%s)
    walltime=$(($end_time - $start_time))

    total_energy=$(grep '^[ ]*etot  =' octopus.stdout | awk '{print $3}' | tail -1)
    converged=$(grep -i 'converged' octopus.stdout | tail -1 || echo 'not converged')

    echo "  Done: walltime=${walltime}s energy=${total_energy:-N/A} conv=${converged:-N} rc=$rc"
    echo "$config,$ps_val,$pd_val,$pk_val,$omp_val,$np_val,$walltime,${total_energy:-NA},${converged:-NA},$rc" >> benchmark_h2o10.csv
done

echo ''
echo '=== (H2O)10 Strong Scaling Results ==='
echo ''
echo 'NP    Walltime  Speedup  Efficiency'
base_wt=$(grep ',NP=1,' benchmark_h2o10.csv | cut -d, -f6)
for line in $(tail -n +2 benchmark_h2o10.csv); do
    np=$(echo $line | cut -d, -f6)
    wt=$(echo $line | cut -d, -f6)
    speedup=$(python3 -c "print(round($base_wt/$wt, 2))")
    efficiency=$(python3 -c "print(round($base_wt/$wt/$np*100, 1))")
    printf "%-4d  %-7ds  %-6s  %-6s%%\n" $np $wt $speedup $efficiency
done
