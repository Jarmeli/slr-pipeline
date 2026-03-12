#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# azure-vm-create.sh
#
# Provisions a budget Azure VM for running LM Studio (headless) as the
# OpenAI-compatible inference backend for the SLR pipeline.
#
# Tier: Standard_D2s_v3  (2 vCPU / 8 GB RAM) — validated available in canadacentral
#       for Azure Student. Fits Phi-3-mini GGUF Q4_K_M (~2.2 GB model, ~5-6 GB total).
#
# Usage:
#   chmod +x scripts/azure-vm-create.sh
#   ./scripts/azure-vm-create.sh          # interactive: prompts for your IP
#   MY_IP=1.2.3.4 ./scripts/azure-vm-create.sh   # non-interactive
#
# Prerequisites:
#   - Azure CLI installed  (brew install azure-cli)
#   - Logged in:           az login
#   - Student subscription selected (az account set --subscription <id>)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config — edit these if needed ────────────────────────────────────────────
RG="slr-lmstudio-rg"
LOCATION="canadacentral"   # Matches PostgreSQL DB region; allowed by student subscription
VM_NAME="slr-lmstudio-vm"
VM_SIZE="Standard_D2s_v3"  # 2 vCPU / 8 GB RAM — validated available in canadacentral for student sub
OS_IMAGE="Ubuntu2204"
ADMIN_USER="azureuser"
SSH_KEY_PATH="$HOME/.ssh/slr_lmstudio_rsa"
LM_PORT=1234

# ── Detect your public IP for a tight NSG rule (no open-to-internet) ─────────
if [[ -z "${MY_IP:-}" ]]; then
  MY_IP=$(curl -s https://api.ipify.org)
  echo "Detected your public IP: $MY_IP"
  read -rp "Use this IP to restrict port $LM_PORT access? [Y/n] " CONFIRM
  CONFIRM="${CONFIRM:-Y}"
  if [[ "$CONFIRM" =~ ^[Nn]$ ]]; then
    MY_IP="*"
    echo "WARNING: Port $LM_PORT will be open to the internet. Change the NSG rule after setup."
  fi
fi

# ── Generate SSH key pair if it doesn't exist ────────────────────────────────
if [[ ! -f "$SSH_KEY_PATH" ]]; then
  echo "Generating SSH key at $SSH_KEY_PATH …"
  ssh-keygen -t rsa -b 4096 -f "$SSH_KEY_PATH" -N "" -C "slr-lmstudio"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Creating Azure resources in: $LOCATION"
echo "  Resource group : $RG"
echo "  VM             : $VM_NAME ($VM_SIZE)"
echo "  OS             : Ubuntu 22.04 LTS"
echo "  Admin user     : $ADMIN_USER"
echo "  LM Studio port : $LM_PORT → allowed from $MY_IP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 1. Resource Group ─────────────────────────────────────────────────────────
echo "[1/5] Creating resource group …"
az group create \
  --name "$RG" \
  --location "$LOCATION" \
  --output none

# ── 2. VM ─────────────────────────────────────────────────────────────────────
echo "[2/5] Provisioning VM (this takes ~2 min) …"
az vm create \
  --resource-group "$RG" \
  --name "$VM_NAME" \
  --size "$VM_SIZE" \
  --image "$OS_IMAGE" \
  --admin-username "$ADMIN_USER" \
  --ssh-key-values "${SSH_KEY_PATH}.pub" \
  --public-ip-sku Standard \
  --os-disk-size-gb 32 \
  --output json \
  | tee /tmp/az_vm_create.json

PUBLIC_IP=$(jq -r '.publicIpAddress' /tmp/az_vm_create.json)

# ── 3. NSG rules ──────────────────────────────────────────────────────────────
echo "[3/5] Configuring firewall rules …"

# Allow LM Studio API port only from your IP
az vm open-port \
  --resource-group "$RG" \
  --name "$VM_NAME" \
  --port "$LM_PORT" \
  --priority 1010 \
  --output none

# Tighten rule to only allow from MY_IP
NSG=$(az network nsg list --resource-group "$RG" --query "[0].name" -o tsv)
az network nsg rule update \
  --resource-group "$RG" \
  --nsg-name "$NSG" \
  --name "open-port-${LM_PORT}" \
  --source-address-prefixes "$MY_IP" \
  --output none

echo "[3/5] NSG: port $LM_PORT → $MY_IP ✓"

# ── 4. Copy VM init script and run it ────────────────────────────────────────
echo "[4/5] Uploading and running VM init script …"

# Wait for SSH to be ready
sleep 15
ssh-keyscan -H "$PUBLIC_IP" >> ~/.ssh/known_hosts 2>/dev/null

scp -i "$SSH_KEY_PATH" \
  "$(dirname "$0")/vm-lmstudio-init.sh" \
  "${ADMIN_USER}@${PUBLIC_IP}:/home/${ADMIN_USER}/vm-lmstudio-init.sh"

ssh -i "$SSH_KEY_PATH" "${ADMIN_USER}@${PUBLIC_IP}" \
  "chmod +x /home/${ADMIN_USER}/vm-lmstudio-init.sh && \
   nohup bash /home/${ADMIN_USER}/vm-lmstudio-init.sh > /home/${ADMIN_USER}/lmstudio-setup.log 2>&1 &"

echo "[4/5] Init script running in background on VM."
echo "      Monitor: ssh -i $SSH_KEY_PATH ${ADMIN_USER}@${PUBLIC_IP} 'tail -f ~/lmstudio-setup.log'"

# ── 5. Print connection info ─────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[5/5] DONE — connection details"
echo ""
echo "  VM Public IP   : $PUBLIC_IP"
echo "  SSH access     : ssh -i $SSH_KEY_PATH ${ADMIN_USER}@${PUBLIC_IP}"
echo ""
echo "  LM Studio URL  : http://${PUBLIC_IP}:${LM_PORT}/v1"
echo ""
echo "  Next step — update your .env:"
echo "    LM_STUDIO_URL=http://${PUBLIC_IP}:${LM_PORT}/v1"
echo "    LM_STUDIO_MODEL=lmstudio-community/Phi-3-mini-4k-instruct-GGUF/Phi-3-mini-4k-instruct-Q4_K_M.gguf"
echo ""
echo "  Setup log (wait ~5 min for model download):"
echo "    ssh -i $SSH_KEY_PATH ${ADMIN_USER}@${PUBLIC_IP} 'tail -f ~/lmstudio-setup.log'"
echo ""
echo "  Stop the VM when not in use to save credits:"
echo "    az vm deallocate --resource-group $RG --name $VM_NAME"
echo "  Restart:"
echo "    az vm start --resource-group $RG --name $VM_NAME"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Write IP to a local file for other scripts to use
echo "$PUBLIC_IP" > "$(dirname "$0")/.vm_public_ip"
