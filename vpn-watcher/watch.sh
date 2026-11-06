#!/bin/sh
# Restarts mcp-youtube-transcript whenever mcp-youtube-transcript-vpn (re)starts.
#
# Why this exists: mcp-youtube-transcript uses `network_mode: service:mcp-youtube-transcript-vpn`,
# so it shares the VPN container's network namespace. When the VPN container restarts
# (autoheal recovering from a stuck NordVPN server, or any other reason), Docker gives it
# a new network namespace but does NOT restart containers attached via network_mode —
# they're left pointing at a namespace that no longer routes anywhere, so the service goes
# unreachable from outside even though its own process is still running (its healthcheck
# hits 127.0.0.1, which always succeeds from inside the dead namespace).
set -eu

# Second job: YouTube flags VPN IPs as bots. On that error, restart the VPN so it picks a
# new server; the events loop below then restarts the MCP. Limits stop a restart loop.
COOLDOWN=900
MAX_PER_HOUR=3
ROTATIONS=/tmp/vpn-rotations

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }

rotate_vpn() {
  now=$(date +%s)
  last=$(tail -n 1 "$ROTATIONS")
  if [ $((now - ${last:-0})) -lt "$COOLDOWN" ]; then
    log "bot error, cooldown active, not rotating"
    return 0
  fi
  recent=$(awk -v since=$((now - 3600)) '$1 > since { n++ } END { print n + 0 }' "$ROTATIONS")
  if [ "$recent" -ge "$MAX_PER_HOUR" ]; then
    log "bot error, hourly limit reached, not rotating"
    return 0
  fi
  echo "$now" >> "$ROTATIONS"
  log "bot error, restarting VPN for a new IP"
  docker restart mcp-youtube-transcript-vpn || log "VPN restart failed"
}

watch_bot_errors() {
  : > "$ROTATIONS"
  while true; do
    # docker logs exits when the MCP restarts, so reconnect from the current time.
    docker logs -f --since "$(date -u +%Y-%m-%dT%H:%M:%SZ)" mcp-youtube-transcript 2>&1 |
    while IFS= read -r line; do
      case "$line" in
        *"Sign in to confirm"*) rotate_vpn ;;
      esac
    done || true
    sleep 2
  done
}

watch_bot_errors &

docker events \
  --filter "container=mcp-youtube-transcript-vpn" \
  --filter "event=start" \
  --format '{{json .}}' |
while read -r _; do
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) vpn container (re)started, restarting mcp-youtube-transcript"
  docker restart mcp-youtube-transcript || true
done
