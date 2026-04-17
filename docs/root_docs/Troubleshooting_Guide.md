# Dirac Solver - Manual Repair Guide 🛠️

If you encounter network errors (`ERR_CONNECTION_REFUSED`) or Docker startup failures, follow these steps to manually reset the system.

## 1. Reset Network Ports (Port Cleanup)
Conflict on ports is the #1 cause of connection issues. Run these commands in **PowerShell as Administrator** to kill zombie processes:

```powershell
# Kill anything on port 3001 (Node), 8000 (Octopus), 8001 (Local Engine), and 5173 (Vite)
Stop-Process -Id (Get-NetTCPConnection -LocalPort 3001).OwningProcess -Force -ErrorAction SilentlyContinue
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess -Force -ErrorAction SilentlyContinue
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8001).OwningProcess -Force -ErrorAction SilentlyContinue
Stop-Process -Id (Get-NetTCPConnection -LocalPort 5173).OwningProcess -Force -ErrorAction SilentlyContinue
```

## 2. Standard Manual Startup Order
If `start_all.bat` fails, start them manually in separate terminals in this exact order:

1.  **Docker (Octopus Engine)**:
    ```bash
    cd docker
    docker-compose up -d
    ```
2.  **Local Engine**:
    ```bash
    python backend_engine/main.py
    ```
    *(Should listen on port **8001**)*
3.  **Vite Frontend**:
    ```bash
    cd frontend
    npm run dev
    ```
4.  **Node API Server**:
    ```bash
    npx ts-node src/server.ts
    ```

## 3. Fix Docker "server.py not found" (Errno 2)
If Docker starts but logs show `Errno 2: server.py not found`, the image or volume is out of sync.

### Option A: Force Rebuild (Recommended)
```bash
cd docker
docker-compose build --no-cache
docker-compose up -d
```

### Option B: Check Folder Structure
Ensure you are running the command from the root `Dirac_solver` or the `docker` subdirectory. The volume mapping expects a `./workspace` folder to exist in the current directory.

## 4. Local Python Errors
If you try to run `docker/workspace/server.py` **locally** (outside Docker) and see `ModuleNotFoundError: No module named 'mcp'`:
- **Cause**: You are missing the MCP library in your local Python environment.
- **Fix**: Run `pip install mcp pydantic starlette uvicorn jinja2` in your terminal.
- **Note**: It is still better to run this inside Docker to ensure Octopus binary compatibility.

---
**Tips**:
- Always use `http://localhost:5173` (NOT `https`).
- Ensure Docker Desktop is running before starting the app.
