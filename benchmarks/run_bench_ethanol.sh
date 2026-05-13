#!/bin/bash
#PBS -N octopus_bench_ethanol
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=04:00:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/bench_ethanol_out.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/bench_ethanol_err.log

source /data/apps/intel/2018u3/env.sh
WORKDIR=/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench
cd "$WORKDIR"

# Ethanol C2H5OH - 26 electrons (比 CH4 10电子大不少)
printf '%s\n'   'CalculationMode = gs'   'UnitsOutput = eV_Angstrom'   ''   '%Species'   '  "C" | species_pseudo | set | standard | lmax | 1 | lloc | 0'   '  "H" | species_pseudo | set | standard | lmax | 1 | lloc | 0'   '  "O" | species_pseudo | set | standard | lmax | 1 | lloc | 0'   '%'   ''   '%Coordinates'   '  "C"  |  0.000000  |  0.000000  |  0.000000'   '  "C"  |  1.517000  |  0.000000  |  0.000000'   '  "O"  | -0.757000  |  1.312000  |  0.000000'   '  "H"  |  0.000000  | -0.500000  |  0.939000'   '  "H"  |  0.000000  | -0.500000  | -0.939000'   '  "H"  |  1.900000  |  0.707000  |  0.939000'   '  "H"  |  1.900000  |  0.707000  | -0.939000'   '  "H"  |  2.057000  | -0.500000  |  0.000000'   '%'   ''   'Radius = 10.0*angstrom'   'Spacing = 0.18*angstrom'   'XCFunctional = gga_x_pbe+gga_c_pbe'   'BoxShape = sphere'   > inp

echo 'Ethanol input written'

# 测试配置: 固定 PS=64, 测不同 NP (进程数)
# 强缩放: 体系固定, 核数增加, 理想加速比 = NP
CONFIGS=(
    "PS=64,D=1,K=1,O=1:NP=1"
    "PS=64,D=1,K=1,O=1:NP=8"
    "PS=64,D=1,K=1,O=1:NP=16"
    "PS=64,D=1,K=1,O=1:NP=32"
    "PS=64,D=1,K=1,O=1:NP=64"
)

echo 'config_name,par_states,par_domains,par_kpoints,omp_threads,mpirun_np,walltime_sec,total_energy,converged,exit_code' > benchmark_ethanol.csv

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
    echo "$config,$ps_val,$pd_val,$pk_val,$omp_val,$np_val,$walltime,${total_energy:-NA},${converged:-NA},$rc" >> benchmark_ethanol.csv
done

echo ''
echo '=== Results (by walltime) ==='
cat benchmark_ethanol.csv
echo ''
echo '=== Speedup (relative to NP=1) ==='
base=$(grep ',NP=1,' benchmark_ethanol.csv | cut -d, -f6)
for line in $(tail -n +2 benchmark_ethanol.csv); do
    np=$(echo $line | cut -d, -f6)
    wt=$(echo $line | cut -d, -f6)
    echo $line
done
