# Common Commands

## Preflight (first after connect)

```bash
ssh dirac-key "(ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null) | grep -E ':(3004|5173|8000|8001|8101)\b'"
curl -s http://127.0.0.1:3004/api/automation/dispatch/latest
curl -s http://127.0.0.1:8001/harness/case_registry
```

## Auto Dispatch

```bash
python scripts/dispatch_dirac_task.py \
  --task 'n_atom_gs_official' \
  --source cli \
  --execute \
  --exec-timeout-seconds 300 \
  --sync-state state/dirac_solver_progress_sync.json
```

## Report Cleanup

```bash
python scripts/cleanup_harness_reports.py
```

## VASP Direct Call

```bash
curl -s -X POST http://127.0.0.1:8000/solve_vasp \
  -H 'Content-Type: application/json' \
  -d '{"octopusMolecule":"H2O","xcFunctional":"PBE","spinComponents":"unpolarized","encut":520,"ediff":1e-6,"prec":"Accurate","vaspBox":10.0}' | python -m json.tool
```

## PBS Job Monitoring

```bash
qstat -f JOBID | grep -E 'walltime|Job_Name|queue'    # 详细状态
qstat | grep $(whoami) | head -10                       # 我的所有作业
tracejob JOBID                                          # 作业生命周期
```
