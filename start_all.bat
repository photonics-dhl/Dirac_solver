@echo off
setlocal EnableDelayedExpansion

REM 
REM  Dirac Solver  Start All Services
REM  Starts: Docker (Octopus MCP), Local Engine, Vite Frontend, Node API
REM 

set DOCKER_DESKTOP=D:\Softwares_new\Docker\Docker Desktop.exe
set DOCKER_EXE=D:\Softwares_new\Docker\resources\bin\docker.exe
set COMPOSE_EXE=D:\Softwares_new\Docker\resources\bin\docker-compose.exe
set WORK_DIR=%~dp0

REM Ensure Docker binaries are on PATH for this session
set PATH=%PATH%;D:\Softwares_new\Docker\resources\bin

echo ======================================================
echo  Dirac Solver  Service Launcher
echo ======================================================
echo.

REM  [1/5] Kill stale processes 
echo [1/5] Clearing stale processes...
taskkill /IM node.exe /F >nul 2>&1
taskkill /IM python.exe /F >nul 2>&1
timeout /t 1 /nobreak >nul

REM  [2/5] Ensure Docker Desktop daemon is running 
echo [2/5] Checking Docker Desktop daemon...
docker info >nul 2>&1
if %errorlevel% equ 0 (
    echo       Docker daemon: READY
    goto :docker_ready
)

echo       Docker daemon not running. Starting Docker Desktop...
if not exist "%DOCKER_DESKTOP%" (
    echo [WARNING] Docker Desktop not found at:
    echo           %DOCKER_DESKTOP%
    echo           Octopus engine will be OFFLINE.
    goto :docker_failed
)

REM Start Docker Desktop (non-blocking)
start "" "%DOCKER_DESKTOP%"

REM Poll for daemon readiness (up to 60 seconds)
echo       Waiting for daemon (up to 60s)...
set /a WAIT=0
:docker_poll
timeout /t 3 /nobreak >nul
set /a WAIT+=3
docker info >nul 2>&1
if %errorlevel% equ 0 goto :docker_ready
if %WAIT% geq 60 (
    echo [WARNING] Docker daemon did not start within 60s.
    echo           Octopus engine will be OFFLINE.
    goto :docker_failed
)
set /a PCT=!WAIT!*100/60
echo       Waiting... %WAIT%s / 60s
goto :docker_poll

:docker_ready
echo       Docker daemon: ONLINE

REM  [3/5] Start Octopus container 
echo [3/5] Starting Octopus Engine (Docker - Port 8000)...
cd /d "%WORK_DIR%docker"
docker compose up -d
if %errorlevel% neq 0 (
    echo       Trying docker-compose fallback...
    docker-compose up -d
)
cd /d "%WORK_DIR%"

REM Wait for MCP health endpoint to respond
echo       Waiting for Octopus MCP to respond on :8000...
set /a WAIT=0
:mcp_poll
timeout /t 2 /nobreak >nul
set /a WAIT+=2
powershell -NoProfile -Command "try { $r=(Invoke-WebRequest -Uri http://localhost:8000/health -UseBasicParsing -TimeoutSec 2).StatusCode; exit ($r -eq 200 ? 0 : 1) } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 (
    echo       Octopus MCP: ONLINE [%WAIT%s]
    goto :mcp_ready
)
if %WAIT% geq 30 (
    echo [WARNING] MCP did not respond within 30s.
    goto :mcp_ready
)
goto :mcp_poll

:docker_failed
:mcp_ready

REM  [4/5] Start Python Local Physics Engine 
echo [4/5] Starting Local Physics Engine (Port 8001)...
start "Python-Engine-8001" /min cmd /c "cd /d %WORK_DIR% && python backend_engine/main.py 2>&1"
timeout /t 2 /nobreak >nul

REM  [5/5] Start Vite + Node API 
echo [5/5] Starting Vite Frontend (5173) and Node API (3001)...
start "Vite-Frontend-5173" /min cmd /c "cd /d %WORK_DIR%frontend && npm run dev 2>&1"
timeout /t 2 /nobreak >nul
start "Node-API-3001" /min cmd /c "cd /d %WORK_DIR% && npx ts-node src/server.ts 2>&1"
timeout /t 3 /nobreak >nul

echo.
echo ======================================================
echo  Services Summary
echo ======================================================
echo   Frontend   : http://localhost:5173/
echo   Node API   : http://localhost:3001/
echo   Local Eng  : http://localhost:8001/
echo   Octopus    : http://localhost:8000/health
echo ======================================================
echo.
echo Press any key to close this launcher window.
echo (Services will keep running in background windows.)
pause > nul

