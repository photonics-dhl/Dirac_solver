import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp.server import Server
from mcp.server.sse import SseServerTransport


def sanitize_floats(obj):
    """Recursively replace NaN/Inf with 0.0 so JSON serialization never crashes."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_floats(v) for v in obj]
    return obj
import mcp.types as types
from jinja2 import Template

mcp_server = Server("octopus-physics-mcp")

# ─── Octopus inp templates ────────────────────────────────────────

POTENTIAL_TEMPLATES = {
    "Harmonic": '"0.5*x^2"',
    "FiniteWell": '"-{depth}*step({hw}-abs(x))"',
    "FreeSpace": '"0"',
}

# Real 3D Coordinates (Angstroms roughly for demonstration, Octopus default is Ang if Units=eV_Angstrom, otherwise Bohr)
# We will use default atomic units (Bohr), but these serve as a demo structure
MOLECULES = {
    "H": [
        " 'H' | 0.0 | 0.0 | 0.0 "
    ],
    "He": [
        " 'He' | 0.0 | 0.0 | 0.0 "
    ],
    "H2": [
        " 'H' | 0.0 | 0.0 | -0.7 " ,
        " 'H' | 0.0 | 0.0 | 0.7 "
    ],
    "N2": [
        " 'N' | 0.0 | 0.0 | -1.03 " ,
        " 'N' | 0.0 | 0.0 | 1.03 "
    ],
    "CH4": [
        " 'C' | 0.0 | 0.0 | 0.0 " ,
        " 'H' | 1.186 | 1.186 | 1.186 " ,
        " 'H' | -1.186 | -1.186 | 1.186 " ,
        " 'H' | 1.186 | -1.186 | -1.186 " ,
        " 'H' | -1.186 | 1.186 | -1.186 "
    ],
    "Benzene": [
        " 'C' | 0.000000 |  1.396000 | 0.000000 ",
        " 'C' | 1.208966 |  0.698000 | 0.000000 ",
        " 'C' | 1.208966 | -0.698000 | 0.000000 ",
        " 'C' | 0.000000 | -1.396000 | 0.000000 ",
        " 'C' |-1.208966 | -0.698000 | 0.000000 ",
        " 'C' |-1.208966 |  0.698000 | 0.000000 ",
        " 'H' | 0.000000 |  2.484000 | 0.000000 ",
        " 'H' | 2.151214 |  1.242000 | 0.000000 ",
        " 'H' | 2.151214 | -1.242000 | 0.000000 ",
        " 'H' | 0.000000 | -2.484000 | 0.000000 ",
        " 'H' |-2.151214 | -1.242000 | 0.000000 ",
        " 'H' |-2.151214 |  1.242000 | 0.000000 "
    ],
    # ── New molecules added 2026-03 ──
    "CO": [
        " 'C' | 0.0 | 0.0 | -1.066 ",
        " 'O' | 0.0 | 0.0 |  1.066 ",
    ],
    "H2O": [
        " 'O' | 0.0    | 0.0 |  0.0   ",
        " 'H' | 1.430  | 0.0 | -1.107 ",
        " 'H' |-1.430  | 0.0 | -1.107 ",
    ],
    "NH3": [
        " 'N' | 0.0    |  0.000 |  0.0   ",
        " 'H' | 0.0    |  1.771 | -0.627 ",
        " 'H' | 1.533  | -0.886 | -0.627 ",
        " 'H' |-1.533  | -0.886 | -0.627 ",
    ],
    "C2H4": [
        " 'C' | 0.0    |  0.0  |  1.261 ",
        " 'C' | 0.0    |  0.0  | -1.261 ",
        " 'H' | 1.745  |  0.0  |  2.332 ",
        " 'H' |-1.745  |  0.0  |  2.332 ",
        " 'H' | 1.745  |  0.0  | -2.332 ",
        " 'H' |-1.745  |  0.0  | -2.332 ",
    ],
    "Li": [" 'Li' | 0.0 | 0.0 | 0.0 "],
    "Na": [" 'Na' | 0.0 | 0.0 | 0.0 "],
    "LiH": [
        " 'Li' | 0.0 | 0.0 | -1.511 ",
        " 'H'  | 0.0 | 0.0 |  1.511 ",
    ],
    # Periodic crystals — use ReducedCoordinates in generate_inp()
    "Si": [
        " 'Si' | 0.0   | 0.0   | 0.0   ",
        " 'Si' | 2.566 | 2.566 | 2.566 ",
    ],
    "Al2O3": [
        " 'Al' | 0.0   | 0.0   |  2.263 ",
        " 'Al' | 0.0   | 0.0   | -2.263 ",
        " 'O'  | 2.386 | 0.0   |  0.0   ",
        " 'O'  |-1.193 | 2.067 |  0.0   ",
        " 'O'  |-1.193 |-2.067 |  0.0   ",
    ],
}

# 2D coordinates (Bohr) — bond axes rotated into the xy-plane
MOLECULES_2D = {
    "H": [" 'H' | 0.0 | 0.0 "],
    "He": [" 'He' | 0.0 | 0.0 "],
    "H2": [
        " 'H' | -0.7 | 0.0 ",
        " 'H' |  0.7 | 0.0 ",
    ],
    "N2": [
        " 'N' | -1.03 | 0.0 ",
        " 'N' |  1.03 | 0.0 ",
    ],
    "CH4": [
        " 'C' |  0.000 |  0.000 ",
        " 'H' |  1.186 |  1.186 ",
        " 'H' | -1.186 |  1.186 ",
        " 'H' | -1.186 | -1.186 ",
        " 'H' |  1.186 | -1.186 ",
    ],
    "Benzene": [
        " 'C' |  0.000000 |  1.396000 ",
        " 'C' |  1.208966 |  0.698000 ",
        " 'C' |  1.208966 | -0.698000 ",
        " 'C' |  0.000000 | -1.396000 ",
        " 'C' | -1.208966 | -0.698000 ",
        " 'C' | -1.208966 |  0.698000 ",
        " 'H' |  0.000000 |  2.484000 ",
        " 'H' |  2.151214 |  1.242000 ",
        " 'H' |  2.151214 | -1.242000 ",
        " 'H' |  0.000000 | -2.484000 ",
        " 'H' | -2.151214 | -1.242000 ",
        " 'H' | -2.151214 |  1.242000 ",
    ],
    # ── New molecules added 2026-03 ──
    "CO":  [" 'C' | -1.066 | 0.0 ", " 'O' |  1.066 | 0.0 "],
    "H2O": [" 'O' |  0.0   | 0.0 ", " 'H' |  1.430 | -1.107 ", " 'H' | -1.430 | -1.107 "],
    "NH3": [
        " 'N' |  0.0   |  0.0   ",
        " 'H' |  1.771 | -0.627 ",
        " 'H' | -0.886 | -0.627 ",
    ],
    "C2H4": [
        " 'C' |  1.261 |  0.0   ",
        " 'C' | -1.261 |  0.0   ",
        " 'H' |  2.332 |  1.745 ",
        " 'H' |  2.332 | -1.745 ",
        " 'H' | -2.332 |  1.745 ",
        " 'H' | -2.332 | -1.745 ",
    ],
    "Li":  [" 'Li' | 0.0 | 0.0 "],
    "Na":  [" 'Na' | 0.0 | 0.0 "],
    "LiH": [" 'Li' | -1.511 | 0.0 ", " 'H' |  1.511 | 0.0 "],
    "Si":  [" 'Si' | 0.0 | 0.0 "],  # periodic: use ReducedCoordinates
    "Al2O3": [" 'Al' | 0.0 | 0.0 ", " 'O' |  2.386 | 0.0 "],  # simplified
}

octopus_inp_template = Template("""CalculationMode = gs
Dimensions = {{ dimensions }}
BoxShape = sphere
Spacing = {{ grid_spacing }}
Radius = {{ radius }}

ExtraStates = {{ extra_states }}

%Output
  wfs
  potential
  eigenvalues
%
OutputFormat = axis_x

%Species
  "Particle" | species_user_defined | potential_formula | {{ potential_formula }} | valence | 1
%

%Coordinates
  "Particle" | 0
%
""")


# ─── Helper: run Octopus and parse results ────────────────────────

def generate_inp(config: dict, is_td: bool = False) -> str:
    """Generate an Octopus inp file from physics config."""
    engine_mode = config.get("engineMode", "local1D")
    dim_str = config.get("octopusDimensions", "3D")

    if engine_mode == "octopus3D" and dim_str != "1D":
        mol_raw = config.get("molecule", config.get("moleculeName", config.get("octopusMolecule", "H2")))
        # mol_raw can be a string name ("H2") or a dict {"name": "H2", "atoms": [...]}
        if isinstance(mol_raw, dict):
            molecule = mol_raw.get("name", "H2")
            custom_atoms = mol_raw.get("atoms", None)
        else:
            molecule = mol_raw
            custom_atoms = None

        dimensions = 2 if dim_str == "2D" else 3

        # Build coords_str from custom atoms if provided, else from MOLECULES table
        if custom_atoms:
            coords_lines = [f"  '{a['symbol']}' | {a['x']} | {a['y']} | {a['z']}" for a in custom_atoms]
            coords_str = "\n".join(coords_lines)
        elif dimensions == 2:
            coords = MOLECULES_2D.get(molecule, MOLECULES_2D.get("H2", [" 'H' | 0.0 | 0.0 "]))
            coords_str = "\n".join(coords)
        else:
            coords = MOLECULES.get(molecule, MOLECULES["H2"])
            coords_str = "\n".join(coords)

        # Molecule Mode (2D or 3D)
        inp = f"Dimensions = {dimensions}\n"
        inp += f"CalculationMode = {'td' if is_td else 'gs'}\n\n"
        
        # Grid parameters from config
        spacing = config.get("octopusSpacing", config.get("gridSpacing", config.get("spacing", 0.3)))
        # Priority: octopusRadius (a real radius) > spatialRange/2 (spatialRange is a diameter) > radius > default
        # IMPORTANT: only halve when falling back to spatialRange — if octopusRadius is explicitly set it is already a radius.
        if "octopusRadius" in config:
            radius = float(config["octopusRadius"])
        elif "spatialRange" in config:
            radius = float(config["spatialRange"]) / 2.0  # spatialRange is diameter
        else:
            radius = float(config.get("radius", 10.0))

        # Auto-expand radius so all atoms fit inside the global sphere (BoxShape=sphere is centered at origin).
        # Any atom with dist_from_origin > radius is outside the simulation box and will cause nonsensical SCF or timeout.
        import math as _math
        if custom_atoms:
            _atom_coords = custom_atoms
        elif dimensions == 2:
            _atom_coords = MOLECULES_2D.get(molecule, [])
        else:
            _atom_coords = MOLECULES.get(molecule, [])
        _max_dist = 0.0
        for _a in _atom_coords:
            if isinstance(_a, dict):
                _d = _math.sqrt(float(_a.get('x', 0))**2 + float(_a.get('y', 0))**2 + float(_a.get('z', 0))**2)
            else:
                # parse "  'H' | x | y | z " or "  'H' | x | y " strings
                _parts = [p.strip() for p in str(_a).split('|')]
                try:
                    _coords = [float(_parts[i]) for i in range(1, min(4, len(_parts)))]
                    _d = _math.sqrt(sum(c**2 for c in _coords))
                except (ValueError, IndexError):
                    _d = 0.0
            if _d > _max_dist:
                _max_dist = _d
        _min_required_radius = _max_dist + 5.0  # 5 Bohr padding so atoms are not on the boundary
        if float(radius) < _min_required_radius:
            print(f"[WARN] Box radius {radius} Bohr too small for geometry (max atom dist={_max_dist:.2f} Bohr). Auto-expanding to {_min_required_radius:.1f} Bohr.", flush=True)
            radius = round(_min_required_radius, 1)

        # Guard against OOM: if effective box volume at the chosen spacing would produce >8M grid points, raise spacing.
        _effective_diam = 2.0 * float(radius)
        _npts_per_axis = _effective_diam / float(spacing)
        _total_pts = _npts_per_axis ** 3
        if _total_pts > 8_000_000:
            _safe_spacing = round((_effective_diam / (8_000_000 ** (1/3))), 2)
            print(f"[WARN] Spacing={spacing} with radius={radius} → {_total_pts/1e6:.1f}M grid points (exceeds 8M limit). Clamping spacing to {_safe_spacing} Bohr.", flush=True)
            spacing = max(float(spacing), _safe_spacing)

        inp += f"Radius = {radius}\n"
        inp += f"Spacing = {spacing}\n\n"
        
        inp += "%Species\n"
        # Build species block — formula-based potentials for all present elements
        elements_in_mol = set()
        all_coords = custom_atoms if custom_atoms else (
            MOLECULES_2D.get(molecule, []) if dimensions == 2 else MOLECULES.get(molecule, [])
        )
        for line in all_coords:
            import re as _re
            if isinstance(line, dict):
                # custom_atoms are dicts: {symbol, x, y, z}
                sym = str(line.get("symbol", "")).strip()
                if sym:
                    elements_in_mol.add(sym)
            else:
                m_sym = _re.search(r"'([A-Za-z]{1,2})'", str(line))
                if m_sym:
                    elements_in_mol.add(m_sym.group(1))
        # Hardcoded formula map: symbol -> (formula, valence)
        FORMULA_MAP = {
            "H":  ("-1/sqrt(r^2+0.01)",  1),
            "He": ("-2/sqrt(r^2+0.01)",  2),
            "Li": ("-1/sqrt(r^2+0.01)",  1),
            "C":  ("-4/sqrt(r^2+0.01)",  4),
            "N":  ("-5/sqrt(r^2+0.01)",  5),
            "O":  ("-6/sqrt(r^2+0.01)",  6),
            "Na": ("-1/sqrt(r^2+0.04)",  1),
            "Si": ("-4/sqrt(r^2+0.01)",  4),
            "Al": ("-3/sqrt(r^2+0.01)",  3),
        }
        for sym in sorted(elements_in_mol):
            if sym in FORMULA_MAP:
                formula_str, valence = FORMULA_MAP[sym]
                inp += f"  '{sym}' | species_user_defined | potential_formula | \"{formula_str}\" | valence | {valence}\n"
            else:
                # Unknown element — use generic 1-electron approximation
                inp += f"  '{sym}' | species_user_defined | potential_formula | \"-1/sqrt(r^2+0.1)\" | valence | 1\n"
        inp += "%\n\n"

        inp += "%Coordinates\n"
        inp += coords_str + "\n"
        inp += "%\n\n"

        # Explicitly disable external PSF requirement
        inp += "LCAOReadWeights = no\n\n"

        # SCF convergence tuning — especially important for custom-potential multi-atom geometries
        # where LCAO initial guess is unavailable and Broyden can oscillate.
        # Smaller Mixing (0.1 vs default 0.3) + more history steps = more stable convergence.
        inp += "Mixing = 0.1\n"
        inp += "MixNumberSteps = 8\n"
        inp += "MaxSCFIterations = 200\n"
        inp += "SCFTolerance = 5e-5\n"

        # Periodic system support: LatticeVectors + KPoints
        # _CRYSTAL_DEFAULT_PD: fallback if the UI sends no periodicDimensions for a known crystal.
        # User's explicit config["periodicDimensions"] always takes precedence so they can simulate
        # e.g. a 1D Si waveguide (PeriodicDimensions=1) instead of bulk (3).
        _CRYSTAL_DEFAULT_PD = {"Si": 3, "Al2O3": 3}
        _user_pd = config.get("periodicDimensions")
        if _user_pd is not None:
            periodic_dims = int(_user_pd)
        else:
            periodic_dims = _CRYSTAL_DEFAULT_PD.get(molecule, 0)
        if periodic_dims > 0:
            inp += f"PeriodicDimensions = {periodic_dims}\n"
            # Mixed periodicity (1D or 2D periodic + remaining finite directions with sphere bc)
            # requires ExperimentalFeatures = yes in Octopus ≥ 13
            if periodic_dims < dimensions:
                inp += "ExperimentalFeatures = yes\n"
            # Use provided latticeVectors or built-in defaults
            lv = config.get("latticeVectors")
            if not lv:
                # Crystal-specific 3D primitive vectors (only for pd==3)
                if periodic_dims == 3 and molecule == "Si":
                    lv = [[0.0, 5.132, 5.132], [5.132, 0.0, 5.132], [5.132, 5.132, 0.0]]
                elif periodic_dims == 3 and molecule == "Al2O3":
                    lv = [[5.128, -2.564, 0.0], [0.0, 4.440, 0.0], [0.0, 0.0, 13.900]]
                elif periodic_dims == 2 and molecule == "Al2O3":
                    # Al₂O₃ (0001) slab: in-plane vectors from the hexagonal cell
                    lv = [[5.128, -2.564, 0.0], [0.0, 4.440, 0.0]]
                elif periodic_dims == 2 and molecule == "Si":
                    # Si(001) surface: a/√2 ≈ 7.255 Bohr in-plane, user can override via latticeA/B
                    a = float(config.get("latticeA", 7.255))
                    b = float(config.get("latticeB", a))
                    lv = [[a, 0.0, 0.0], [0.0, b, 0.0]]
                elif periodic_dims == 1:
                    _crystal_a1d = {"Si": 10.263, "Al2O3": 5.128}
                    a_def = _crystal_a1d.get(molecule, 10.0)
                    lv = [[float(config.get("latticeA", a_def)), 0.0, 0.0]]
                elif periodic_dims == 2:
                    a = float(config.get("latticeA", 10.0))
                    b = float(config.get("latticeB", 10.0))
                    lv = [[a, 0.0, 0.0], [0.0, b, 0.0]]
                else:
                    a = float(config.get("latticeA", 10.0))
                    b = float(config.get("latticeB", a))
                    c = float(config.get("latticeC", a))
                    lv = [[a, 0.0, 0.0], [0.0, b, 0.0], [0.0, 0.0, c]]
            inp += "%LatticeVectors\n"
            for v in lv:
                inp += f"  {v[0]} | {v[1]} | {v[2]}\n"
            inp += "%\n"
            kgrid = config.get("kpointsGrid", "2 2 2")
            k_parts = kgrid.replace(',', ' ').split()
            # For mixed-periodicity systems, only fill k-points along periodic axes;
            # set k=1 for all finite (non-periodic) directions to avoid spurious bands.
            if periodic_dims == 1:
                k_parts = [k_parts[0], "1", "1"]
            elif periodic_dims == 2:
                k_parts = [k_parts[0], k_parts[1] if len(k_parts) > 1 else "2", "1"]
            inp += "%KPointsGrid\n"
            inp += f"  {'  |  '.join(k_parts[:3])}\n"
            inp += "%\n"
            inp += "\n"

        # Optional: XC functional, mixing, spin from config
        xc_functional = config.get("xcFunctional", "lda_x+lda_c_pz")
        mixing_scheme = config.get("mixingScheme", "broyden")
        spin = config.get("spinComponents", "unpolarized")
        extra_states_3d = int(config.get("octopusExtraStates", config.get("extraStates", 4)))

        # OEP/HF functionals use special Octopus variables (not libxc strings)
        _OEP_MAP = {
            "hartree_fock": ("hf_x", ""),
            "oep_kli":      ("lda_x", "OEPLevel = kli"),
            "oep_slater":   ("lda_x", "OEPLevel = slater"),
        }
        if xc_functional in _OEP_MAP:
            _xc_mapped, _oep_line = _OEP_MAP[xc_functional]
            inp += f"XCFunctional = {_xc_mapped}\n"
            if _oep_line:
                inp += f"{_oep_line}\n"
        else:
            inp += f"XCFunctional = {xc_functional}\n"
        inp += f"MixingScheme = {mixing_scheme}\n"
        if spin != "unpolarized":
            inp += f"SpinComponents = {spin}\n"

        # Non-uniform / curvilinear mesh options
        deriv_order = int(config.get("derivativesOrder", 4))
        if deriv_order != 4:
            inp += f"DerivativesOrder = {deriv_order}\n"
        curv_method = config.get("curvMethod", "uniform")
        if curv_method == "gygi":
            inp += "CurvMethod = gygi\n"
            inp += f"CurvGygiA = {float(config.get('curvGygiAlpha', 2.0))}\n"
        if config.get("doubleGrid", False):
            inp += "DoubleGrid = yes\n"

        if is_td:
            # TDDFT Delta-kick + output
            # Octopus 16+: use TDDeltaStrength/TDDeltaKickTime instead of
            # the deprecated %TDFunctions/%TDExternalFields tdf_delta syntax
            steps = config.get("octopusTdSteps", config.get("tdSteps", config.get("TDMaxSteps", 200)))
            td_dt = config.get("octopusTdTimeStep", config.get("TDTimeStep", 0.05))
            propagator = config.get("octopusPropagator", "aetrs")
            excitation_type = config.get("tdExcitationType", "delta")
            polarization = int(config.get("tdPolarization", 1))  # 1=x, 2=y, 3=z
            amplitude = float(config.get("tdFieldAmplitude", 0.01))

            inp += f"TDPropagator = {propagator}\n"
            inp += f"TDMaxSteps = {steps}\n"
            inp += f"TDTimeStep = {td_dt}\n"

            if excitation_type == "delta":
                # Broadband delta-kick (best for optical spectra)
                inp += f"TDDeltaStrength = {amplitude}\n"
                inp += "TDDeltaKickTime = 0.0\n"
                inp += f"TDPolarizationDirection = {polarization}\n\n"
                
                # Free electron probe alongside delta kick: needs its own %TDExternalFields block
                if config.get("feProbeEnabled", False):
                    fe_v   = float(config.get("feProbeVelocity", 0.5))
                    fe_y0  = float(config.get("feProbeY0", 2.0))
                    fe_z0  = float(config.get("feProbeZ0", 0.0))
                    fe_q   = float(config.get("feProbeCharge", -1.0))
                    c_au   = 137.036
                    v_au   = fe_v * c_au
                    expr = f"{fe_q}/sqrt((x - {v_au:.4f}*t)^2 + {fe_y0}^2 + {fe_z0}^2 + 0.01)"
                    inp += "# ── Free Electron Probe potential ──\n"
                    inp += "%TDExternalFields\n"
                    inp += f"  scalar_potential | 1 | 0 | 0 | 1.0 | \"fe_probe\"\n"
                    inp += "%\n"
                    inp += "%TDFunctions\n"
                    inp += f"  \"fe_probe\" | tdf_from_expr | \"{expr}\"\n"
                    inp += "%\n\n"
            else:
                # External field via %TDExternalFields + %TDFunctions
                pol_vec = {1: "1 | 0 | 0", 2: "0 | 1 | 0", 3: "0 | 0 | 1"}[polarization]
                # Build the external fields block — may include both signal and probe
                ext_fields = [f"  electric_field | {pol_vec} | {amplitude} | \"td_pulse\""]
                td_funcs = []
                if excitation_type == "gaussian":
                    sigma = float(config.get("tdGaussianSigma", 5.0))
                    t0    = float(config.get("tdGaussianT0",    10.0))
                    td_funcs.append(f"  \"td_pulse\" | tdf_gaussian | {sigma} | {t0} | {sigma}")
                elif excitation_type == "sin":
                    freq = float(config.get("tdSinFrequency", 0.057))
                    td_funcs.append(f"  \"td_pulse\" | tdf_from_expr | \"sin({freq}*t)\"")
                elif excitation_type == "continuous_wave":
                    freq = float(config.get("tdSinFrequency", 0.057))
                    td_funcs.append(f"  \"td_pulse\" | tdf_from_expr | \"cos({freq}*t)\"")

                # Append probe if enabled — combined into same %TDExternalFields block
                if config.get("feProbeEnabled", False):
                    fe_v   = float(config.get("feProbeVelocity", 0.5))
                    fe_y0  = float(config.get("feProbeY0", 2.0))
                    fe_z0  = float(config.get("feProbeZ0", 0.0))
                    fe_q   = float(config.get("feProbeCharge", -1.0))
                    c_au   = 137.036
                    v_au   = fe_v * c_au
                    expr = f"{fe_q}/sqrt((x - {v_au:.4f}*t)^2 + {fe_y0}^2 + {fe_z0}^2 + 0.01)"
                    ext_fields.append(f"  scalar_potential | 1 | 0 | 0 | 1.0 | \"fe_probe\"")
                    td_funcs.append(f"  \"fe_probe\" | tdf_from_expr | \"{expr}\"")

                inp += "%TDExternalFields\n"
                inp += "\n".join(ext_fields) + "\n"
                inp += "%\n"
                inp += "%TDFunctions\n"
                inp += "\n".join(td_funcs) + "\n"
                inp += "%\n\n"

            inp += "%TDOutput\n"
            inp += "  multipoles\n"
            inp += "  energy\n"
            inp += "%\n"
        else:
            # Ground State: output BOTH axis slices (*.y=0,z=0) AND full 3D cube files
            inp += f"ExtraStates = {extra_states_3d}\n"
            inp += "%Output\n"
            inp += "  wfs\n"
            inp += "  density\n"
            inp += "  potential\n"   # v0 + vh + vxc + vks files (all components)
            inp += "  eigenvalues\n"
            inp += "  dos\n"
            inp += "  elf\n"         # Electron Localization Function
            if periodic_dims > 0:
                inp += "  stress\n"  # Stress tensor (periodic systems only)
            inp += "%\n"
            # axis_x: 1D line-scan files (fast, for wavefunction 1D plots)
            # cube: full 3D volumetric data (for proper 2D heatmaps and 3D isosurfaces)
            inp += "OutputFormat = cube + axis_x\n"

        return inp

    # Original 1D local physics configuration behavior
    potential_type = config.get("potentialType", "Harmonic")
    grid_spacing = config.get("octopusSpacing", config.get("gridSpacing", 0.1))
    spatial_extent = config.get("octopusRadius", config.get("spatialRange", 10.0) / 2.0)
    dimensions = 1 if config.get("octopusDimensions", config.get("dimensionality", "1D")) == "1D" else (2 if config.get("octopusDimensions", config.get("dimensionality")) == "2D" else 3)
    extra_states = max(0, config.get("octopusExtraStates", config.get("extraStates", 3)))

    if potential_type == "Harmonic":
        formula = '"0.5*x^2"'
    elif potential_type == "FiniteWell":
        depth = abs(config.get("potentialStrength", 10.0))
        hw = config.get("wellWidth", 1.0) / 2.0
        formula = f'"-{depth}*step({hw}-abs(x))"'
    elif potential_type == "InfiniteWell":
        hw = config.get("wellWidth", 1.0) / 2.0
        formula = f'"-1000*step({hw}-abs(x))"'
    elif potential_type == "Coulomb":
        Z = abs(config.get("potentialStrength", 1.0))
        formula = f'"-{Z}/sqrt(x^2+0.01)"'  # Regularized Coulomb
    else:
        formula = '"0"'

    return octopus_inp_template.render(
        dimensions=dimensions,
        grid_spacing=grid_spacing,
        radius=spatial_extent,
        extra_states=extra_states,
        potential_formula=formula,
    )


def parse_octopus_info(info_path: str) -> dict:
    """Parse Octopus static/info file for eigenvalues and energies."""
    result = {"eigenvalues": [], "eigenvalue_entries": [], "total_energy": None, "converged": False, "scf_iterations": 0}

    if not os.path.exists(info_path):
        return result

    with open(info_path, "r") as f:
        content = f.read()

    # Check convergence
    m = re.search(r"SCF converged in\s+(\d+)\s+iterations", content)
    if m:
        result["converged"] = True
        result["scf_iterations"] = int(m.group(1))

    # Parse eigenvalues block - handle scientific notation and flexible whitespace
    # Octopus 16.3 might use different header formats
    header_pattern = re.compile(r"#st\s+Spin\s+Eigenvalue.*Occupation")
    # Also handle simpler headers or variations
    simple_header = re.compile(r"State\s+Energy\s+Occupation")
    alternate_header = re.compile(r"Eigenvalues\s+\[H\]")
    
    lines = content.split("\n")
    in_ev_block = False
    for line in lines:
        if header_pattern.search(line) or simple_header.search(line) or alternate_header.search(line):
            in_ev_block = True
            continue
        if in_ev_block:
            stripped = line.strip()
            # Stop if we hit Energy block or an empty line
            if not stripped or stripped.startswith("Energy") or stripped.startswith("---"):
                break
            parts = stripped.split()
            # Format: #st Spin Eigenvalue Occupation
            if len(parts) >= 3:
                try:
                    val_match = re.findall(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?", line)
                    if val_match:
                        ev = float(val_match[0])
                        result["eigenvalues"].append(ev)
                        # Try to parse occupation (last numeric column)
                        try:
                            occ = float(val_match[-1]) if len(val_match) >= 2 else 2.0
                        except (ValueError, IndexError):
                            occ = 2.0
                        state_idx = int(parts[0]) if parts[0].isdigit() else len(result["eigenvalue_entries"]) + 1
                        spin_label = parts[1] if len(parts) > 2 and not parts[1].replace('.','').replace('-','').replace('e','').replace('E','').replace('+','').isdigit() else "up"
                        result["eigenvalue_entries"].append({
                            "state": state_idx,
                            "spin": spin_label,
                            "eigenvalue_hartree": ev,
                            "occupation": occ,
                        })
                except (ValueError, IndexError):
                    pass

    # Parse total energy
    m = re.search(r"Total\s+=\s+([-\d.]+)", content)
    if m:
        result["total_energy"] = float(m.group(1))

    result["engine"] = "octopus-14.0"
    return result

def get_atom_positions(molecule: str, dimensions: int = 3, custom_atoms: list = None) -> list:
    """Return list of {symbol, x, y, z} for frontend geometry visualization."""
    import re as _re
    if custom_atoms:
        return [{"symbol": a["symbol"], "x": float(a.get("x", 0)),
                 "y": float(a.get("y", 0)), "z": float(a.get("z", 0))} for a in custom_atoms]
    lines = (MOLECULES_2D if dimensions == 2 else MOLECULES).get(molecule, [])
    atoms = []
    for line in lines:
        parts = [p.strip().strip("'") for p in line.split("|")]
        if len(parts) < 2:
            continue
        try:
            sym = parts[0]
            coords = [float(p) for p in parts[1:4]]
            while len(coords) < 3:
                coords.append(0.0)
            atoms.append({"symbol": sym, "x": coords[0], "y": coords[1], "z": coords[2]})
        except ValueError:
            pass
    return atoms

def parse_octopus_wfs_1d(static_dir: str) -> dict:
    """Parse 1D text files (vks and wf-st) into arrays."""
    import glob
    result = {"x_grid": [], "potential": [], "wavefunctions": []}
    if not os.path.exists(static_dir):
        return result
        
    # Read potential
    vks_path = os.path.join(static_dir, "vks.y=0,z=0")
    if os.path.exists(vks_path):
        with open(vks_path, "r") as f:
            for line in f:
                if line.startswith("#"): continue
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        x = float(parts[0])
                        v = float(parts[1])
                        result["x_grid"].append(x)
                        result["potential"].append(v)
                    except ValueError:
                        pass

    # Read individual potential components (v0=external, vh=Hartree, vxc=XC)
    for _key, _fname in [("v0", "v0.y=0,z=0"), ("vh", "vh.y=0,z=0"), ("vxc", "vxc.y=0,z=0")]:
        _fpath = os.path.join(static_dir, _fname)
        if os.path.exists(_fpath):
            _data: list = []
            with open(_fpath) as _fh:
                for _line in _fh:
                    if _line.startswith("#"):
                        continue
                    _parts = _line.split()
                    if len(_parts) >= 2:
                        try:
                            _data.append(float(_parts[1]))
                        except ValueError:
                            pass
            if _data:
                result[_key] = _data
    
    # Read wavefunctions
    wf_files = sorted(glob.glob(os.path.join(static_dir, "wf-st*.y=0,z=0")))
    for wf_file in wf_files:
        wf_data = []
        with open(wf_file, "r") as f:
            for line in f:
                if line.startswith("#"): continue
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        # parts[1] is Re, parts[2] is Im (usually 0 for bound state string)
                        val = float(parts[1])
                        wf_data.append(val)
                    except ValueError:
                        pass
        if wf_data:
            result["wavefunctions"].append(wf_data)

    # Read electron density 1D slice
    density_path = os.path.join(static_dir, "density.y=0,z=0")
    if os.path.exists(density_path):
        density_data = []
        with open(density_path, "r") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        density_data.append(float(parts[1]))
                    except ValueError:
                        pass
        if density_data:
            result["density"] = density_data

    return result

def parse_octopus_cross_section(work_dir: str) -> dict:
    """Parse the cross_section_vector file (in work_dir root) for optical spectrum.
    
    oct-propagation_spectrum writes cross_section_vector to the working directory
    root (not inside td.general/). Format: 5 columns per row (may wrap over two
    physical lines):
      col 0: energy (Hartree)  col 1: Im(alpha_xx)  col 2: Re(alpha_xx)
      col 3: Im(alpha_xy)      col 4: Re(alpha_xy)
    Absorption cross section sigma ~ Im(alpha), col 1.
    """
    HARTREE_TO_EV = 27.2114
    # File is written to root work_dir, NOT inside td.general/
    cs_path = os.path.join(work_dir, "cross_section_vector")
    result = {"energy_ev": [], "cross_section": []}
    
    if not os.path.exists(cs_path):
        return result
    
    import re
    with open(cs_path, "r") as f:
        content = f.read()
    # Extract all floating point numbers (both uppercase E and lowercase e), ignoring comment lines
    nums = re.findall(r'[-+]?\d+\.\d+[eE][+-]\d+', content)
    # 5 numbers per data row: omega | Im(alpha_xx) | Im(alpha_yy) | Im(alpha_zz) | sigma_iso
    # For a z-axis kick, Im(alpha_xx)=Im(alpha_yy)≈0; the physical signal is in Im(alpha_zz).
    # Use the sum of all diagonal components so any kick direction is captured.
    for i in range(0, len(nums) - 4, 5):
        try:
            energy_ha = float(nums[i])
            # Sum the three diagonal Im(alpha) components → total absorption for any kick direction
            im_alpha_xx = float(nums[i + 1])
            im_alpha_yy = float(nums[i + 2])
            im_alpha_zz = float(nums[i + 3])
            im_alpha = im_alpha_xx + im_alpha_yy + im_alpha_zz
            energy_ev = energy_ha * HARTREE_TO_EV
            if energy_ev > 0.01:  # skip E~0 artefact
                result["energy_ev"].append(round(energy_ev, 6))
                result["cross_section"].append(round(im_alpha, 10))
        except (ValueError, IndexError):
            pass
    return result


def parse_octopus_convergence(static_dir: str) -> dict:
    """Parse static/convergence for SCF energy diff per iteration."""
    path = os.path.join(static_dir, "convergence")
    result: dict = {"iterations": [], "energy_diff": []}
    if not os.path.exists(path):
        return result
    try:
        with open(path, "r") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        result["iterations"].append(int(float(parts[0])))
                        result["energy_diff"].append(abs(float(parts[2])))
                    except ValueError:
                        pass
    except Exception as e:
        print(f"[WARN] parse_octopus_convergence: {e}")
    return result


def parse_octopus_dos(static_dir: str) -> dict:
    """Parse static/total-dos.dat (or equivalent) for Density of States."""
    import glob as _glob
    HARTREE_TO_EV = 27.2114
    result: dict = {"energy_ev": [], "dos": []}
    candidates = _glob.glob(os.path.join(static_dir, "*dos*"))
    if not candidates:
        return result
    dos_path = sorted(candidates)[0]
    try:
        with open(dos_path, "r") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        result["energy_ev"].append(float(parts[0]) * HARTREE_TO_EV)
                        result["dos"].append(float(parts[1]))
                    except ValueError:
                        pass
    except Exception as e:
        print(f"[WARN] parse_octopus_dos: {e}")
    return result


def parse_td_dipole(td_dir: str) -> dict:
    """Parse td.general/multipoles for dipole moment vs time.
    
    Octopus multipoles file format (lmax=1, 3D):
      col 0: iter  col 1: time  col 2: electronic_charge  col 3: <x>  col 4: <y>  col 5: <z>
    """
    path = os.path.join(td_dir, "multipoles")
    result: dict = {"time": [], "dipole_x": [], "dipole_y": [], "dipole_z": []}
    if not os.path.exists(path):
        return result
    try:
        with open(path, "r") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.split()
                # 6 columns: iter | time | charge | <x> | <y> | <z>
                if len(parts) >= 6:
                    try:
                        result["time"].append(float(parts[1]))
                        result["dipole_x"].append(float(parts[3]))  # <x>
                        result["dipole_y"].append(float(parts[4]))  # <y>
                        result["dipole_z"].append(float(parts[5]))  # <z>
                    except ValueError:
                        pass
    except Exception as e:
        print(f"[WARN] parse_td_dipole: {e}")
    return result


async def run_octopus_calculation(config: dict) -> dict:
    """Run an Octopus calculation and return parsed results."""
    print(f"[DEBUG] run_octopus_calculation starting...")
    work_dir = tempfile.mkdtemp(prefix="octopus_")
    engine_mode = config.get("engineMode", "local1D")
    print(f"[DEBUG] engineMode from config = {repr(engine_mode)} | expected: 'octopus3D'")
    calc_mode = config.get("calcMode", "gs")
    
    try:
        # 1. ALWAYS Run Ground State First
        inp_content_gs = generate_inp(config, is_td=False)
        print(f"[DEBUG] Generated Octopus Inp (GS):\n{inp_content_gs}")
        with open(os.path.join(work_dir, "inp"), "w") as f:
            f.write(inp_content_gs)

        # Run Octopus GS
        process_gs = await asyncio.create_subprocess_exec(
            "octopus",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir
        )
        stdout_gs, stderr_gs = await asyncio.wait_for(
            process_gs.communicate(), timeout=300
        )

        if process_gs.returncode != 0:
            err_msg = stderr_gs.decode("utf-8", errors="replace")
            print(f"[ERROR] Octopus GS failed Code {process_gs.returncode}: {err_msg}")
            # Still return partial data if info file exists, otherwise error
            info_path = os.path.join(work_dir, "static", "info")
            if not os.path.exists(info_path):
                return {"status": "error", "message": f"Octopus GS failed: {err_msg}", "engine": "octopus-14.0"}

        stdout_text = stdout_gs.decode("utf-8", errors="replace")
        stderr_text = stderr_gs.decode("utf-8", errors="replace")
        
        # Parse GS info
        info_path = os.path.join(work_dir, "static", "info")
        parsed_gs = parse_octopus_info(info_path)
        
        # Base JSON Response structure
        response_data = {
            "status": "success" if (parsed_gs["converged"] or process_gs.returncode == 0) else "warning",
            "eigenvalues": parsed_gs["eigenvalues"],
            "total_energy": parsed_gs["total_energy"],
            "converged": parsed_gs["converged"],
            "scf_iterations": parsed_gs["scf_iterations"],
            "engine": "octopus-14.0",
            "stdout_tail": stdout_text[-1000:] if stdout_text else "",
            "stderr_tail": stderr_text[-1000:] if stderr_text else "",
            "returncode": process_gs.returncode,
        }

        if engine_mode == "octopus3D":
            # Populate molecular specific fields from GS
            evals = parsed_gs["eigenvalues"]
            homo_energy = None
            lumo_energy = None

            if parsed_gs.get("eigenvalue_entries"):
                occupied = [e["eigenvalue_hartree"] for e in parsed_gs["eigenvalue_entries"] if e.get("occupation", 0) > 0.5]
                unoccupied = [e["eigenvalue_hartree"] for e in parsed_gs["eigenvalue_entries"] if e.get("occupation", 0) <= 0.5]
                homo_energy = max(occupied) if occupied else None
                lumo_energy = min(unoccupied) if unoccupied else None
            elif evals:
                # Fallback: negative eigenvalues = occupied, positive = virtual
                negative_evals = [e for e in evals if e < 0]
                positive_evals = [e for e in evals if e >= 0]
                homo_energy = max(negative_evals) if negative_evals else None
                lumo_energy = min(positive_evals) if positive_evals else None

            # Persist results to workspace/output for host mapping if needed
            output_dir = "/workspace/output"
            os.makedirs(output_dir, exist_ok=True)
            # Copy static files if they exist
            static_dir = os.path.join(work_dir, "static")
            if os.path.exists(static_dir):
                for item in os.listdir(static_dir):
                    s = os.path.join(static_dir, item)
                    d = os.path.join(output_dir, item)
                    if os.path.isfile(s):
                        shutil.copy2(s, d)

            # Parse 1D slice wavefunctions (produced by OutputFormat = axis_x)
            wfs_data = parse_octopus_wfs_1d(static_dir)
            if wfs_data["x_grid"]:
                response_data["x_grid"] = wfs_data["x_grid"]
                response_data["potential"] = wfs_data["potential"]
                response_data["wavefunctions"] = wfs_data["wavefunctions"]
            if wfs_data.get("density"):
                response_data["density_1d"] = wfs_data["density"]
            # Potential breakdown: v0=external, vh=Hartree, vxc=XC, vks=total KS
            _pc = {k: wfs_data[k] for k in ("v0", "vh", "vxc") if wfs_data.get(k)}
            if _pc:
                _pc["vks"] = wfs_data.get("potential", [])
                response_data["potential_components"] = _pc

            # Convert eigenvalues Hartree → eV for frontend display
            HARTREE_TO_EV = 27.2114
            evals_eV = [e * HARTREE_TO_EV for e in evals]
            homo_eV = homo_energy * HARTREE_TO_EV if homo_energy is not None else None
            lumo_eV = lumo_energy * HARTREE_TO_EV if lumo_energy is not None else None

            # Proper HOMO/LUMO from parsed_gs occupation numbers
            occupied_eig = [
                e["eigenvalue_hartree"] * HARTREE_TO_EV
                for e in parsed_gs.get("eigenvalue_entries", [])
                if e.get("occupation", 0) > 0.5
            ]
            unoccupied_eig = [
                e["eigenvalue_hartree"] * HARTREE_TO_EV
                for e in parsed_gs.get("eigenvalue_entries", [])
                if e.get("occupation", 0) <= 0.5
            ]
            if occupied_eig:
                homo_eV = max(occupied_eig)
            if unoccupied_eig:
                lumo_eV = min(unoccupied_eig)

            # Resolve molecule name (can be string or dict with name key)
            _mol_raw = config.get("octopusMolecule", config.get("molecule", config.get("moleculeName", "H2")))
            _mol_name = _mol_raw.get("name", "H2") if isinstance(_mol_raw, dict) else _mol_raw

            # Atom positions for frontend geometry visualization
            _custom_atoms = config.get("customAtoms") or config.get("atoms")
            _dims = int(config.get("octopusDimensions", config.get("dimensionality", 3)) if config.get("octopusDimensions", config.get("dimensionality", "3D")) not in ("1D", "2D", "3D") else (1 if config.get("octopusDimensions","3D")=="1D" else (2 if config.get("octopusDimensions","3D")=="2D" else 3)))
            # Read box radius using the same priority logic as generate_inp (no halving when octopusRadius is explicit)
            if "octopusRadius" in config:
                _box_radius = float(config["octopusRadius"])
            elif "spatialRange" in config:
                _box_radius = float(config["spatialRange"]) / 2.0
            else:
                _box_radius = float(config.get("radius", 10.0))

            response_data["molecular"] = {
                "moleculeName": _mol_name,
                "calcMode": calc_mode,
                "energy_levels": evals_eV,
                "homo_energy": homo_eV,
                "lumo_energy": lumo_eV,
                "total_energy_hartree": parsed_gs.get("total_energy"),
                "scf_iterations": parsed_gs.get("scf_iterations", 0),
                "converged": parsed_gs.get("converged", False),
                "atom_positions": get_atom_positions(_mol_name, _dims, _custom_atoms),
                "box_radius": _box_radius,
            }
            print(f"[DEBUG] response_data['molecular'] set: {response_data.get('molecular')}")
            response_data["molecular"]["convergence_data"] = parse_octopus_convergence(static_dir)
            response_data["molecular"]["dos_data"] = parse_octopus_dos(static_dir)

            # 2. If TD mode is requested, run TD propagation now that GS is done
            if calc_mode == "td" and parsed_gs["converged"]:
                print(f"[DEBUG] TD mode requested: calcMode={calc_mode}, converged={parsed_gs['converged']}")
                
                # **KEY FIX**: Don't delete restart. Instead, generate TD inp and let Octopus
                # use the restart files for initialization. Just need to continue from where GS left off.
                # The restart/ folder contains the converged density matrix, which TD needs.
                print(f"[DEBUG] Keeping restart directory for TD initialization")
                
                # Generate and write TD input
                inp_content_td = generate_inp(config, is_td=True)
                inp_path = os.path.join(work_dir, "inp")
                with open(inp_path, "w") as f:
                    f.write(inp_content_td)
                print(f"[DEBUG] TD inp file written, size={len(inp_content_td)} bytes")
                
                # Run TD octopus - it will use the restart files from GS
                print(f"[DEBUG] Starting TD octopus process in {work_dir}")
                process_td = await asyncio.create_subprocess_exec(
                    "octopus",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=work_dir
                )
                print(f"[DEBUG] TD octopus process started, PID={process_td.pid}")
                
                # TD can take longer (allow 10m just in case)
                try:
                    stdout_td, stderr_td = await asyncio.wait_for(
                        process_td.communicate(), timeout=3600
                    )
                    print(f"[DEBUG] TD octopus completed, returncode={process_td.returncode}")
                except asyncio.TimeoutError:
                    print(f"[ERROR] TD octopus timed out after 3600s")
                    process_td.kill()
                    raise
                
                # Log TD output
                stdout_td_str = stdout_td.decode("utf-8", errors="replace")
                stderr_td_str = stderr_td.decode("utf-8", errors="replace")
                
                print(f"[DEBUG] TD stdout length={len(stdout_td_str)}, stderr length={len(stderr_td_str)}")
                
                if stderr_td_str:
                    print(f"[DEBUG] TD stderr (last 500 chars):\n{stderr_td_str[-500:]}")
                
                if process_td.returncode != 0:
                    print(f"[ERROR] TD octopus failed with return code {process_td.returncode}")
                    if stdout_td_str:
                        print(f"[ERROR] TD stdout (last 800):\n{stdout_td_str[-800:]}")
                
                # Check if TD created output directories
                td_dir = os.path.join(work_dir, "td.general")
                print(f"[DEBUG] Checking for td.general directory: {td_dir}")
                if os.path.exists(td_dir):
                    td_files = os.listdir(td_dir)
                    print(f"[DEBUG] ✓ td.general created with {len(td_files)} files")
                    if td_files:
                        print(f"[DEBUG] Files in td.general: {td_files[:10]}")
                else:
                    print(f"[ERROR] ✗ td.general directory NOT created by TD octopus")
                
                stdout_text += "\n--- TD Run ---\n" + stdout_td_str[-500:]
                response_data["stdout_tail"] = stdout_text[-1500:]
                response_data["molecular"]["td_executed"] = process_td.returncode == 0
                
                # Now run oct-propagation_spectrum to get the cross section
                if os.path.exists(td_dir):
                    print(f"[DEBUG] Starting oct-propagation_spectrum in {work_dir}")
                    process_spec = await asyncio.create_subprocess_exec(
                        "oct-propagation_spectrum",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=work_dir
                    )
                    
                    try:
                        stdout_spec, stderr_spec = await asyncio.wait_for(
                            process_spec.communicate(), timeout=600
                        )
                        print(f"[DEBUG] oct-propagation_spectrum completed, returncode={process_spec.returncode}")
                    except asyncio.TimeoutError:
                        print(f"[ERROR] oct-propagation_spectrum timed out")
                        process_spec.kill()
                    
                    stderr_spec_str = stderr_spec.decode("utf-8", errors="replace")
                    if stderr_spec_str:
                        print(f"[DEBUG] oct-propagation_spectrum stderr (last 300 chars):\n{stderr_spec_str[-300:]}")
                    
                    # Check for cross_section_vector (written to work_dir root, not td.general/)
                    cs_path = os.path.join(work_dir, "cross_section_vector")
                    print(f"[DEBUG] Checking for cross_section_vector at {cs_path}")
                    if os.path.exists(cs_path):
                        cs_size = os.path.getsize(cs_path)
                        print(f"[DEBUG] ✓ cross_section_vector found, size={cs_size} bytes")
                    else:
                        print(f"[ERROR] ✗ cross_section_vector NOT found")
                        # Also check td.general/ in case of version differences
                        td_cs = os.path.join(td_dir, "cross_section_vector")
                        if os.path.exists(td_cs):
                            print(f"[DEBUG] Found in td.general/ instead: {td_cs}")
                        root_files = os.listdir(work_dir)
                        print(f"[DEBUG] Work dir files: {[f for f in root_files if 'cross' in f.lower() or 'spectrum' in f.lower()]}")
                    
                    spectrum_data = parse_octopus_cross_section(work_dir)
                    print(f"[DEBUG] parse_octopus_cross_section: energy_ev={len(spectrum_data.get('energy_ev', []))} points, cs={len(spectrum_data.get('cross_section', []))} points")
                    response_data["molecular"]["optical_spectrum"] = spectrum_data
                    # Parse dipole time series from td.general/multipoles
                    td_dipole_data = parse_td_dipole(td_dir)
                    print(f"[DEBUG] parse_td_dipole: {len(td_dipole_data.get('time', []))} steps")
                    response_data["molecular"]["td_dipole"] = td_dipole_data

                    # Persist TD output to /workspace/output for host access
                    output_dir = "/workspace/output"
                    os.makedirs(output_dir, exist_ok=True)
                    # Copy td.general/ directory
                    td_out = os.path.join(output_dir, "td.general")
                    if os.path.exists(td_out):
                        shutil.rmtree(td_out, ignore_errors=True)
                    shutil.copytree(td_dir, td_out)
                    print(f"[DEBUG] ✓ Copied td.general/ to {td_out}")
                    # Copy cross_section_vector if at root level
                    cs_path = os.path.join(work_dir, "cross_section_vector")
                    if os.path.exists(cs_path):
                        shutil.copy2(cs_path, os.path.join(output_dir, "cross_section_vector"))
                        print(f"[DEBUG] ✓ Copied cross_section_vector to {output_dir}")
                else:
                    print(f"[DEBUG] Skipping oct-propagation_spectrum because td.general not found")
                    response_data["molecular"]["optical_spectrum"] = {"energy_ev": [], "cross_section": []}

        else:
            # 1D Local Physics mode outputs
            static_dir = os.path.join(work_dir, "static")
            wfs_data = parse_octopus_wfs_1d(static_dir)
            response_data["x_grid"] = wfs_data["x_grid"]
            response_data["potential"] = wfs_data["potential"]
            response_data["wavefunctions"] = wfs_data["wavefunctions"]

        return response_data

    except asyncio.TimeoutError:
        return {"status": "error", "message": "Octopus computation timed out"}
    except Exception as e:
        print(f"[ERROR] solve_handler: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        # Keep work_dir for a bit if debugging is needed, but for now cleanup
        # shutil.rmtree(work_dir, ignore_errors=True)
        pass


# ─── REST endpoints ───────────────────────────────────────────────

async def health_handler(request: Request):
    """Health check endpoint."""
    return JSONResponse({"status": "ok", "engine": "octopus-14.0"})


async def solve_handler(request: Request):
    """REST endpoint compatible with physics_engine.ts pipeline."""
    print(f"[DEBUG] solve_handler received request")
    try:
        config = await request.json()
        print(f"[DEBUG] solve_handler parsed config: {config}")
    except Exception as e:
        print(f"[ERROR] solve_handler failed to parse JSON: {e}")
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)

    print(f"[DEBUG] solve_handler calling run_octopus_calculation")
    result = await run_octopus_calculation(config)
    print(f"[DEBUG] solve_handler received result: {result.get('status')}")

    # Format response to match the existing PhysicsResult interface
    eigenvalues = result.get("eigenvalues", [])
    x_grid = result.get("x_grid", [])
    potential_V = result.get("potential", [])
    wfs = result.get("wavefunctions", [])
    
    # Format wavefunctions for frontend (assuming non-relativistic / single component for now)
    formatted_wfs = []
    for w in wfs:
        formatted_wfs.append({
            "psi_up": w,
            "psi_down": [0.0] * len(w)
        })

    # If no wfs parsed, fallback to empty arrays
    if not formatted_wfs:
        formatted_wfs = [{"psi_up": [], "psi_down": []} for _ in eigenvalues]

    response = {
        "status": result.get("status", "error"),
        "eigenvalues": eigenvalues,
        "total_energy": result.get("total_energy"),
        "converged": result.get("converged", False),
        "scf_iterations": result.get("scf_iterations", 0),
        "engine": result.get("engine", "octopus-14.0"),
        "problemType": "molecular" if result.get("molecular") else config.get("problemType", "boundstate"),
        "matrix_info": {
            "size": len(x_grid) if x_grid else len(eigenvalues),
            "non_zeros": 0,
            "isHermitian": True,
        },
        "x_grid": x_grid,
        "potential_V": potential_V,
        "wavefunctions": formatted_wfs,
        "molecular": result.get("molecular"),
        "density_1d": result.get("density_1d", []),
        "potential_components": result.get("potential_components"),
        "message": result.get("stderr_tail", str(result.get("message", ""))),
    }
    return JSONResponse(sanitize_floats(response))


# ─── MCP tool handlers (kept for MCP SDK clients) ─────────────────

@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "run_octopus":
        result = await run_octopus_calculation(arguments)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    if name == "parse_results":
        run_dir = arguments.get("run_dir", "/workspace/output")
        static_dir = os.path.join(run_dir)  # files were copied flat to output_dir
        info_path = os.path.join(static_dir, "info")
        out: dict = {"run_dir": run_dir}
        if os.path.exists(info_path):
            out["info"] = parse_octopus_info(info_path)
        wfs = parse_octopus_wfs_1d(static_dir)
        out["available_states"] = len(wfs.get("wavefunctions", []))
        out["x_grid"] = wfs.get("x_grid", [])
        out["potential"] = wfs.get("potential", [])
        out["wavefunctions"] = wfs.get("wavefunctions", [])
        return [types.TextContent(type="text", text=json.dumps(out, indent=2))]
    return [types.TextContent(type="text", text="Unknown tool.")]

@mcp_server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="run_octopus",
            description="Run an Octopus DFT calculation with the given physics config.",
            inputSchema={
                "type": "object",
                "properties": {
                    "potentialType": {"type": "string"},
                    "gridSpacing": {"type": "number"},
                    "spatialRange": {"type": "number"},
                    "dimensionality": {"type": "string"},
                    "potentialStrength": {"type": "number"},
                    "wellWidth": {"type": "number"},
                    "extraStates": {"type": "integer"},
                    "engineMode": {"type": "string"},
                    "octopusMolecule": {"type": "string"},
                    "octopusSpacing": {"type": "number"},
                    "octopusRadius": {"type": "number"},
                    "xcFunctional": {"type": "string"},
                    "mixingScheme": {"type": "string"},
                    "spinComponents": {"type": "string"},
                }
            }
        ),
        types.Tool(
            name="parse_results",
            description="Parse Octopus output files from a completed run directory. Returns eigenvalues, wavefunctions, and convergence data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "run_dir": {"type": "string", "description": "Linux path to the output directory (e.g. /workspace/output)"},
                },
                "required": ["run_dir"],
            }
        ),
    ]

# ─── SSE transport (for MCP SDK clients) ──────────────────────────

sse_transport = None

async def sse_handler(request: Request):
    global sse_transport
    transport = SseServerTransport("/messages")
    sse_transport = transport
    async def run_server():
        try:
            await mcp_server.run(transport.async_stream(), transport.async_send)
        except Exception as e:
            print(f"SSE Server error: {e}")
    asyncio.create_task(run_server())
    return await transport.handle_sse(request)

async def messages_handler(request: Request):
    global sse_transport
    if sse_transport is None:
        return JSONResponse({"error": "No SSE connection established"}, status_code=400)
    await sse_transport.handle_post_message(request)
    return JSONResponse({"status": "accepted"})


from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# ─── Starlette app with all routes ────────────────────────────────

middleware = [
    Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
]

starlette_app = Starlette(routes=[
    Route("/health", endpoint=health_handler, methods=["GET"]),
    Route("/solve", endpoint=solve_handler, methods=["POST"]),
    Route("/sse", endpoint=sse_handler, methods=["GET"]),
    Route("/messages", endpoint=messages_handler, methods=["POST"]),
], middleware=middleware)

if __name__ == "__main__":
    print("Starting Octopus Physics MCP Server on port 8000...")
    uvicorn.run(starlette_app, host="0.0.0.0", port=8000, log_level="debug")
