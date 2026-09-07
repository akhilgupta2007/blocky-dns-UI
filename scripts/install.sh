#!/usr/bin/env bash
# BlockyDNS Hub - 1-Command Automated Installer for Raspberry Pi & Linux
set -e

echo "=========================================================="
echo "🛡️  Installing BlockyDNS Hub on Raspberry Pi / Linux Host"
echo "=========================================================="

# 1. Check Root
if [ "$EUID" -ne 0 ]; then
  echo "[-] Please run as root: sudo bash install.sh"
  exit 1
fi

# 2. Check Directory or Clone
INSTALL_DIR="/opt/blocky-dns"
if [ ! -f "docker-compose.yml" ]; then
  if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
    echo "[+] Found existing installation at $INSTALL_DIR. Navigating there..."
    cd "$INSTALL_DIR"
  else
    echo "[+] Cloning BlockyDNS Hub repository to $INSTALL_DIR..."
    if ! command -v git >/dev/null 2>&1; then
      apt-get update -y && apt-get install -y git
    fi
    REPO_URL="${BLOCKY_REPO_URL:-https://github.com/akhil/blocky-dns-UI.git}"
    git clone "$REPO_URL" "$INSTALL_DIR" || true
    cd "$INSTALL_DIR"
  fi
fi

# 3. Check Docker and Docker Compose
if ! command -v docker >/dev/null 2>&1; then
  echo "[+] Installing Docker Engine..."
  curl -fsSL https://get.docker.com | sh
  if [ -n "$SUDO_USER" ]; then
    usermod -aG docker "$SUDO_USER" || true
  fi
  systemctl enable docker
  systemctl start docker
fi

# 4. Check Port 53 conflict (systemd-resolved)
if lsof -Pi :53 -sTCP:LISTEN -t >/dev/null 2>&1 || ss -lntu | grep -q ':53 '; then
  echo "[!] Port 53 is currently occupied (often by systemd-resolved DNS stub listener)."
  echo "[+] Disabling systemd-resolved stub listener to allow Blocky to bind to port 53..."
  mkdir -p /etc/systemd/resolved.conf.d/
  cat << 'EOF' > /etc/systemd/resolved.conf.d/blockydns.conf
[Resolve]
DNS=127.0.0.1
DNSStubListener=no
EOF
  systemctl restart systemd-resolved || true
fi

# 5. Prepare Directories and Permissions Automatically (Zero manual steps)
echo "[+] Preparing directories and volume permissions..."
mkdir -p data certs config
chmod -R 777 data certs config 2>/dev/null || true

# 6. Ensure default config.yml exists
if [ ! -f "config/config.yml" ] && [ -f "config/config.example.yml" ]; then
  echo "[+] Initializing config/config.yml from default template..."
  cp config/config.example.yml config/config.yml
fi

if [ -f "config/config.yml" ]; then
  chmod 666 config/config.yml 2>/dev/null || true
  sed -i 's|target:.*|target: /app/data/blockydns.db|' config/config.yml 2>/dev/null || true
fi

# 7. Launch Containers
echo "[+] Pulling images and launching BlockyDNS Hub..."
if docker compose version >/dev/null 2>&1; then
  docker compose up -d --build
else
  docker-compose up -d --build
fi

HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$HOST_IP" ]; then
  HOST_IP="127.0.0.1"
fi

echo ""
echo "=========================================================="
echo "🎉 BlockyDNS Hub is now running!"
echo "   Secured Web UI (HTTPS): https://${HOST_IP}:3443"
echo "   Unencrypted Web UI:     http://${HOST_IP}:3000 (Redirects to HTTPS)"
echo "   DNS Listener (Port 53): ${HOST_IP}:53"
echo "   Zero manual chmod or volume configuration needed."
echo "=========================================================="
