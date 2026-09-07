#!/bin/sh
set -e

# Ensure a permissive umask so files/dirs created by Python and Blocky are freely accessible
umask 0000

# Ensure target volume directories exist inside the container
mkdir -p /app/data /app/certs /app/config

# Self-heal permissions on mounted host volumes silently
chmod -R 777 /app/data /app/certs /app/config 2>/dev/null || true

# If config.yml does not exist, initialize it from config.example.yml
if [ ! -f "/app/config/config.yml" ]; then
  if [ -f "/app/config/config.example.yml" ]; then
    echo "[Entrypoint] Initializing default /app/config/config.yml from template..."
    cp /app/config/config.example.yml /app/config/config.yml
  fi
fi

# Ensure config.yml is readable and writable across containers
if [ -f "/app/config/config.yml" ]; then
  chmod 666 /app/config/config.yml 2>/dev/null || true
fi

# Hand off execution to the main container command (CMD in Dockerfile)
exec "$@"
