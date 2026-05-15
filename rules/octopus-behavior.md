# Octopus 16.0 Behavior Notes

## PP Mode Verified Parameters

Ground truth: `docs/octopus_case_convergence.md`

| Atom | Mode | spacing | radius | XC | Eigenvalue Error | Status |
|------|------|---------|--------|-----|---------|--------|
| N | PP LDA | 0.18 Å | 10.0 Å | lda_x+lda_c_pz | s: 0.4% | OK |
| H | PP PBE | 0.18 Å | 10.0 Å | gga_x_pbe+gga_c_pbe | 1s: 0.03% | OK |
| He | PP LDA | 0.15 Å | 10.0 Å | lda_x+lda_c_pz | 1s: 1.8% | OK |

## Critical Gotchas

- **FromScratch + CalculationMode=td/casida won't auto-run GS**. Two-step required: first `CalculationMode=gs`, then `CalculationMode=td/casida` with `FromScratch=no`
- **Casida XC Kernel supports LDA only**. PBE/GGA triggers fatal error: "Only LDA functionals are authorized in XCKernel"
- **ScaLAPACKCompatible=yes requires ExperimentalFeatures=yes**, otherwise fatal error
- **`TDOutput=cross_section_vector` does not exist** — use `oct-propagation_spectrum` post-processing tool instead

## udocker Container Reuse

Avoid ~40s image extraction overhead per run:

```bash
CONTAINER=$(udocker ps | grep octopus | head -1 | awk '{print $1}')
udocker run --volume=/data/home/zju321:/data/home/zju321 \
  --env="OMP_NUM_THREADS=16" $CONTAINER \
  bash -c "cd /workdir && mpirun -np 4 --bind-to core /app/bin/octopus"
```
