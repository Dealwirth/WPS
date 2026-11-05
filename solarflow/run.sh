#!/usr/bin/env bash
# SolarFlow Add-on Starter.
#
# Die s6-Init des HA-Basisimages reicht die per ``-e`` gesetzten Variablen
# (u. a. SUPERVISOR_TOKEN) nicht automatisch an dieses Skript weiter. Sie
# liegen aber in /run/s6/container_environment. Wir laden sie daher explizit,
# damit der Server den Supervisor-Token sicher erhaelt.
set -e

if [ -d /run/s6/container_environment ]; then
  for f in /run/s6/container_environment/*; do
    [ -f "$f" ] || continue
    name="$(basename "$f")"
    value="$(cat "$f")"
    export "$name=$value"
  done
fi

OPTIONS="${SOLARFLOW_OPTIONS_FILE:-/data/options.json}"
if [ ! -f "$OPTIONS" ]; then
  echo '{}' > "$OPTIONS"
fi

export SOLARFLOW_OPTIONS_FILE="$OPTIONS"
export SOLARFLOW_DATA_DIR="${SOLARFLOW_DATA_DIR:-/data}"
export SOLARFLOW_PORT="${SOLARFLOW_PORT:-8099}"

echo "[SolarFlow] Starte Server auf Port ${SOLARFLOW_PORT} ..."
exec python3 -u /app/server.py
