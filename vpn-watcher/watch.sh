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

docker events \
  --filter "container=mcp-youtube-transcript-vpn" \
  --filter "event=start" \
  --format '{{json .}}' |
while read -r _; do
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) vpn container (re)started, restarting mcp-youtube-transcript"
  docker restart mcp-youtube-transcript || true
done
