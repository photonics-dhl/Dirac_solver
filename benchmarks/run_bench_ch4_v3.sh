#!/bin/bash
#PBS -N octopus_bench_ch4_v3
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=04:00:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/bench_ch4_v3_out.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/bench_ch4_v3_err.log

source /data/apps/intel/2018u3/env.sh
WORKDIR=/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench
cd "$WORKDIR"

# CH4 PP Mode
printf '%s\n'   'CalculationMode = gs'   'UnitsOutput = eV_Angstrom'   ''   '%Species'   '  "C" | species_pseudo | set | standard | lmax | 1 | lloc | 0'   '  "H" | species_pseudo | set | standard | lmax | 1 | lloc | 0'   '%'   ''   '%Coordinates'   '  "C"  |  0.000000  |  0.000000  |  0.000000'   '  "H"  |  0.629118  |  0.629118  |  0.629118'   '  "H"  | -0.629118  | -0.629118  |  0.629118'   '  "H"  | -0.629118  |  0.629118  | -0.629118'   '  "H"  |  0.629118  | -0.629118  | -0.629118'   '%'   ''   'Radius = 10.0*angstrom'   'Spacing = 0.18*angstrom'   'XCFunctional = gga_x_pbe+gga_c_pbe'   'BoxShape = sphere'   > inp

# 配置列表 - 用更合理的 MPI 进程数 (np=64/OMP)
CONFIGS=(
    "PS=64,D=1,K=1,O=1:NP=64"
    "PS=32,D=1,K=1,O=2:NP=32"
    "PS=16,D=1,K=1,O=4:NP=16"
    "PS=8,D=1,K=1,O=8:NP=8"
    "PS=32,D=2,K=1,O=1:NP=32"
    "PS=16,D=4,K=1,O=1:NP=16"
    "PS=1,D=1,K=1,O=64:NP=1"
)

echo 'config_name,par_states,par_domains,par_kpoints,omp_threads,mpirun_np,walltime_sec,total_energy,converged,exit_code' > benchmark_ch4_v3.csv

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

    start_time=$(date +%s)

    /data/home/zju321/.local/bin/udocker run         --workdir=/tmp         --volume="$WORKDIR:/tmp:ro"         --env=OMP_NUM_THREADS         --env=OCTOPUS_PAR_STATES         --env=OCTOPUS_PAR_DOMAINS         --env=OCTOPUS_PAR_KPOINTS         --env=LD_LIBRARY_PATH         bench_octopus         mpirun -np $np_val octopus > octopus.stdout 2>&1

    end_time=$(date +%s)
    walltime=$(($end_time - $start_time))

    total_energy=$(grep 'Total energy' octopus.stdout | grep -v Eigenvalues | awk '{print $3}' | tail -1)
    converged=$(grep -i 'converged' octopus.stdout | tail -1 || echo 'not converged')
    exit_code=$(grep 'EXIT_CODE' octopus.stdout | tail -1 | cut -d= -f2)
    [ -z "$exit_code" ] && exit_code='?'

    echo "  Done: walltime=${walltime}s energy=${total_energy:-N/A} conv=${converged:-N}"
    echo "$config,$ps_val,$pd_val,$pk_val,$omp_val,$np_val,$walltime,${total_energy:-NA},${converged:-NA},$exit_code" >> benchmark_ch4_v3.csv
done

echo ''
echo '=== Results ==='
tail -n +2 benchmark_ch4_v3.csv | sort -t, -k6 -n
