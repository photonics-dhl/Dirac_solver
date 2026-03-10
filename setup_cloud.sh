#!/usr/bin/env bash
# setup_cloud.sh — One-time bootstrap for Ubuntu 24.04 ECS instance
# Run as: sudo bash setup_cloud.sh
# After running: edit .env with your values, then ./start_all.sh
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUBLIC_IP="${1:-$(curl -s ifconfig.me)}"

echo "=== Dirac Solver Cloud Setup ==="
echo "    Repo:      $REPO_DIR"
echo "    Public IP: $PUBLIC_IP"
echo ""

# ── System packages ────────────────────────────────────────────────
echo "[1/7] Installing system packages..."
apt-get update -qq
apt-get install -y curl git python3 python3-pip python3-venv build-essential

# ── Docker ────────────────────────────────────────────────────────
echo "[2/7] Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | bash
    usermod -aG docker ubuntu || true
fi
systemctl enable docker
systemctl start docker

# ── Node.js 20 LTS ────────────────────────────────────────────────
echo "[3/7] Installing Node.js 20..."
if ! command -v node &>/dev/null || [[ "$(node -v)" != v20* ]]; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi

# ── Python deps ───────────────────────────────────────────────────
echo "[4/7] Installing Python dependencies..."
pip3 install --break-system-packages \
    fastapi uvicorn httpx \
    numpy matplotlib scipy \
    mcp python-dotenv \
    jinja2 xarray netCDF4 h5py

# ── npm deps ──────────────────────────────────────────────────────
echo "[5/7] Installing Node.js dependencies..."
cd "$REPO_DIR"
npm install
cd "$REPO_DIR/frontend"
npm install
cd "$REPO_DIR"

# ── Build Docker image ────────────────────────────────────────────
echo "[6/7] Building Octopus Docker image..."
cd "$REPO_DIR/docker"
docker build -t octopus-mcp-server:latest .
cd "$REPO_DIR"

# ── Environment config ────────────────────────────────────────────
echo "[7/7] Creating .env from template..."
if [ ! -f "$REPO_DIR/.env" ]; then
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    # Patch Linux cloud values
    sed -i "s|WORKSPACE_ROOT=.*|WORKSPACE_ROOT=$REPO_DIR|" "$REPO_DIR/.env"
    sed -i "s|OCTOPUS_OUTPUT_DIR=.*|OCTOPUS_OUTPUT_DIR=$REPO_DIR/@Octopus_docs/output|" "$REPO_DIR/.env"
    sed -i "s|VISIT_EXE=visit|VISIT_EXE=visit|" "$REPO_DIR/.env"  # bare name, rely on PATH
fi

# Frontend env
if [ ! -f "$REPO_DIR/frontend/.env.local" ]; then
    cat > "$REPO_DIR/frontend/.env.local" <<EOF
VITE_API_BASE_URL=http://${PUBLIC_IP}:3001
VITE_MCP_BASE_URL=http://${PUBLIC_IP}:8000
EOF
fi

# ── Create logs and output dirs ─────────────────────────────────
mkdir -p "$REPO_DIR/logs"
mkdir -p "$REPO_DIR/@Octopus_docs/output/gs"
mkdir -p "$REPO_DIR/@Octopus_docs/output/td"
mkdir -p "$REPO_DIR/@Octopus_docs/output/renders"

# ── UFW firewall ───────────────────────────────────────────────────
echo "Opening firewall ports (UFW)..."
ufw allow 22/tcp   || true
ufw allow 3001/tcp || true
ufw allow 5173/tcp || true
ufw allow 8000/tcp || true
ufw --force enable || true

echo ""
echo "=== Setup complete! ==="
echo ""
echo "IMPORTANT: Also open these ports in Alibaba Cloud Security Group console:"
echo "  TCP 3001 (Node API), TCP 5173 (Frontend), TCP 8000 (Octopus MCP)"
echo ""
echo "Next steps:"
echo "  1. Edit $REPO_DIR/.env and add your ZCHAT_API_KEY"
echo "  2. Run: ./start_all.sh"
echo "  3. Frontend: http://${PUBLIC_IP}:5173"
