#!/bin/bash
#PBS -N octopus_bench_ch4_v2
#PBS -q workq
#PBS -l nodes=1:ppn=64
#PBS -l walltime=04:00:00
#PBS -o /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/bench_ch4_v2_out.log
#PBS -e /data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench/bench_ch4_v2_err.log

set -e
source /data/apps/intel/2018u3/env.sh
WORKDIR=/data/home/zju321/.openclaw/workspace/projects/Dirac/run/bench
cd "$WORKDIR"

# CH4 PP Mode - species_pseudo 格式
printf '%s\n' \
  'CalculationMode = gs' \
  'UnitsOutput = eV_Angstrom' \
  '' \
  '%Species' \
  '  "C" | species_pseudo | set | standard | lmax | 1 | lloc | 0' \
  '  "H" | species_pseudo | set | standard | lmax | 1 | lloc | 0' \
  '%' \
  '' \
  '%Coordinates' \
  '  "C"  |  0.000000  |  0.000000  |  0.000000' \
  '  "H"  |  0.629118  |  0.629118  |  0.629118' \
  '  "H"  | -0.629118  | -0.629118  |  0.629118' \
  '  "H"  | -0.629118  |  0.629118  | -0.629118' \
  '  "H"  |  0.629118  | -0.629118  | -0.629118' \
  '%' \
  '' \
  'Radius = 10.0*angstrom' \
  'Spacing = 0.18*angstrom' \
  'XCFunctional = gga_x_pbe+gga_c_pbe' \
  'BoxShape = sphere' \
  'MaxSCFIterations = 500' \
  'SCFTolerance = 1e-6' \
  > inp

echo 'Input written'

# 配置列表: PS=ParStates, D=ParDomains, K=ParKPoints, O=OMP_threads
CONFIGS=(
    "PS=64,D=1,K=1,O=1"
    "PS=32,D=1,K=1,O=2"
    "PS=16,D=1,K=1,O=4"
    "PS=8,D=1,K=1,O=8"
    "PS=32,D=2,K=1,O=1"
    "PS=16,D=4,K=1,O=1"
    "PS=1,D=1,K=1,O=64"
)

echo 'config_name,par_states,par_domains,par_kpoints,omp_threads,mpirun_np,walltime_sec,total_energy,converged,exit_code' > benchmark_ch4_v2.csv

for config in "${CONFIGS[@]}"; do
    unset ps_val pd_val pk_val omp_val
    IFS=',' read -ra parts <<< "$config"
    for part in "${parts[@]}"; do
        key="${part%%=*}"
        val="${part#*=}"
        case "$key" in
            PS) ps_val="$val" ;;
            D) pd_val="$val" ;;
            K) pk_val="$val" ;;
            O) omp_val="$val" ;;
        esac
    done
    mpirun_np=$((64 / omp_val))

    echo "--- [$config] ---"
    echo "  PS=$ps_val D=$pd_val K=$pk_val OMP=$omp_val mpirun -np $mpirun_np"

    export OMP_NUM_THREADS=$omp_val
    export OCTOPUS_PAR_STATES=$ps_val
    export OCTOPUS_PAR_DOMAINS=$pd_val
    export OCTOPUS_PAR_KPOINTS=$pk_val

    rm -f octopus.stdout

    start_time=$(date +%s)

    # 无 stdin 重定向！靠 --workdir=/tmp + volume mount 让 Octopus 找 inp
    /data/home/zju321/.local/bin/udocker run \
        --workdir=/tmp \
        --volume="$WORKDIR:/tmp:ro" \
        --env=OMP_NUM_THREADS \
        --env=OCTOPUS_PAR_STATES \
        --env=OCTOPUS_PAR_DOMAINS \
        --env=OCTOPUS_PAR_KPOINTS \
        --env=LD_LIBRARY_PATH \
        bench_octopus \
        mpirun -np $mpirun_np octopus > octopus.stdout 2>&1

    end_time=$(date +%s)
    walltime=$((end_time - start_time))

    total_energy=$(grep 'Total energy' octopus.stdout | grep -v Eigenvalues | awk '{print $3}' | tail -1)
    converged=$(grep -i 'converged' octopus.stdout | tail -1 || echo 'not converged')
    exit_code=$(grep 'EXIT_CODE' octopus.stdout | tail -1 | cut -d= -f2)
    [ -z "$exit_code" ] && exit_code='?'

    echo "  Done: walltime=${walltime}s energy=${total_energy:-N/A}"
    echo "$config,$ps_val,$pd_val,$pk_val,$omp_val,$mpirun_np,$walltime,${total_energy:-NA},${converged:-NA},$exit_code" >> benchmark_ch4_v2.csv
done

echo ''
echo '=== Results (sorted by walltime) ==='
tail -n +2 benchmark_ch4_v2.csv | sort -t, -k6 -n
echo ''
echo 'Best config:'
tail -n +2 benchmark_ch4_v2.csv | sort -t, -k6 -n | head -1