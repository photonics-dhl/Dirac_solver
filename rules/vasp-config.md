# VASP 6.x Configuration (PAW-PBE)

## Paths

- Binary: `/data/software/AMD/vasp_std`
- POTCAR: `/data/home/Hzk-14/pot/potpaw_PBE.54/`
- LD_LIBRARY_PATH: `/data/home/Hzk-20/anaconda3/lib:/data/home/Hzk-14/deepmd-kit/lib`

## Standard Parameters

ENCUT=520 eV, EDIFF=1e-6, PREC=Accurate, ISMEAR=0, SIGMA=0.01, Gamma-only k-points, 8-10 Å cubic box

## Supported Elements

Full periodic table coverage via potpaw_PBE.54 (PAW-PBE, standard). 85+ elements available:

`Ac Ag Al Am Ar As At Au B Ba Be Bi Br C Ca Cd Ce Cf Cl Cm Co Cr Cs Cu Dy Er Eu F Fe Fr Ga Gd Ge H He Hf Hg Ho I In Ir K Kr La Li Lu Mg Mn Mo N Na Nb Nd Ne Ni Np O Os P Pa Pb Pd Pm Po Pr Pt Pu Ra Rb Re Rh Rn Ru S Sb Sc Se Si Sm Sn Sr Ta Tb Tc Te Th Ti Tl Tm U V W Xe Y Yb Zn Zr`

Variants also available: `*_sv` (semi-core), `*_pv` (p-core), `*_GW` (GW-optimized), `*_h` (hard). POTCAR assembled via `assemble_potcar()` — any element with directory under `VASP_POTCARS_DIR` works without code change.

## ΔSCF Ionization Potential

Supports cation calculation via `nelect=N-1` parameter.

## Reference Data

`knowledge_base/corpus_new/vasp_gs_reference.md` — atom + molecule GS reference values.
