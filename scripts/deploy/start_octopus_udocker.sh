#!/bin/sh
set -eu

CONTAINER_NAME="${CONTAINER_NAME:-dirac_octopus_udocker}"
IMAGE_NAME="${IMAGE_NAME:-registry.gitlab.com/octopus-code/octopus:16.0}"
UDOCKER_BIN="${UDOCKER_BIN:-$HOME/.local/bin/udocker}"

if [ ! -x "$UDOCKER_BIN" ]; then
    if command -v udocker >/dev/null 2>&1; then
        UDOCKER_BIN="$(command -v udocker)"
    else
        echo "Error: udocker not found. Install with: python3 -m pip install --user udocker"
        exit 1
    fi
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
WORKSPACE_DIR="$SCRIPT_DIR/docker/workspace"
OUTPUT_DIR="$SCRIPT_DIR/@Octopus_docs/output"
LOG_DIR="$SCRIPT_DIR/logs"

mkdir -p "$OUTPUT_DIR" "$LOG_DIR"

if ! "$UDOCKER_BIN" images | grep -q "$IMAGE_NAME"; then
    echo "Image not found locally: $IMAGE_NAME"
    echo "Trying pull (may fail on restricted network)..."
    "$UDOCKER_BIN" pull "$IMAGE_NAME"
fi

if ! "$UDOCKER_BIN" ps | grep -Fq "$CONTAINER_NAME"; then
    echo "Creating container $CONTAINER_NAME from $IMAGE_NAME..."
    "$UDOCKER_BIN" create --name="$CONTAINER_NAME" "$IMAGE_NAME"
fi

echo "Configuring udocker execution mode (F3) for $CONTAINER_NAME..."
if ! "$UDOCKER_BIN" setup --force --execmode=F3 "$CONTAINER_NAME" > /tmp/udocker_setup.log 2>&1; then
    echo "Warning: failed to set F3 execmode, attempting to continue."
    tail -n 20 /tmp/udocker_setup.log || true
fi

if ! "$UDOCKER_BIN" run --workdir=/tmp "$CONTAINER_NAME" octopus --version > /tmp/octopus_probe.log 2>&1; then
    echo "Error: udocker container cannot run octopus."
    tail -n 40 /tmp/octopus_probe.log || true
    exit 1
fi

PYTHON_BIN="python3"
if [ -x "$HOME/miniconda3/envs/ai_agent/bin/python" ]; then
    PYTHON_BIN="$HOME/miniconda3/envs/ai_agent/bin/python"
fi

MISSING_MODS="$("$PYTHON_BIN" - <<'PY'
import importlib.util
mods = ["uvicorn", "starlette", "jinja2", "numpy"]
missing = [m for m in mods if importlib.util.find_spec(m) is None]
print(",".join(missing))
PY
)"

if [ -n "$MISSING_MODS" ]; then
    echo "Installing missing Python deps: $MISSING_MODS"
    if ! "$PYTHON_BIN" -m pip install --user uvicorn starlette jinja2 numpy; then
        echo "Error: failed to install required Python packages ($MISSING_MODS)."
        echo "Please install them manually into the ai_agent environment, then retry."
        exit 1
    fi
fi

echo "Starting Octopus MCP server on port 8000 via host python + udocker octopus..."
cd "$WORKSPACE_DIR"
export PYTHONUNBUFFERED=1
export UDOCKER_BIN
export OCTOPUS_UDOCKER_CONTAINER="$CONTAINER_NAME"
export OCTOPUS_OUTPUT_DIR="$OUTPUT_DIR"
export OCTOPUS_EXEC_STRATEGY="${OCTOPUS_EXEC_STRATEGY:-hpc}"
export OCTOPUS_HPC_ENV_SCRIPT="${OCTOPUS_HPC_ENV_SCRIPT:-/data/apps/intel/2018u3/env.sh}"
export OCTOPUS_PBS_QUEUE="${OCTOPUS_PBS_QUEUE:-workq}"
export OCTOPUS_PBS_QUEUE_CANDIDATES="${OCTOPUS_PBS_QUEUE_CANDIDATES:-workq,com}"
export OCTOPUS_PBS_NCPUS="${OCTOPUS_PBS_NCPUS:-64}"
export OCTOPUS_PBS_MPIPROCS="${OCTOPUS_PBS_MPIPROCS:-64}"
export OCTOPUS_PBS_LAUNCHER="${OCTOPUS_PBS_LAUNCHER:-container-mpirun}"
export OCTOPUS_PBS_WALLTIME="${OCTOPUS_PBS_WALLTIME:-01:00:00}"
export OCTOPUS_PBS_CMD_TIMEOUT_SECONDS="${OCTOPUS_PBS_CMD_TIMEOUT_SECONDS:-180}"
export OCTOPUS_PMIX_GDS="${OCTOPUS_PMIX_GDS:-hash}"
export OCTOPUS_PMIX_PSEC="${OCTOPUS_PMIX_PSEC:-native}"
export OCTOPUS_PBS_PRECHECK_FREE="${OCTOPUS_PBS_PRECHECK_FREE:-true}"
export OCTOPUS_PBS_BIND_FREE_NODE="${OCTOPUS_PBS_BIND_FREE_NODE:-true}"
export OCTOPUS_RUN_CLEANUP_ENABLED="${OCTOPUS_RUN_CLEANUP_ENABLED:-true}"
export OCTOPUS_RUN_RETENTION_COUNT="${OCTOPUS_RUN_RETENTION_COUNT:-20}"
export OCTOPUS_RUN_MAX_AGE_HOURS="${OCTOPUS_RUN_MAX_AGE_HOURS:-168}"
export OCTOPUS_RUN_KEEP_FAILED="${OCTOPUS_RUN_KEEP_FAILED:-true}"

# Optional outbound proxy for all remote outbound requests
# Priority: GLOBAL_PROXY_URL, then ZCHAT_PROXY_URL (backward compatibility)
PROXY_URL="${GLOBAL_PROXY_URL:-${ZCHAT_PROXY_URL:-}}"
if [ -n "$PROXY_URL" ]; then
    export HTTPS_PROXY="$PROXY_URL"
    export HTTP_PROXY="$PROXY_URL"
    export ALL_PROXY="$PROXY_URL"
    export https_proxy="$PROXY_URL"
    export http_proxy="$PROXY_URL"
    export all_proxy="$PROXY_URL"
    export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1}"
    export no_proxy="${no_proxy:-localhost,127.0.0.1}"
fi

exec "$PYTHON_BIN" server.py
