#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# vm-lmstudio-init.sh
#
# Runs INSIDE the Azure VM to set up a headless OpenAI-compatible inference
# server using Ollama (drop-in replacement for LM Studio's server API).
#
# Why Ollama instead of LM Studio GUI?
#   LM Studio has no stable headless Linux installer URL. Ollama provides the
#   exact same /v1/chat/completions + /v1/models API, runs as a systemd service,
#   and is the standard choice for headless Linux inference.
#
# Model: phi3:mini (3.8B, ~2.2 GB) — fits Standard_D2s_v3 (8 GB RAM)
# Port : 11434  → orchestrator calls http://<vm-ip>:11434/v1
#
# This script is uploaded and run by azure-vm-create.sh automatically.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

OLLAMA_PORT=11434
MODEL="phi3:mini"       # 3.8B Phi-3-mini — fast, small, OpenAI-function-calling capable

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ── 1. System packages ────────────────────────────────────────────────────────
log "Updating system packages …"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends curl ca-certificates > /dev/null 2>&1
log "System packages ✓"

# ── 2. Install Ollama ─────────────────────────────────────────────────────────
log "Installing Ollama …"
curl -fsSL https://ollama.com/install.sh | sh
log "Ollama installed ✓"

# ── 3. Configure Ollama to listen on all interfaces ──────────────────────────
log "Configuring Ollama service …"
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf > /dev/null << 'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF

sudo systemctl daemon-reload
sudo systemctl enable ollama
sudo systemctl restart ollama
sleep 5
log "Ollama service configured ✓"

# ── 4. Pull the model ─────────────────────────────────────────────────────────
log "Pulling model: $MODEL (~2.2 GB, may take 5-10 min) …"
ollama pull "$MODEL"
log "Model download complete ✓"

# ── 5. Smoke test ─────────────────────────────────────────────────────────────
log "Running smoke test …"
for i in {1..12}; do
  if curl -sf "http://localhost:${OLLAMA_PORT}/v1/models" | python3 -c \
      "import sys,json; d=json.load(sys.stdin); [print('  model:', m['id']) for m in d.get('data',[])]" 2>/dev/null; then
    log "Ollama server healthy ✓"
    break
  fi
  log "Waiting for server … (attempt $i/12)"
  sleep 10
done

# ── 6. Summary ────────────────────────────────────────────────────────────────
PUBLIC_IP=$(curl -s https://api.ipify.org 2>/dev/null || echo "<vm-public-ip>")
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Ollama inference server setup COMPLETE"
echo ""
echo "  Endpoint  : http://${PUBLIC_IP}:${OLLAMA_PORT}/v1"
echo "  Model     : $MODEL"
echo ""
echo "  Service   : sudo systemctl status ollama"
echo "  Logs      : journalctl -u ollama -f"
echo ""
echo "  Test from your Mac:"
echo "    curl http://${PUBLIC_IP}:${OLLAMA_PORT}/v1/models"
echo ""
echo "  Update your .env:"
echo "    LM_STUDIO_URL=http://${PUBLIC_IP}:${OLLAMA_PORT}/v1"
echo "    LM_STUDIO_MODEL=phi3:mini"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
