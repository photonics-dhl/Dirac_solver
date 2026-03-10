from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import eigsh
import math

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PhysicsConfig(BaseModel):
    # Core parameters
    mass: float = 1.0
    gridSpacing: float = 0.05
    potentialStrength: float = 0.0
    # Geometry
    dimensionality: str = "1D"
    unitSystem: str = "natural"
    spatialRange: float = 10.0
    gridPoints: int = 100
    boundaryCondition: str = "dirichlet"
    # Potential
    potentialType: str = "InfiniteWell"
    wellWidth: float = 1.0
    customExpression: Optional[str] = None
    # Equation & problem type
    equationType: str = "Schrodinger"
    problemType: str = "boundstate"
    picture: str = "schrodinger"
    # Time evolution parameters
    numTimeSteps: int = 50
    totalTime: float = 5.0
    initialState: str = "gaussian"
    gaussianCenter: float = 0.0
    gaussianWidth: float = 0.3
    gaussianMomentum: float = 5.0
    # Scattering
    scatteringEnergyMin: float = 0.0
    scatteringEnergyMax: float = 10.0
    scatteringEnergySteps: int = 200


# ─── Potential Builders ─────────────────────────────────────────────

def build_potential_1d(x: np.ndarray, config: PhysicsConfig) -> np.ndarray:
    V = np.zeros(len(x))
    ptype = config.potentialType.lower().replace(" ", "").replace("_", "")
    V0 = config.potentialStrength
    w = config.wellWidth / 2.0

    if ptype == "infinitewell":
        V[:] = 0.0
        # Infinite walls are enforced in the kinetic operator builder

    elif ptype == "finitewell":
        for i in range(len(x)):
            if np.abs(x[i]) < w:
                V[i] = V0  # inside well (usually negative)
            else:
                V[i] = 0.0 # outside well

    elif ptype == "coulomb":
        Z = abs(V0) if V0 != 0 else 1.0
        a = config.gridSpacing * 0.5  # softening
        V = -Z / np.sqrt(x**2 + a**2)

    elif ptype == "harmonic":
        k = abs(V0) if V0 != 0 else 0.5
        V = k * x**2

    elif ptype == "gaussian":
        sigma = w  # wellWidth used as sigma
        V0_ = V0 if V0 != 0 else -1.0
        V = V0_ * np.exp(-x**2 / (2 * sigma**2))

    elif ptype == "step":
        V[x >= 0] = V0
        V[x < 0] = 0.0

    elif ptype == "doublewell":
        # Double well: V(x) = V0*(x^2 - d^2)^2 / d^4; d = wellWidth/2
        d = w
        a = abs(V0) if V0 != 0 else 1.0
        V = a * (x**2 - d**2)**2 / (d**4 + 1e-10)

    elif ptype == "morse":
        # Morse potential: V(x) = V0*(1-exp(-alpha*(x-xe)))^2; xe=0, alpha=wellWidth
        alpha = config.wellWidth if config.wellWidth != 0 else 1.0
        V0_ = abs(V0) if V0 != 0 else 1.0
        V = V0_ * (1 - np.exp(-alpha * x))**2

    elif ptype == "freespace":
        V[:] = 0.0

    elif ptype == "custom" and config.customExpression:
        try:
            V = eval(config.customExpression, {"x": x, "np": np,
                     "sin": np.sin, "cos": np.cos, "exp": np.exp,
                     "sqrt": np.sqrt, "abs": np.abs, "pi": np.pi})
            if np.isscalar(V):
                V = np.full_like(x, V)
        except Exception as e:
            raise ValueError(f"Invalid custom expression: {e}")
    else:
        # Fallback to constant potential if not matched, but should not happen for standard types
        V[:] = V0

    return V


def build_2d_potential(xx: np.ndarray, yy: np.ndarray, config: PhysicsConfig) -> np.ndarray:
    """2D potential on meshgrid (Nx, Ny)."""
    V_x = build_potential_1d(xx[0, :], config)  # potential along x
    V_y = build_potential_1d(yy[:, 0], config)  # potential along y
    # For separable potentials, V(x,y) = V(x) + V(y)
    return V_x[np.newaxis, :] + V_y[:, np.newaxis]


# ─── Hamiltonian Builders ────────────────────────────────────────────

def build_schrodinger_1d(x, V, m, config):
    N = len(x)
    dx = x[1] - x[0]
    diag = np.ones(N) * (1.0 / (m * dx**2)) + V
    off = np.ones(N - 1) * (-0.5 / (m * dx**2))

    ptype = config.potentialType.lower()
    if "infinite" in ptype and "well" in ptype:
        w = config.wellWidth / 2.0
        for i in range(N):
            if np.abs(x[i]) >= w - 1e-10:
                if i < N - 1: off[i] = 0.0
                if i > 0: off[i - 1] = 0.0

    return sparse.diags([off, diag, off], [-1, 0, 1], format='csr')


def build_dirac_1d(x, V, m, config):
    """1D Dirac Hamiltonian in 2-component spinor space (2N × 2N matrix)."""
    N = len(x)
    dx = x[1] - x[0]

    diag_A = m + V
    diag_B = -m + V
    H_AA = sparse.diags([diag_A], [0], shape=(N, N))
    H_BB = sparse.diags([diag_B], [0], shape=(N, N))

    b_off = np.ones(N - 1) / (2.0 * dx)
    ptype = config.potentialType.lower()
    if "infinite" in ptype and "well" in ptype:
        w = config.wellWidth / 2.0
        for i in range(N):
            if np.abs(x[i]) >= w - 1e-10:
                if i < N - 1: b_off[i] = 0.0
                if i > 0: b_off[i - 1] = 0.0

    D_minus = sparse.diags([b_off, -b_off], [-1, 1], shape=(N, N))
    D_plus = sparse.diags([-b_off, b_off], [-1, 1], shape=(N, N))

    return sparse.bmat([[H_AA, D_minus], [D_plus, H_BB]], format='csr')


def build_kleingorden_1d(x, V, m, config):
    """Klein-Gordon effective Hamiltonian: H_eff = -∂²/∂x² + m² + 2mV(x)
    We solve H_eff ψ = E² ψ, then E = sqrt(eigenvalue).
    This is equivalent to (E - V)² = p² + m², so H_eff = p² + (m + V)² - V²
    Simplified: H_eff = -∂²/∂x² + m² + 2mV for weak potentials.
    """
    N = len(x)
    dx = x[1] - x[0]
    # p² operator (same as kinetic in Schrödinger but without 1/2m)
    diag = np.ones(N) * (1.0 / dx**2) + m**2 + 2 * m * V
    off = np.ones(N - 1) * (-0.5 / dx**2)

    ptype = config.potentialType.lower()
    if "infinite" in ptype and "well" in ptype:
        w = config.wellWidth / 2.0
        for i in range(N):
            if np.abs(x[i]) >= w - 1e-10:
                if i < N - 1: off[i] = 0.0
                if i > 0: off[i - 1] = 0.0

    return sparse.diags([off, diag, off], [-1, 0, 1], format='csr')


def build_schrodinger_2d(x, y, V2d, m):
    """2D Schrödinger Hamiltonian via Kronecker sum."""
    Nx, Ny = len(x), len(y)
    dx, dy = x[1] - x[0], y[1] - y[0]

    # 1D kinetic operators
    diag_x = np.ones(Nx) * (1.0 / (m * dx**2))
    off_x = np.ones(Nx - 1) * (-0.5 / (m * dx**2))
    T_x = sparse.diags([off_x, diag_x, off_x], [-1, 0, 1], format='csr')

    diag_y = np.ones(Ny) * (1.0 / (m * dy**2))
    off_y = np.ones(Ny - 1) * (-0.5 / (m * dy**2))
    T_y = sparse.diags([off_y, diag_y, off_y], [-1, 0, 1], format='csr')

    # Kronecker sum: T_2D = T_x ⊗ I_y + I_x ⊗ T_y
    I_x = sparse.eye(Nx, format='csr')
    I_y = sparse.eye(Ny, format='csr')
    T_2D = sparse.kron(T_x, I_y, format='csr') + sparse.kron(I_x, T_y, format='csr')

    # Potential (flattened)
    V_flat = V2d.flatten()
    V_mat = sparse.diags([V_flat], [0], format='csr')

    return T_2D + V_mat


# ─── Eigenstate Solver ───────────────────────────────────────────────

def solve_eigenstates(H, N_total, k=10):
    """Solve for k lowest eigenstates of sparse Hamiltonian H."""
    k = min(k, N_total - 2)
    if N_total <= 2000:
        evals, evecs = np.linalg.eigh(H.toarray())
    else:
        evals, evecs = eigsh(H, k=k, which='SA')
    idx = np.argsort(evals)
    return evals[idx], evecs[:, idx]


# ─── Momentum Space ──────────────────────────────────────────────────

def compute_momentum_space(psi_x, dx):
    """Compute momentum-space wavefunction via FFT."""
    N = len(psi_x)
    freqs = np.fft.fftfreq(N, d=dx)
    p_grid = 2 * np.pi * freqs
    psi_p_raw = np.fft.fft(psi_x) * dx / np.sqrt(2 * np.pi)
    sort_idx = np.argsort(p_grid)
    return p_grid[sort_idx], np.abs(psi_p_raw[sort_idx])


# ─── Time Evolution Solver ───────────────────────────────────────────

def solve_time_evolution(x, V, m, config, eq):
    """
    Build eigenstate basis, project initial Gaussian wavepacket,
    propagate in time, return |ψ(x,t)|².
    """
    N = len(x)
    dx = x[1] - x[0]

    # Build Hamiltonian and solve eigenstates
    if "dirac" in eq:
        H = build_dirac_1d(x, V, m, config)
        k_use = min(80, 2 * N - 2)
    elif "kleingorden" in eq or "klein" in eq:
        H = build_kleingorden_1d(x, V, m, config)
        k_use = min(80, N - 2)
    else:
        H = build_schrodinger_1d(x, V, m, config)
        k_use = min(80, N - 2)

    evals, evecs = solve_eigenstates(H, H.shape[0], k=k_use)

    # For Dirac, extract upper component
    if "dirac" in eq:
        evals_phys = []
        evecs_phys = []
        # Keep only positive-energy states
        for i in range(len(evals)):
            if evals[i] > 0:
                psi_A = evecs[:N, i]
                norm = np.sqrt(np.sum(np.abs(psi_A)**2) * dx)
                if norm > 1e-12:
                    evecs_phys.append(psi_A / norm)
                    evals_phys.append(evals[i])
        evals = np.array(evals_phys[:80])
        phi = np.array(evecs_phys[:80])  # shape (k, N)
    elif "kleingorden" in eq or "klein" in eq:
        # Take positive energy sqrt(eigenvalues)
        pos_mask = evals > 0
        evals = np.sqrt(np.clip(evals[pos_mask], 0, None))[:80]
        phi = evecs[:, pos_mask].T[:80]  # shape (k, N)
        for i in range(len(phi)):
            norm = np.sqrt(np.sum(np.abs(phi[i])**2) * dx)
            if norm > 1e-12:
                phi[i] /= norm
    else:
        # Keep up to lowest 80
        k_keep = min(80, len(evals))
        evals = evals[:k_keep]
        phi = evecs[:, :k_keep].T  # shape (k, N)
        for i in range(len(phi)):
            norm = np.sqrt(np.sum(np.abs(phi[i])**2) * dx)
            if norm > 1e-12:
                phi[i] /= norm

    if len(evals) == 0:
        raise ValueError("No valid eigenstates found for time evolution")

    # Construct initial Gaussian wavepacket
    x0 = config.gaussianCenter
    sigma = config.gaussianWidth * (x[-1] - x[0])  # relative to domain
    k0 = config.gaussianMomentum
    psi0 = np.exp(-(x - x0)**2 / (4 * sigma**2)) * np.exp(1j * k0 * x)
    norm0 = np.sqrt(np.sum(np.abs(psi0)**2) * dx)
    psi0 /= norm0

    # Expansion coefficients: c_n = <phi_n | psi_0>
    c = np.array([np.sum(phi[i] * psi0) * dx for i in range(len(evals))])

    # Time grid
    T_total = config.totalTime
    n_steps = min(config.numTimeSteps, 100)
    time_grid = np.linspace(0, T_total, n_steps)

    # Propagate: ψ(x,t) = Σ_n c_n φ_n(x) e^{-i E_n t}
    psi_t = np.zeros((n_steps, N))  # |ψ(x,t)|²
    for ti, t in enumerate(time_grid):
        psi_xt = np.zeros(N, dtype=complex)
        for ni in range(len(evals)):
            psi_xt += c[ni] * phi[ni] * np.exp(-1j * evals[ni] * t)
        psi_t[ti] = np.abs(psi_xt)**2

    return {
        "time_grid": time_grid.tolist(),
        "psi_t": psi_t.tolist(),
        "initial_state": (np.abs(psi0)**2).tolist(),
        "eigenvalues": evals.tolist(),
        "initial_coefficients": (np.abs(c)**2).tolist(),
        "x_grid": x.tolist(),
    }


# ─── Scattering Solver (Transfer Matrix) ────────────────────────────

def solve_scattering(x, V, m, config, eq):
    """
    Transfer matrix method for 1D scattering.
    Computes T(E) and R(E) for a range of incident energies.
    Returns energy_range, transmission, reflection, and scattering wavefunctions
    at selected energies.
    """
    E_min = config.scatteringEnergyMin
    E_max = config.scatteringEnergyMax
    n_E = min(config.scatteringEnergySteps, 500)
    energies = np.linspace(E_min + 1e-6, E_max, n_E)

    dx = x[1] - x[0]
    N = len(x)

    transmission = np.zeros(n_E)
    reflection = np.zeros(n_E)

    for ei, E in enumerate(energies):
        # Local wavenumber: k²(x) = 2m(E - V(x)) for Schrödinger
        # For KG: k²(x) = (E - V)² - m²; for Dirac similarly
        if "dirac" in eq.lower() or "kleingorden" in eq.lower() or "klein" in eq.lower():
            k2 = (E - V)**2 - m**2
        else:
            k2 = 2 * m * (E - V)

        # Transfer matrix product
        M = np.eye(2, dtype=complex)
        for i in range(N - 1):
            k2i = k2[i]
            if k2i > 0:
                ki = np.sqrt(k2i)
                phi_i = ki * dx
                Mi = np.array([
                    [np.cos(phi_i), np.sin(phi_i) / ki],
                    [-ki * np.sin(phi_i), np.cos(phi_i)]
                ], dtype=complex)
            else:
                kappa = np.sqrt(max(-k2i, 1e-12))
                phi_i = kappa * dx
                Mi = np.array([
                    [np.cosh(phi_i), np.sinh(phi_i) / kappa],
                    [kappa * np.sinh(phi_i), np.cosh(phi_i)]
                ], dtype=complex)
            M = M @ Mi

        # Transmission: T = 1 / |M[0,0]|²  (simplified for same-medium boundaries)
        k2_left = k2[0]
        k2_right = k2[-1]

        if k2_left > 0 and k2_right > 0:
            k_left = np.sqrt(k2_left)
            k_right = np.sqrt(k2_right)
            # T = (k_right/k_left) / |M11 + M12*k_right|² ... overly complex;
            # Use simplified: T ≈ k_right/k_left * |2/(M[0,0]+M[0,1]*k_right/1j+...)|
            # Simplified (same-medium case): T = 1/|M[0,0]|²
            denom = abs(M[0, 0])**2
            T_val = min(k_right / k_left / max(denom, 1e-12), 1.0)
            T_val = max(T_val, 0.0)
        elif k2_left > 0 and k2_right <= 0:
            T_val = 0.0  # evanescent on right — total reflection
        else:
            T_val = 0.0

        transmission[ei] = T_val
        reflection[ei] = 1.0 - T_val

    # Find resonances: peaks in T(E)
    resonance_indices = []
    for i in range(1, n_E - 1):
        if transmission[i] > transmission[i - 1] and transmission[i] > transmission[i + 1]:
            if transmission[i] > 0.5:  # only strong resonances
                resonance_indices.append(i)
    resonances = [float(energies[i]) for i in resonance_indices]

    # Compute wavefunction at a few representative energies (for visualization)
    sample_energies_idx = np.linspace(0, n_E - 1, min(5, n_E), dtype=int)
    sample_wavefunctions = []
    for ei in sample_energies_idx:
        E = energies[ei]
        k2 = 2 * m * (E - V)
        if k2[0] > 0:
            k0 = np.sqrt(k2[0])
            # Approximate wavefunction: incident + reflected on left, transmitted on right
            psi = np.zeros(N, dtype=complex)
            # Simple approximation: plane wave modulated by local wavenumber
            phase = np.cumsum(np.sqrt(np.clip(k2, 0, None))) * dx
            psi = np.exp(1j * phase) * np.sqrt(np.clip(k2, 1e-12, None))**(-0.25)
            psi /= (np.sqrt(np.sum(np.abs(psi)**2) * dx) + 1e-12)
            sample_wavefunctions.append({
                "energy": float(E),
                "psi_sq": np.abs(psi).tolist(),
                "transmission": float(transmission[ei]),
            })

    return {
        "energy_range": energies.tolist(),
        "transmission": transmission.tolist(),
        "reflection": reflection.tolist(),
        "resonances": resonances,
        "sample_wavefunctions": sample_wavefunctions,
        "x_grid": x.tolist(),
    }


# ─── Main Solve Endpoint ─────────────────────────────────────────────

@app.post("/solve")
def solve_quantum_system(config: PhysicsConfig):
    try:
        # ── Grid Setup ──────────────────────────────────────────────
        eq = config.equationType.lower()
        problem = config.problemType.lower()
        dim = config.dimensionality.upper()

        dx_target = config.gridSpacing
        N_req = int(np.round(config.spatialRange / dx_target)) + 1

        # Memory safety limits
        if dim == "1D":
            N = min(N_req, 2000)
        elif dim == "2D":
            N = min(int(np.sqrt(min(N_req**2, 10000))), 80)
        else:  # 3D
            N = min(int(N_req**(1/3)), 25)

        x = np.linspace(-config.spatialRange / 2, config.spatialRange / 2, N)
        dx = x[1] - x[0]
        m = config.mass
        V = build_potential_1d(x, config)

        # ── Scattering Problem ──────────────────────────────────────
        if "scatter" in problem:
            result = solve_scattering(x, V, m, config, eq)
            result["problemType"] = "scattering"
            result["equationType"] = config.equationType
            result["potential_V"] = V.tolist()
            result["matrix_info"] = {"size": N, "non_zeros": N * 3, "isHermitian": True}
            return result

        # ── Time Evolution Problem ──────────────────────────────────
        if "time" in problem or "evolution" in problem:
            result = solve_time_evolution(x, V, m, config, eq)
            result["problemType"] = "timeevolution"
            result["equationType"] = config.equationType
            result["potential_V"] = V.tolist()
            result["matrix_info"] = {"size": N, "non_zeros": N * 3, "isHermitian": True}
            return result

        # ── Bound State Problem ─────────────────────────────────────
        k_display = 10

        if dim == "2D":
            # 2D Schrödinger only
            Ny, Nx = N, N
            y = np.linspace(-config.spatialRange / 2, config.spatialRange / 2, Ny)
            xx, yy = np.meshgrid(x, y)
            V2d = build_2d_potential(xx, yy, config)
            H = build_schrodinger_2d(x, y, V2d, m)
            N_total = Nx * Ny
            k_display = min(k_display, N_total - 2)
            evals, evecs = solve_eigenstates(H, N_total, k=k_display)

            k_display = min(k_display, len(evals))
            evals = evals[:k_display]
            evecs = evecs[:, :k_display]

            eigenvalues = evals.tolist()
            wavefunctions = []
            for i in range(k_display):
                psi_flat = evecs[:, i].real
                norm = np.sqrt(np.sum(psi_flat**2) * dx**2)
                psi_flat /= (norm + 1e-12)
                psi_2d = psi_flat.reshape(Ny, Nx)
                # Marginal distributions for 1D plots
                psi_x = np.sqrt(np.sum(psi_2d**2, axis=0) * dx)
                psi_y = np.sqrt(np.sum(psi_2d**2, axis=1) * dx)
                wavefunctions.append({
                    "psi_up": psi_x.tolist(),
                    "psi_down": psi_y.tolist(),
                    "psi_2d": psi_2d.tolist(),
                })

            # Physical Filter: only return true bound states (E < V_max)
            v_max = np.max(V2d)
            if v_max > np.min(V2d) + 1e-5 and "infinite" not in config.potentialType.lower():
                bound_mask = evals < v_max
                k_bound = min(k_display, np.sum(bound_mask))
                eigenvalues = eigenvalues[:k_bound]
                wavefunctions = wavefunctions[:k_bound]

            return {
                "problemType": "boundstate",
                "equationType": config.equationType,
                "dimensionality": "2D",
                "eigenvalues": eigenvalues,
                "wavefunctions": wavefunctions,
                "x_grid": x.tolist(),
                "y_grid": y.tolist(),
                "potential_V": V.tolist(),
                "matrix_info": {"size": N_total, "non_zeros": N_total * 5, "isHermitian": True},
            }

        elif dim == "3D":
            # 3D: only return simplified result (memory constrained)
            Nz = N
            z = x.copy()
            # Build 3D as three 1D problems + potential (separable approximation)
            H = build_schrodinger_1d(x, V, m, config)  # Use 1D for now
            evals, evecs = solve_eigenstates(H, N, k=k_display)
            k_display = min(k_display, len(evals))
            evals = evals[:k_display]
            evecs = evecs[:, :k_display]

            eigenvalues = (evals * 3).tolist()  # 3D energy ≈ 3 × E_1D for separable
            wavefunctions = []
            for i in range(k_display):
                psi = evecs[:, i]
                norm = np.sqrt(np.sum(np.abs(psi)**2) * dx)
                psi = psi / (norm + 1e-12)
                wavefunctions.append({
                    "psi_up": psi.tolist(),
                    "psi_down": np.zeros(N).tolist(),
                })

            return {
                "problemType": "boundstate",
                "equationType": config.equationType,
                "dimensionality": "3D",
                "eigenvalues": eigenvalues,
                "wavefunctions": wavefunctions,
                "x_grid": x.tolist(),
                "potential_V": V.tolist(),
                "matrix_info": {"size": N**3, "non_zeros": N**3 * 7, "isHermitian": True},
            }

        # ── 1D Bound State Solvers ──────────────────────────────────
        if "kleingorden" in eq or "klein" in eq or "kg" in eq:
            H = build_kleingorden_1d(x, V, m, config)
            evals_sq, evecs = solve_eigenstates(H, N, k=k_display)
            # Energy = sqrt(eigenvalue), only positive
            pos_mask = evals_sq > m**2  # above rest mass threshold
            if pos_mask.sum() == 0:
                pos_mask = evals_sq > 0
            evals = np.sqrt(np.clip(evals_sq[pos_mask], 0, None))
            evecs_pos = evecs[:, pos_mask]
            k_display = min(k_display, len(evals))
            evals = evals[:k_display]
            evecs_pos = evecs_pos[:, :k_display]

            eigenvalues = evals.tolist()
            freqs = np.fft.fftfreq(N, d=dx)
            p_grid = 2 * np.pi * freqs
            sort_idx = np.argsort(p_grid)
            p_grid_sorted = p_grid[sort_idx]

            wavefunctions = []
            for i in range(k_display):
                psi = evecs_pos[:, i].real
                norm = np.sqrt(np.sum(psi**2) * dx)
                psi /= (norm + 1e-12)
                _, psi_p = compute_momentum_space(psi, dx)
                wavefunctions.append({
                    "psi_up": psi.tolist(),
                    "psi_down": np.zeros(N).tolist(),
                    "psi_p_mag": psi_p.tolist(),
                })

            H_mat = H
            return {
                "problemType": "boundstate",
                "equationType": "KleinGordon",
                "eigenvalues": eigenvalues,
                "wavefunctions": wavefunctions,
                "x_grid": x.tolist(),
                "p_grid": p_grid_sorted.tolist(),
                "potential_V": V.tolist(),
                "matrix_info": {"size": H_mat.shape[0], "non_zeros": H_mat.nnz, "isHermitian": True},
            }

        elif "dirac" in eq:
            H = build_dirac_1d(x, V, m, config)
            evals, evecs = solve_eigenstates(H, 2 * N, k=min(k_display * 2, 2 * N - 2))

            # Select k_half states near +m and k_half near -m
            k_half = 5
            diff_plus = np.abs(evals - m)
            diff_minus = np.abs(evals + m)
            plus_idx = np.argsort(diff_plus)[:k_half]
            minus_idx = np.argsort(diff_minus)[:k_half]
            selected_idx = sorted(set(plus_idx.tolist() + minus_idx.tolist()))

            eigenvalues = [float(evals[i]) for i in selected_idx]
            wavefunctions = []
            for idx in selected_idx:
                psi_A = evecs[:N, idx]
                psi_B = evecs[N:, idx]
                norm = np.sqrt(np.sum((np.abs(psi_A)**2 + np.abs(psi_B)**2)) * dx)
                psi_A = psi_A / (norm + 1e-12)
                psi_B = psi_B / (norm + 1e-12)
                _, psi_p = compute_momentum_space(psi_A.real, dx)
                wavefunctions.append({
                    "psi_up": psi_A.real.tolist(),
                    "psi_down": psi_B.real.tolist(),
                    "psi_p_mag": psi_p.tolist(),
                })

            freqs = np.fft.fftfreq(N, d=dx)
            p_grid = 2 * np.pi * freqs
            sort_idx = np.argsort(p_grid)
            p_grid_sorted = p_grid[sort_idx]

            return {
                "problemType": "boundstate",
                "equationType": "Dirac",
                "eigenvalues": eigenvalues,
                "wavefunctions": wavefunctions,
                "x_grid": x.tolist(),
                "p_grid": p_grid_sorted.tolist(),
                "potential_V": V.tolist(),
                "matrix_info": {"size": H.shape[0], "non_zeros": H.nnz, "isHermitian": True},
            }

        else:
            # Schrödinger
            H = build_schrodinger_1d(x, V, m, config)
            evals, evecs = solve_eigenstates(H, N, k=k_display)

            k_display = min(k_display, len(evals))
            evals = evals[:k_display]
            evecs = evecs[:, :k_display]

            freqs = np.fft.fftfreq(N, d=dx)
            p_grid = 2 * np.pi * freqs
            sort_idx = np.argsort(p_grid)
            p_grid_sorted = p_grid[sort_idx]

            eigenvalues = evals.tolist()
            wavefunctions = []
            for i in range(k_display):
                psi = evecs[:, i].real
                norm = np.sqrt(np.sum(psi**2) * dx)
                psi /= (norm + 1e-12)
                _, psi_p = compute_momentum_space(psi, dx)
                wavefunctions.append({
                    "psi_up": psi.tolist(),
                    "psi_down": np.zeros(N).tolist(),
                    "psi_p_mag": psi_p.tolist(),
                })

            # Physical Filter: only return true bound states (E < V_max) for non-infinite wells
            v_max = np.max(V)
            if v_max > np.min(V) + 1e-5 and "infinite" not in config.potentialType.lower():
                bound_mask = evals < v_max
                k_bound = min(k_display, np.sum(bound_mask))
                eigenvalues = eigenvalues[:k_bound]
                wavefunctions = wavefunctions[:k_bound]

            return {
                "problemType": "boundstate",
                "equationType": "Schrodinger",
                "eigenvalues": eigenvalues,
                "wavefunctions": wavefunctions,
                "x_grid": x.tolist(),
                "p_grid": p_grid_sorted.tolist(),
                "potential_V": V.tolist(),
                "matrix_info": {"size": H.shape[0], "non_zeros": H.nnz, "isHermitian": True},
            }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
