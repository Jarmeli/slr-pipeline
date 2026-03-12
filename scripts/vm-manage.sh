#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# vm-manage.sh  —  Start / stop / SSH / status helpers for the LM Studio VM
#
# Usage:
#   ./scripts/vm-manage.sh start    # start (or un-deallocate) the VM
#   ./scripts/vm-manage.sh stop     # deallocate VM (stops billing)
#   ./scripts/vm-manage.sh ssh      # open an SSH session
#   ./scripts/vm-manage.sh status   # show VM state + LM Studio health
#   ./scripts/vm-manage.sh ip       # print current public IP
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

RG="slr-lmstudio-rg"
VM_NAME="slr-lmstudio-vm"
ADMIN_USER="azureuser"
SSH_KEY="$HOME/.ssh/slr_lmstudio_rsa"
LM_PORT=11434   # Ollama inference server (OpenAI-compatible)

get_ip() {
  az vm list-ip-addresses \
    --resource-group "$RG" \
    --name "$VM_NAME" \
    --query "[0].virtualMachine.network.publicIpAddresses[0].ipAddress" \
    -o tsv 2>/dev/null
}

CMD="${1:-status}"

case "$CMD" in
  start)
    echo "Starting VM $VM_NAME …"
    az vm start --resource-group "$RG" --name "$VM_NAME" --no-wait
    echo "VM start issued. Run './scripts/vm-manage.sh status' to check."
    ;;

  stop)
    echo "Deallocating VM $VM_NAME (stops billing) …"
    az vm deallocate --resource-group "$RG" --name "$VM_NAME" --no-wait
    echo "Deallocation issued. Billing stops once state = Deallocated."
    ;;

  ssh)
    IP=$(get_ip)
    echo "Connecting to ${ADMIN_USER}@${IP} …"
    ssh -i "$SSH_KEY" "${ADMIN_USER}@${IP}"
    ;;

  ip)
    get_ip
    ;;

  status)
    STATE=$(az vm get-instance-view \
      --resource-group "$RG" \
      --name "$VM_NAME" \
      --query "instanceView.statuses[1].displayStatus" -o tsv 2>/dev/null)
    echo "VM state: $STATE"

    if [[ "$STATE" == "VM running" ]]; then
      IP=$(get_ip)
      echo "Public IP: $IP"
      echo ""
      if curl -sf --max-time 5 "http://${IP}:${LM_PORT}/v1/models" > /dev/null 2>&1; then
        echo "Ollama: HEALTHY at http://${IP}:${LM_PORT}/v1"
        curl -s "http://${IP}:${LM_PORT}/v1/models" | jq -r '.data[].id' 2>/dev/null | sed 's/^/  model: /'
      else
        echo "Ollama: not responding on port $LM_PORT (still starting?)"
        echo "  SSH and check: sudo systemctl status ollama"
      fi
    fi
    ;;

  *)
    echo "Usage: $0 {start|stop|ssh|ip|status}"
    exit 1
    ;;
esac
