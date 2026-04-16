# Parameter Convergence Log

Track Octopus parameter combinations and reviewer tables by round.
Update rule: append one new round block after each suite run.

## Round 2026-04-13T02:56:45.696194Z

### Parameter Combo
- molecule: H
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| hydrogen_gs_reference | PASS | octopus-mcp | -0.48519720 | -0.50000000 | 0.01480280 | 0.029606 | 0.030000 | True | -13.20288841 | -6.77452293 | -13.60569312 | 0.029606 | True | 135983.mu01 | 64/64 | workq | unknown |

- Final verdict: PASS

## Round 2026-04-13T03:00:14.146621Z

### Parameter Combo
- molecule: H2O
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_gs_reference | FAIL | octopus-mcp | -49.48216266 | -76.43890000 | 26.95673734 | 0.352657 | 0.030000 | False | - | -5.57240491 | - | - | - | 135984.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T03:19:11.852253Z

### Parameter Combo
- molecule: H2O
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_gs_reference_octopus_formula | PASS | octopus-mcp | -49.48216266 | -49.48216266 | 0.00000000 | 0.000000 | 0.030000 | True | - | -5.57240491 | - | - | - | 135986.mu01 | 64/64 | workq | unknown |

- Final verdict: PASS

## Round 2026-04-13T03:22:25.323855Z

### Parameter Combo
- molecule: H2O
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_gs_reference | FAIL | octopus-mcp | -49.48216266 | -76.43890000 | 26.95673734 | 0.352657 | 0.030000 | False | - | -5.57240491 | - | - | - | 135988.mu01 | 64/64 | workq | (fat01:ncpus=64) |

- Final verdict: FAIL

## Round 2026-04-13T03:23:10.093711Z

### Parameter Combo
- molecule: H2O
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_gs_reference | FAIL | octopus-mcp | -49.48216266 | -76.43890000 | 26.95673734 | 0.352657 | 0.030000 | False | - | -5.57240491 | - | - | - | 135987.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T03:45:46.917413Z

### Parameter Combo
- molecule: H2O
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_gs_reference | FAIL | octopus-mcp | -49.48216266 | -76.43890000 | 26.95673734 | 0.352657 | 0.030000 | False | - | -5.57240491 | - | - | - | 135995.mu01 | 64/64 | workq | (fat01:ncpus=64) |

- Final verdict: FAIL

## Round 2026-04-13T03:46:31.810275Z

### Parameter Combo
- molecule: H2O
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_gs_reference | FAIL | octopus-mcp | -49.48216266 | -76.43890000 | 26.95673734 | 0.352657 | 0.030000 | False | - | -5.57240491 | - | - | - | 135994.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T04:07:04.299991Z

### Parameter Combo
- molecule: H
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| hydrogen_gs_reference | PASS | octopus-mcp | -0.48519720 | -0.50000000 | 0.01480280 | 0.029606 | 0.030000 | True | -13.20288841 | -6.77452293 | -13.60569312 | 0.029606 | True | 135997.mu01 | 64/64 | workq | unknown |

- Final verdict: PASS

## Round 2026-04-13T04:16:29.434225Z

### Parameter Combo
- molecule: H2O
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_gs_reference | FAIL | octopus-mcp | -49.48216266 | -76.43890000 | 26.95673734 | 0.352657 | 0.030000 | False | - | -5.57240491 | - | - | - | 135998.mu01 | 64/64 | workq | unknown |
| h2o_tddft_absorption | FAIL | octopus-mcp | 2000.00000000 | 2000.00000000 | 0.00000000 | 0.000000 | 0.050000 | True | - | -5.57240491 | - | - | - | 135999.mu01 | 64/64 | workq | unknown |
| h2o_tddft_dipole_response | FAIL | octopus-mcp | 261.00000000 | 221.00000000 | 40.00000000 | 0.180995 | 0.080000 | False | - | -5.57240491 | - | - | - | 136002.mu01 | 64/64 | workq | unknown |
| h2o_tddft_radiation_spectrum | FAIL | octopus-mcp | - | - | - | - | - | - | - | -5.57240491 | - | - | - | 136004.mu01 | 64/64 | workq | unknown |
| h2o_tddft_eels_spectrum | FAIL | octopus-mcp | - | - | - | - | - | - | - | -5.57240491 | - | - | - | 136006.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T04:42:02.914680Z

### Parameter Combo
- molecule: H2O
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_gs_reference | FAIL | octopus-mcp | -49.48216266 | -76.43890000 | 26.95673734 | 0.352657 | 0.030000 | False | - | -5.57240491 | - | - | - | 136011.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T04:46:27.413280Z

### Parameter Combo
- molecule: H2O
- spacing: 0.3
- radius: 8.0
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: 320
- scf_tolerance: 1e-06

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_gs_reference | FAIL | octopus-mcp | -49.48193533 | -76.43890000 | 26.95696467 | 0.352660 | 0.030000 | False | - | -5.55112560 | - | - | - | 136012.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T04:48:08.292304Z

### Parameter Combo
- molecule: H
- spacing: 0.3
- radius: 8.0
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: 320
- scf_tolerance: 1e-06

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| hydrogen_gs_reference | FAIL | octopus-mcp | -0.45469394 | -0.50000000 | 0.04530606 | 0.090612 | 0.030000 | False | -12.37285243 | -6.39889677 | -13.60569312 | 0.090612 | False | 136013.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T04:49:17.168205Z

### Parameter Combo
- molecule: H
- spacing: 0.2
- radius: 10.0
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: 420
- scf_tolerance: 1e-07

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| hydrogen_gs_reference | FAIL | octopus-mcp | -0.43775161 | -0.50000000 | 0.06224839 | 0.124497 | 0.030000 | False | -11.91182814 | -6.19238945 | -13.60569312 | 0.124497 | False | 136015.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T04:50:26.729884Z

### Parameter Combo
- molecule: H
- spacing: 0.3
- radius: 8.0
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: 320
- scf_tolerance: 1e-07

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| hydrogen_gs_reference | FAIL | octopus-mcp | -0.45469394 | -0.50000000 | 0.04530606 | 0.090612 | 0.030000 | False | -12.37285243 | -6.39889677 | -13.60569312 | 0.090612 | False | 136016.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T04:51:57.015175Z

### Parameter Combo
- molecule: H
- spacing: 0.3
- radius: 10.0
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: 420
- scf_tolerance: 1e-07

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| hydrogen_gs_reference | FAIL | octopus-mcp | -0.45481069 | -0.50000000 | 0.04518931 | 0.090379 | 0.030000 | False | -12.37602935 | -6.41560457 | -13.60569312 | 0.090379 | False | 136017.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T04:54:09.073128Z

### Parameter Combo
- molecule: H2O
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_tddft_absorption | FAIL | octopus-mcp | 2000.00000000 | 2000.00000000 | 0.00000000 | 0.000000 | 0.050000 | True | - | -5.57240491 | - | - | - | 136018.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T04:58:46.244417Z

### Parameter Combo
- molecule: H2O
- spacing: 0.34
- radius: 6.6
- extra_states: 4
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_tddft_absorption | FAIL | octopus-mcp | 0.00000000 | 2000.00000000 | -2000.00000000 | 1.000000 | 0.050000 | False | - | -5.51909778 | - | - | - | 136020.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T05:00:09.206861Z

### Parameter Combo
- molecule: H
- spacing: 0.3
- radius: 10.0
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: 420
- scf_tolerance: 1e-07

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| hydrogen_gs_reference | FAIL | octopus-mcp | -0.45481069 | -0.50000000 | 0.04518931 | 0.090379 | 0.030000 | False | -12.37602935 | -6.41560457 | -13.60569312 | 0.090379 | False | 136026.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T05:05:03.580365Z

### Parameter Combo
- molecule: H2O
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_tddft_dipole_response | FAIL | octopus-mcp | 221.00000000 | 221.00000000 | 0.00000000 | 0.000000 | 0.080000 | True | - | -5.57240491 | - | - | - | 136028.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T05:10:06.306838Z

### Parameter Combo
- molecule: H2O
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_tddft_dipole_response | PASS | octopus-mcp | 221.00000000 | 221.00000000 | 0.00000000 | 0.000000 | 0.080000 | True | - | -5.57240491 | - | - | - | 136032.mu01 | 64/64 | workq | unknown |

- Final verdict: PASS

## Round 2026-04-13T05:11:21.495230Z

### Parameter Combo
- molecule: H2O
- spacing: 0.3
- radius: 8.0
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: 400
- scf_tolerance: 1e-07

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_gs_reference | FAIL | octopus-mcp | -49.48193533 | -76.43890000 | 26.95696467 | 0.352660 | 0.030000 | False | - | -5.55112560 | - | - | - | 136036.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T06:40:08.352778Z

### Parameter Combo
- molecule: H2O
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_tddft_dipole_response | FAIL | octopus-mcp | 221.00000000 | 221.00000000 | 0.00000000 | 0.000000 | 0.080000 | True | - | -5.57240491 | - | - | - | 136048.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-13T06:42:23.257990Z

### Parameter Combo
- molecule: H2O
- spacing: 0.24
- radius: 6.5
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| h2o_tddft_absorption | FAIL | octopus-mcp | 2000.00000000 | 2000.00000000 | 0.00000000 | 0.000000 | 0.050000 | True | - | -5.44135481 | - | - | - | 136054.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-16T00:52:11.634771Z

### Parameter Combo
- molecule: H
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| hydrogen_gs_reference | FAIL | octopus-mcp | -68.32278612 | -0.50000000 | -67.82278612 | 135.645572 | 0.030000 | False | -1859.15772251 | -1791.15543835 | -13.60569312 | 135.645572 | False | 137331.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-16T00:56:42.691482Z

### Parameter Combo
- molecule: H
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| hydrogen_gs_reference | FAIL | octopus-mcp | -68.32278612 | -0.50000000 | -67.82278612 | 135.645572 | 0.030000 | False | -1859.15772251 | -1791.15543835 | -13.60569312 | 135.645572 | False | 137332.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-16T01:26:08.872647Z

### Parameter Combo
- molecule: H
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| hydrogen_gs_reference | FAIL | octopus-mcp | -68.32278612 | -0.50000000 | -67.82278612 | 135.645572 | 0.030000 | False | -1859.15772251 | -1791.15543835 | -13.60569312 | 135.645572 | False | 137335.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL

## Round 2026-04-16T01:30:42.939764Z

### Parameter Combo
- molecule: H
- spacing: backend-default
- radius: backend-default
- extra_states: backend-default
- xc_functional: gga_x_pbe+gga_c_pbe
- max_scf_iterations: backend-default
- scf_tolerance: backend-default

### Result Table

| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|
| hydrogen_gs_reference | FAIL | octopus-mcp | -68.32278612 | -0.50000000 | -67.82278612 | 135.645572 | 0.030000 | False | -1859.15772251 | -1791.15543835 | -13.60569312 | 135.645572 | False | 137336.mu01 | 64/64 | workq | unknown |

- Final verdict: FAIL
