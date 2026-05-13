"""
VASP backend for Dirac solver.
Handles INCAR/POSCAR/KPOINTS generation, POTCAR assembly, OUTCAR parsing,
and PBS job submission for VASP calculations.

Integrated with server.py — uses the same PBS infrastructure.
Supports NELECT-based charge control for ΔSCF ionization potential.
"""

import os
import re
import math
from typing import Optional

# ─── Constants ────────────────────────────────────────────────────────────────

VASP_BIN = "/data/software/AMD/vasp_std"
VASP_POTCARS_DIR = "/data/home/Hzk-14/pot/potpaw_PBE.54"
VASP_LD_LIBRARY_PATH = (
    "/data/home/Hzk-20/anaconda3/lib:"
    "/data/home/Hzk-14/deepmd-kit/lib"
)

# Well-known atomic geometries (Angstrom, ~ equilibrium for single atoms at origin).
# Used as defaults when only element symbol is specified.
_ATOMIC_COORDS = {
    "H":  [(0.0, 0.0, 0.0)],
    "O":  [(0.0, 0.0, 0.0)],
    "N":  [(0.0, 0.0, 0.0)],
    "C":  [(0.0, 0.0, 0.0)],
    "He": [(0.0, 0.0, 0.0)],
    "Si": [(0.0, 0.0, 0.0), (1.3575, 1.3575, 1.3575)],  # diamond
}

# Built-in molecule geometries (Angstrom)
_MOLECULES = {
    "H2O": {
        "atoms": [("O", 0, 0, 0), ("H", 0.757, 0.586, 0), ("H", -0.757, 0.586, 0)],
        "charge": 0,
    },
    "CH4": {
        "atoms": [
            ("C", 0, 0, 0),
            ("H",  0.629118,  0.629118,  0.629118),
            ("H", -0.629118, -0.629118,  0.629118),
            ("H",  0.629118, -0.629118, -0.629118),
            ("H", -0.629118,  0.629118, -0.629118),
        ],
        "charge": 0,
    },
}


# ─── VASP Input Generation ───────────────────────────────────────────────────

def generate_vasp_incar(config: dict) -> str:
    """Generate VASP INCAR file content from config dict."""
    calc_mode = str(config.get("calcMode", "gs")).strip().lower()
    species_mode = str(config.get("speciesMode", "standard")).strip().lower()

    lines = []

    # System label
    mol = config.get("octopusMolecule", config.get("moleculeName", "unknown"))
    if isinstance(mol, dict):
        mol = mol.get("name", "custom")
    sys_label = str(mol)[:32]
    lines.append(f" SYSTEM = {sys_label}")

    # SCF control
    encut = int(config.get("encut", 400))
    ediff = float(config.get("ediff", 1e-6))
    nelmin = int(config.get("nelmin", 5))
    lines.append(f" ENCUT = {encut}")
    lines.append(f" EDIFF = {ediff}")
    lines.append(f" NELMIN = {nelmin}")

    # Smearing (default: Gaussian, 0.01 eV — suitable for molecules)
    ismear = int(config.get("ismear", 0))
    sigma = float(config.get("sigma", 0.01))
    lines.append(f" ISMEAR = {ismear}")
    lines.append(f" SIGMA = {sigma}")

    # Spin polarization
    spin = str(config.get("spinComponents", "unpolarized")).strip().lower()
    ispin = 2 if spin == "polarized" else 1
    lines.append(f" ISPIN = {ispin}")

    # Start from scratch (no WAVECAR reuse across runs)
    lines.append(" ISTART = 0")
    lines.append(" ICHARG = 2")

    # XC functional
    xc = str(config.get("xcFunctional", "PBE")).strip()
    if xc.lower() in ("lda_x+lda_c_pz", "lda", "lda_x", "lda_x+lda_c_pw"):
        lines.append(" GGA = CA")  # Ceperley-Alder = LDA
    elif xc.lower() in ("gga_x_pbe+gga_c_pbe", "pbe", "gga_x_pbe"):
        lines.append(" GGA = PE")  # Perdew-Burke-Ernzerhof
    elif xc.lower() in ("hartree_fock", "hf", "exx"):
        lines.append(" GGA = PE")
        lines.append(" LHFCALC = .TRUE.")
        lines.append(" AEXX = 1.0")
    else:
        lines.append(" GGA = PE")  # Default: PBE

    # Charge control for ΔSCF
    nelect = config.get("nelect")
    if nelect is not None:
        lines.append(f" NELECT = {nelect}")
    net_charge = config.get("netCharge")
    if net_charge is not None and nelect is None:
        lines.append(f" NELECT = {8 - int(net_charge)}")  # rough estimate

    # Extra bands
    nbands = config.get("nbands")
    if nbands is not None:
        lines.append(f" NBANDS = {nbands}")

    # Ion relaxation
    if calc_mode == "go":
        lines.append(" NSW = 100")
        lines.append(" IBRION = 2")
        lines.append(" ISIF = 2")
        gotol = float(config.get("GOTolerance", 0.001))
        lines.append(f" EDIFFG = {gotol}")
    else:
        lines.append(" NSW = 0")
        lines.append(" IBRION = -1")

    # Precision / performance
    prec = str(config.get("prec", "Normal")).strip()
    lreal = str(config.get("lreal", "Auto")).strip()
    lines.append(f" PREC = {prec}")
    lines.append(f" LREAL = {lreal}")

    # Additional INCAR tags
    extra_tags = config.get("extraIncarTags", {})
    if isinstance(extra_tags, dict):
        for k, v in extra_tags.items():
            if isinstance(v, bool):
                lines.append(f" {k} = .{'TRUE' if v else 'FALSE'}.")
            elif isinstance(v, str):
                lines.append(f" {k} = {v}")
            else:
                lines.append(f" {k} = {v}")

    return "\n".join(lines)


def generate_vasp_poscar(config: dict) -> str:
    """Generate VASP POSCAR file content."""
    # Determine atom list
    atoms = []
    mol = config.get("octopusMolecule", config.get("moleculeName", ""))
    if isinstance(mol, dict):
        mol = mol.get("name", "")
    mol_name = str(mol or "").strip()

    custom_atoms = config.get("customAtoms")
    if custom_atoms and isinstance(custom_atoms, list):
        for a in custom_atoms:
            sym = a.get("symbol", a.get("element", "H"))
            x = float(a.get("x", 0))
            y = float(a.get("y", 0))
            z = float(a.get("z", 0))
            atoms.append((sym, x, y, z))
    elif mol_name.upper() in _MOLECULES:
        atoms = _MOLECULES[mol_name.upper()]["atoms"]
    elif mol_name in _ATOMIC_COORDS:
        coords = _ATOMIC_COORDS[mol_name]
        for (x, y, z) in coords:
            atoms.append((mol_name, x, y, z))
    else:
        # Default: molecule name treated as element at origin
        atoms = [(mol_name, 0, 0, 0)]

    # Count unique elements in order of first appearance
    element_order = []
    element_count = {}
    for sym, *_ in atoms:
        s = sym.capitalize()
        if s not in element_order:
            element_order.append(s)
            element_count[s] = 0
        element_count[s] += 1

    # Box size
    radius = float(config.get("octopusRadius", config.get("radius", 10.0)))
    box = float(config.get("vaspBox", radius))  # in Bohr or Angstrom
    spacing = float(config.get("octopusSpacing", config.get("gridSpacing", 0.18)))
    # Default to 10 Å box for molecules; use radius if set
    box_a = box if box > 2.0 else 10.0

    title = f"{mol_name or 'system'} from Dirac VASP backend"
    scale = 1.0

    lines = [title, f" {scale}", f" {box_a:.6f} 0.000000 0.000000",
             f" 0.000000 {box_a:.6f} 0.000000",
             f" 0.000000 0.000000 {box_a:.6f}"]

    lines.append(" " + " ".join(element_order))
    lines.append(" " + " ".join(str(element_count[e]) for e in element_order))
    lines.append("Cartesian")

    for sym, x, y, z in atoms:
        lines.append(f" {x:.6f} {y:.6f} {z:.6f}")

    return "\n".join(lines)


def generate_vasp_kpoints(config: dict) -> str:
    """Generate VASP KPOINTS file content. For molecules in boxes: Gamma-only."""
    kpt_type = str(config.get("kpointsType", "gamma")).strip().lower()
    if kpt_type == "gamma":
        return (
            "Gamma-point only\n"
            " 1\n"
            "rec\n"
            " 0 0 0 1\n"
        )
    # Monkhorst-Pack grid
    kgrid = config.get("kpointsGrid", config.get("kpoints", "1 1 1"))
    parts = str(kgrid).split()
    if len(parts) >= 3:
        nx, ny, nz = parts[0], parts[1], parts[2]
    else:
        nx = ny = nz = parts[0]
    return (
        f"Monkhorst-Pack {nx}x{ny}x{nz}\n"
        " 0\n"
        "Monkhorst\n"
        f" {nx} {ny} {nz}\n"
        " 0 0 0\n"
    )


# ─── POTCAR Assembly ─────────────────────────────────────────────────────────

def assemble_potcar(element_list: list[str]) -> str:
    """Assemble POTCAR by concatenating standard PAW_PBE POTCARs in order."""
    parts = []
    for elem in element_list:
        e = elem.capitalize()
        potcar_path = os.path.join(VASP_POTCARS_DIR, e, "POTCAR")
        if not os.path.exists(potcar_path):
            raise ValueError(
                f"No POTCAR for element '{e}' at {potcar_path}. "
                f"Check {VASP_POTCARS_DIR} for available elements."
            )
        with open(potcar_path, "r") as f:
            parts.append(f.read())
    return "".join(parts)


# ─── VASP Output Parsing ────────────────────────────────────────────────────

def parse_vasp_outcar(outcar_path: str) -> dict:
    """Parse VASP OUTCAR file and extract key results."""
    result = {
        "total_energy_ev": None,
        "fermi_energy_ev": None,
        "magnetization": None,
        "band_energies_ev": [],
        "occupations": [],
        "scf_converged": False,
        "nbands": 0,
        "nelect": None,
        "scf_iterations": 0,
    }

    if not os.path.exists(outcar_path):
        return result

    with open(outcar_path, "r", errors="replace") as f:
        content = f.read()

    # Total energy
    m = re.findall(r"free\s+energy\s+TOTEN\s*=\s*([\d.\-E+]+)\s*eV", content)
    if m:
        result["total_energy_ev"] = float(m[-1])

    # Fermi energy
    m = re.search(r"E-fermi\s*:\s*([\d.\-E+]+)", content)
    if m:
        result["fermi_energy_ev"] = float(m.group(1))

    # Magnetization
    for line in content.splitlines():
        if "number of electron" in line and "magnetization" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "magnetization" and i + 1 < len(parts):
                    try:
                        result["magnetization"] = float(parts[i + 1])
                    except ValueError:
                        pass
                    break

    # NELECT
    m = re.search(r"NELECT\s*=\s*([\d.]+)", content)
    if m:
        result["nelect"] = float(m.group(1))

    # SCF convergence
    result["scf_converged"] = "writing wavefunctions" in content.lower()

    # SCF iterations: count "LOOP:" lines (not "LOOP+" post-SCF)
    result["scf_iterations"] = len(re.findall(r"^\s+LOOP:", content, re.MULTILINE))

    # NBANDS
    m = re.search(r"NBANDS=\s*(\d+)", content)
    if m:
        result["nbands"] = int(m.group(1))

    # Band energies from EIGENVAL-like section in OUTCAR
    eigen_section = re.search(
        r"band No\.\s+band energies\s+occupation\s*\n(.*?)(?=\n\s*\n|\Z)",
        content, re.DOTALL
    )
    if eigen_section:
        for line in eigen_section.group(1).strip().splitlines():
            parts = line.split()
            if len(parts) >= 3:
                try:
                    result["band_energies_ev"].append(float(parts[1]))
                    result["occupations"].append(float(parts[2]))
                except ValueError:
                    continue

    return result


def parse_vasp_eigenval(eigenval_path: str) -> dict:
    """Parse VASP EIGENVAL file for band structure data."""
    if not os.path.exists(eigenval_path):
        return {"kpoints": [], "bands": [], "nelect": None}

    with open(eigenval_path, "r") as f:
        lines = f.readlines()

    if len(lines) < 6:
        return {"kpoints": [], "bands": [], "nelect": None}

    # Header: lines 0-4 are metadata, line 5 has nelect/nkpts/nbands
    parts = lines[5].split()
    if len(parts) >= 3:
        nelect = int(parts[0])
        nkpts = int(parts[1])
        nbands = int(parts[2])
    else:
        return {"kpoints": [], "bands": [], "nelect": None}

    kpoints = []
    bands = [[] for _ in range(nbands)]

    idx = 6
    for ik in range(nkpts):
        if idx >= len(lines):
            break
        # Skip blank lines
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
        if idx >= len(lines):
            break
        # k-point header
        kp_parts = lines[idx].split()
        if len(kp_parts) >= 4:
            kpoints.append({
                "kx": float(kp_parts[0]),
                "ky": float(kp_parts[1]),
                "kz": float(kp_parts[2]),
                "weight": float(kp_parts[3]),
            })
        idx += 1
        for ib in range(nbands):
            if idx >= len(lines):
                break
            bp = lines[idx].split()
            if len(bp) >= 2:
                bands[ib].append(float(bp[1]))
            idx += 1

    return {"kpoints": kpoints, "bands": bands, "nelect": nelect}


# ─── PBS Script Generation ───────────────────────────────────────────────────

def build_vasp_pbs_script(
    work_dir: str,
    queue: str = "workq",
    ncpus: int = 1,
    walltime: str = "01:00:00",
    job_name: str = "dirac_vasp",
    fast_path: bool = False,
) -> str:
    """Generate a PBS job script for VASP calculations."""
    return f"""#!/bin/bash
#PBS -N {job_name}
#PBS -l ncpus={ncpus}
#PBS -l walltime={walltime}
#PBS -j oe
#PBS -o {work_dir}/vasp_pbs_output.log

cd {work_dir}

export LD_LIBRARY_PATH={VASP_LD_LIBRARY_PATH}:$LD_LIBRARY_PATH
export VASP={VASP_BIN}

echo "=== VASP Job: {job_name} ==="
echo "Date: $(date)"
echo "Node: $(hostname)"
echo "NCPUS: {ncpus}"

echo "Running VASP..."
{VASP_BIN} > vasp.stdout 2> vasp.stderr
RC=$?

echo "Exit code: $RC"
echo "Total energy:"
grep "free  energy   TOTEN" OUTCAR | tail -1 || echo "NOT FOUND"

echo "Date: $(date)"
exit $RC
"""
