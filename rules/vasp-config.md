# VASP 6.x Configuration (PAW-PBE)

## Paths

- Binary: `/data/software/AMD/vasp_std`
- POTCAR: `/data/home/Hzk-14/pot/potpaw_PBE.54/`
- LD_LIBRARY_PATH: `/data/home/Hzk-20/anaconda3/lib:/data/home/Hzk-14/deepmd-kit/lib`

## Standard Parameters

ENCUT=520 eV, EDIFF=1e-6, PREC=Accurate, ISMEAR=0, SIGMA=0.01, Gamma-only k-points, 8-10 Å cubic box

## Supported Elements

H, C, N, O (PAW_RPBE POTCAR; extend by adding more POTCAR files)

## ΔSCF Ionization Potential

Supports cation calculation via `nelect=N-1` parameter.

## Reference Data

`knowledge_base/corpus_new/vasp_gs_reference.md` — atom + molecule GS reference values.
