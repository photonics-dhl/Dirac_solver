from mcp.server.fastmcp import FastMCP
import numpy as np

# Create the MCP server instance
mcp = FastMCP("DiracPhysicsEngine")

@mcp.tool()
def solve_eigenstate_mcp(
    dimensionality: str,
    grid_spacing: float,
    mass: float,
    potential_type: str
) -> dict:
    """
    Solves the eigenstate of the system.
    Note: Currently using an analytical/mock fallback due to Kwant installation limitations 
    on the host environment.
    """
    import scipy.sparse as sp
    import scipy.sparse.linalg as spla
    
    # 1D Numerical solution using Finite Difference Method
    if dimensionality == "1D" and potential_type == "InfiniteWell":
        # System parameters
        L = 1.0
        hbar = 1.0 # Natural units
        
        # Grid setup
        N = int(L / grid_spacing)
        if N < 3:
            return {"status": "error", "message": "Grid spacing too large for numerical calculation."}
            
        x = np.linspace(0, L, N)
        dx = x[1] - x[0]
        
        # Kinetic energy operator T = - (hbar^2 / 2m) * d^2/dx^2
        # Discrete Laplacian (second derivative) using central difference
        # T_ij = (hbar^2 / 2m dx^2) * (2 for i=j, -1 for i=j±1)
        t_hopping = hbar**2 / (2 * mass * dx**2)
        
        # Construct the sparse Hamiltonian matrix (Tridiagonal)
        diagonals = [
            np.full(N - 2, 2 * t_hopping),       # Main diagonal
            np.full(N - 3, -t_hopping),          # Upper diagonal
            np.full(N - 3, -t_hopping)           # Lower diagonal
        ]
        
        # N-2 because we enforce Dirichlet boundary conditions (psi = 0 at edges)
        H = sp.diags(diagonals, [0, 1, -1], format='csr')
        
        # Solve for the lowest eigenvalues (k=1, smallest magnitude 'SM')
        try:
            eigenvalues, eigenvectors = spla.eigsh(H, k=1, which='SM')
            E_1 = float(eigenvalues[0])
        except Exception as e:
            return {"status": "error", "message": f"Diagonalization failed: {str(e)}"}
        
        return {
            "status": "success",
            "dimensionality": dimensionality,
            "eigenvalue_0": E_1,
            "message": "Used analytical solution due to Kwant absence."
        }
        
    return {
        "status": "error",
        "message": f"Unsupported configuration for fallback: {dimensionality}, {potential_type}"
    }

@mcp.tool()
def verify_physics_benchmark_mcp(
    benchmark_name: str
) -> dict:
    """
    Runs a specific analytical physics benchmark.
    """
    if benchmark_name == "1D_InfiniteWell":
        # Test case: mass=1.0, L=1.0, analytical E_1 = pi^2 / 2 ≈ 4.9348
        expected = np.pi**2 / 2
        
        # Call the solver with a finer grid to reduce discretization error (O(dx^2))
        result = solve_eigenstate_mcp("1D", 0.001, 1.0, "InfiniteWell")
        
        if result.get("status") == "success":
            E_calc = result["eigenvalue_0"]
            tolerance = 1e-4
            passed = abs(E_calc - expected) < tolerance
            
            return {
                "benchmark": benchmark_name,
                "passed": passed,
                "expected": expected,
                "calculated": E_calc,
                "error": abs(E_calc - expected)
            }
            
    return {"status": "error", "message": f"Unknown benchmark: {benchmark_name}"}

if __name__ == "__main__":
    print("Starting Dirac Physics Engine MCP Server...")
    mcp.run(transport='stdio')
