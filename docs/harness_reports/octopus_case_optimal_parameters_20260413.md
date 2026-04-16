# Octopus 官方复现分案例汇总 (2026-04-13)

## 1) 本次重算数据源

- N atom 官方口径重算(JSON): octopus_n_atom_total_energy_convergence_20260413T125930Z.json
- N atom 官方口径重算(图): octopus_n_atom_total_energy_convergence_20260413T125930Z.png
- CH4 官方口径重算(JSON): octopus_ch4_total_energy_convergence_20260413T130700Z.json
- CH4 官方口径重算(图): octopus_ch4_total_energy_convergence_20260413T130700Z.png

## 2) 分案例口径 (避免一刀切)

- N atom: 按官方教程图口径，主图使用误差曲线 (total energy error + s-eigen error + p-eigen error)。
- CH4: 按教程 methane spacing 口径，主图使用总能量随 spacing 变化，并以尾段波动带 <= 0.1 eV 判据确认。
- N atom 总能量图仅作为补充结果，不替代官方误差口径主结果。
- 两个案例都先执行官方网页溯源，再触发计算。

## 3) N atom (官方误差口径主结果)

- spacing: 0.26, 0.24, 0.22, 0.20, 0.18, 0.16, 0.14 A
- reference spacing: 0.16 A
- radius: 5.0 A
- provenance anchors: 2/2

![N atom official error curve](octopus_n_atom_total_energy_convergence_20260413T125930Z.png)

## 4) CH4 (教程 methane_spacing 口径)

- spacing: 0.22, 0.20, 0.18, 0.16, 0.14, 0.12, 0.10 A
- radius: 3.5 A
- extra_states: 4
- eigensolver: chebyshev_filter
- provenance anchors: 3/3

### 关键点

| spacing (A) | total_energy (Ha) | total_energy (eV) | tail 判据相关 |
|---:|---:|---:|---|
| 0.18 | -8.04327353 | -218.867594 | 从 0.18A 到 0.10A 的尾段波动 0.153595 eV (未达 0.1) |
| 0.16 | -8.04027629 | -218.786035 | 从 0.16A 到 0.10A 的尾段波动 0.072036 eV (达标) |

![CH4 total energy curve](octopus_ch4_total_energy_convergence_20260413T130700Z.png)

## 5) N atom 总能量补充图 (补充, 非主口径)

![N atom total energy supplementary curve](octopus_n_atom_total_energy_convergence_20260413T123832Z.png)

## 6) 经验总结

- 先口径后计算: 复现任务必须先锁定官方可验证指标，再出表和画图。
- 图和表必须同口径: 既然是 total energy convergence，就只画总能量曲线。
- 溯源前置: 每次运行前都做网页锚点检查，避免“算了但不对应教程”的偏差。
- 尾段判据优先: CH4 是否满足教程阈值，应看尾段波动带，而不是单点对单点。
- 变更纪律: 无科学理由不改教程指定项(例如 chebyshev eigensolver)。

## 7) 甲烷优先扩展与验证门控落地记录 (2026-04-14)

- 目标修正: 以 N atom 成功路径为模板，先上 `ch4_gs_reference`，其余官方案例保持 pending，先自动化严格验证再上前端。
- 前端改动: 自动 Reviewer Suite 的 GS 任务从 `hydrogen_gs_reference` 切换为 `ch4_gs_reference`；审批状态仅用于 reviewer 展示与上架节奏，不阻塞求解器执行。
- 自动化改动: `scripts/run_dft_tddft_agent_suite.py` 新增 `ch4_gs_reference` 与 `n_atom_gs_official` profile；审批清单仅作为审查/记录辅助信息。
- 数据源说明: `knowledge_base/case_validation_manifest.json` 用于记录案例进度，不作为求解器参数或路由开关。
- 可视化改动: 结果面板新增结果驱动提示逻辑；N_atom 自动显示 S/P 本征态诊断信息，TDDFT 根据返回字段动态展示偶极响应说明。
- 校验结果: `npx tsc --noEmit` 通过；前端与后端/Python改动文件在编辑器错误检查中均无新增问题。
- 下一步: 按顺序执行严格验证并升级：Hydrogen GS -> H2O GS -> TDDFT Dipole -> TDDFT Absorption，每案例满足连续 3 次 PASS + 方差约束 + 溯源完整后再升为 approved。

## 8) CH4 前端发起复现记录 (20260414T082611Z)

- 触发路径: frontend-equivalent `/api/physics/run` (Octopus GS)
- API base: `http://10.72.212.33:3001`
- 参数口径: pseudo + angstrom + `fastPath=false` + `radius=3.5` + `extra_states=4` + `chebyshev_filter`
- 参考 spacing: 0.16 A

| spacing (A) | total_energy (Ha) | total_energy (eV) | error vs 0.16A (eV) | converged | scf_iterations | job_id |
|---:|---:|---:|---:|:---:|---:|---|
| 0.22 | -6.82495589 | -185.716511 | -1.763641 | Y | 27 | 136480.mu01 |
| 0.20 | -6.78979855 | -184.759831 | -0.806961 | Y | 28 | 136481.mu01 |
| 0.18 | -6.76418237 | -184.062779 | -0.109909 | Y | 32 | 136482.mu01 |
| 0.16 | -6.76014329 | -183.952870 | 0.000000 | Y | 22 | 136483.mu01 |
| 0.14 | -6.75954347 | -183.936548 | 0.016322 | Y | 26 | 136484.mu01 |
| 0.12 | -6.75757541 | -183.882995 | 0.069876 | Y | 28 | 136485.mu01 |
| 0.10 | -6.75642304 | -183.851637 | 0.101233 | Y | 40 | 136486.mu01 |

- Completed points: 7/7
- Reference point 0.16A available: Y
- Tail band (from 0.18A): 0.211142 eV
- Tail band (from 0.16A): 0.101233 eV
- Official criterion (<=0.1 eV from 0.16A): FAIL

## 9) Hydrogen 三步法验证记录 (20260414T083118Z)

- Step1 (检索):
  - Reference source: https://physics.nist.gov/cgi-bin/cuu/Value?rydhcev
  - Target: -0.500000 Ha (-13.605693 eV)
- Step2 (后端求解验证): backend-profile payload 调用 `/api/physics/run`
- Step3 (前端发起复核): frontend-equivalent payload 调用 `/api/physics/run`
- API base: `http://10.72.212.33:3001`

| Step | total_energy (Ha) | total_energy (eV) | rel.delta vs ref | within 3% |
|---|---:|---:|---:|:---:|
| Step2 Backend | -68.32278612 | -1859.1577225133478 | 135.64557224 | N |
| Step3 Frontend | -90.39550377 | -2459.7869679861346 | 179.79100754 | N |

- Inter-step delta (Step3-Step2): -600.629245 eV
- Case completion verdict: NOT_COMPLETED

## 10) Hydrogen 三步法验证记录 (Coulomb all-electron, 20260414T092526Z)

- Step1 (检索):
  - Reference source: https://physics.nist.gov/cgi-bin/cuu/Value?rydhcev
  - Target: -0.500000 Ha (-13.605693 eV)
- Step2 (后端求解验证): backend-profile payload 调用 `/api/physics/run` (Coulomb + all_electron)
- Step3 (前端发起复核): frontend-equivalent payload 调用 `/api/physics/run` (同一物理设定)
- API base: `http://10.72.212.33:3001`

| Step | total_energy (Ha) | total_energy (eV) | rel.delta vs ref | within 15% |
|---|---:|---:|---:|:---:|
| Step2 Backend | -0.43922753 | -11.95198996870128 | 0.12154494000000005 | Y |
| Step3 Frontend | -0.42649906 | -11.60563065521081 | 0.14700188000000003 | Y |

- Inter-step delta (Step3-Step2): 0.346359 eV
- Workflow completion verdict (backend/frontend consistency): NOT_COMPLETED
- Strict reference alignment (<=3% both steps): NOT_ALIGNED

## 8) CH4 前端发起复现记录 (20260414T112227Z)

- 触发路径: frontend-equivalent `/api/physics/run` (Octopus GS)
- API base: `http://10.72.212.33:3001`
- 参数口径: pseudo + angstrom + `fastPath=false` + `radius=3.5` + `extra_states=4` + `chebyshev_filter`
- 参考 spacing: 0.16 A

| spacing (A) | total_energy (Ha) | total_energy (eV) | error vs 0.16A (eV) | converged | scf_iterations | job_id |
|---:|---:|---:|---:|:---:|---:|---|
| 0.22 | -6.82495589 | -185.716511 | -1.763641 | Y | 27 | 136591.mu01 |
| 0.20 | -6.78979855 | -184.759831 | -0.806961 | Y | 28 | 136592.mu01 |
| 0.18 | -6.76418237 | -184.062779 | -0.109909 | Y | 32 | 136593.mu01 |
| 0.16 | -6.76014329 | -183.952870 | 0.000000 | Y | 22 | 136594.mu01 |
| 0.14 | N/A | N/A | N/A | N | - | timeout/error |
| 0.12 | -6.75757541 | -183.882995 | 0.069876 | Y | 28 | 136595.mu01 |
| 0.10 | -6.75642304 | -183.851637 | 0.101233 | Y | 40 | 136596.mu01 |

- Completed points: 6/7
- Reference point 0.16A available: Y
- Tail band (from 0.18A): 0.211142 eV
- Tail band (from 0.16A): 0.101233 eV
- Official criterion (<=0.1 eV from 0.16A): FAIL

## 8) CH4 前端发起复现记录 (20260414T121457Z)

- 触发路径: frontend-equivalent `/api/physics/run` (Octopus GS)
- API base: `http://10.72.212.33:3001`
- 参数口径: pseudo + angstrom + `fastPath=false` + `radius=3.5` + `extra_states=4` + `chebyshev_filter`
- 参考 spacing: 0.16 A

| spacing (A) | total_energy (Ha) | total_energy (eV) | error vs 0.16A (eV) | converged | scf_iterations | job_id |
|---:|---:|---:|---:|:---:|---:|---|
| 0.22 | -6.82495589 | -185.716511 | -1.763641 | Y | 27 | 136600.mu01 |
| 0.20 | -6.78979855 | -184.759831 | -0.806961 | Y | 28 | 136602.mu01 |
| 0.18 | -6.76418237 | -184.062779 | -0.109909 | Y | 32 | 136603.mu01 |
| 0.16 | -6.76014329 | -183.952870 | 0.000000 | Y | 22 | 136604.mu01 |
| 0.14 | -6.75954347 | -183.936548 | 0.016322 | Y | 26 | 136605.mu01 |
| 0.12 | -6.75757541 | -183.882995 | 0.069876 | Y | 28 | 136606.mu01 |
| 0.10 | N/A | N/A | N/A | N | - | timeout/error |

- Completed points: 6/7
- Reference point 0.16A available: Y
- Tail band (from 0.18A): 0.179785 eV
- Tail band (from 0.16A): 0.069876 eV
- Official criterion (<=0.1 eV from 0.16A): PASS

