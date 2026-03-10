
import requests

config = {
    "mass": 0.511,
    "gridSpacing": 0.1,
    "potentialStrength": -1.0,
    "dimensionality": "1D",
    "spatialRange": 10.0,
    "potentialType": "InfiniteWell",
    "wellWidth": 1.0,
    "equationType": "Schrodinger",
    "problemType": "boundstate"
}

try:
    resp = requests.post("http://127.0.0.1:8001/solve", json=config)
    print("Status Code:", resp.status_code)
    data = resp.json()
    print("Eigenvalues:", data.get("eigenvalues"))
    print("Matrix Info:", data.get("matrix_info"))
    print("Wavefunctions Count:", len(data.get("wavefunctions", [])))
except Exception as e:
    print("Error:", e)
