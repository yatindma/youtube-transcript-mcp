<div align="center">

# 📺 YouTube Transcript MCP

**Give any LLM client instant, unblocked access to YouTube transcripts and search — self-hosted, no third-party API quotas.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![MCP](https://img.shields.io/badge/Protocol-MCP-6b46c1)](https://modelcontextprotocol.io)

</div>

---

## The problem

Plain `youtube_transcript_api` / `yt-dlp` calls from almost any cloud server (VPS, cloud
function, CI runner) get hit with:

```
RequestBlocked / IpBlocked
Sign in to confirm you're not a bot
```

YouTube fingerprints datacenter IP ranges and blocks transcript/caption requests from
them — even with correct headers, cookies, or a fresh proxy. This isn't a bug in the
transcript library; it's an IP-reputation block that no amount of retry logic fixes.

## The fix

Route just this one tool's egress through a **residential VPN (NordVPN OpenVPN)**,
running in its own isolated container — everything else on your host keeps its normal
IP. That's the whole trick. It's implemented here as a small, auditable Docker Compose
stack that anyone can stand up in a few minutes.

## What you get

Two tools, exposed over the [Model Context Protocol](https://modelcontextprotocol.io) via streamable HTTP:

| Tool | What it does |
|---|---|
| `search_videos(query, max_results?)` | Search YouTube — title, url, uploader, upload date, duration, view count. No YouTube Data API key required. |
| `get_transcript(url, lang?, next_cursor?)` | Full transcript text for a video. No 50k-character truncation — get the whole thing. |

Search result → straight into `get_transcript`. That's the whole loop: find a video,
read what's actually said in it.

## Quick start

```bash
git clone <this-repo-url>
cd youtube-transcript-mcp
cp .env.example .env
# edit .env: NordVPN "Service credentials" (dashboard → Manual setup) + a random API key
docker compose up -d --build
```

Point any MCP client at it:

```json
{
  "mcpServers": {
    "youtube-transcript": {
      "type": "http",
      "url": "https://your-domain.example/mcp?key=YOUR_MCP_API_KEY"
    }
  }
}
```

Use `/mcp` (streamable HTTP) — not `/sse` (legacy transport that most current clients,
including the Claude.ai connector, won't connect to).

No Traefik / no domain yet? Skip straight to [Running it standalone](#running-it-standalone-no-traefik).

## Architecture

```
             Claude / any MCP client
                       │  https://your-domain/mcp?key=...
                       ▼
   ┌───────────────────────────────────────────┐
   │                Traefik                     │   (optional — see below)
   │   ① rate limit   ② API-key check   ③ TLS   │──▶ 401 if the key is wrong
   └───────────────────┬─────────────────────────┘
                       │ key OK
                       ▼
   ╔═══════════════════════════════════════════════╗
   ║        isolated Docker network (this stack)     ║
   ║                                                 ║
   ║   ┌─────────────────────────────────────┐      ║
   ║   │  gluetun  (NordVPN OpenVPN tunnel)    │      ║
   ║   └──────────────┬──────────────────────┘      ║
   ║                  │ network_mode: service:*        ║
   ║                  ▼                              ║
   ║   ┌─────────────────────────────────────┐      ║
   ║   │  mcp-youtube-transcript server        │      ║
   ║   │  (mcp-proxy ⇄ stdio MCP process)      │      ║
   ║   └──────────────┬──────────────────────┘      ║
   ╚══════════════════│══════════════════════════════╝
                       │ 🔒 egress via VPN IP, not the host's
                       ▼
                   YouTube
                       │
                       ▼
              transcript / search results
```

Only the containers inside that bubble share the VPN's network. Every other container
on your host — your app, your reverse proxy, anything else — is untouched and keeps
using its normal IP.

## Why a VPN and not a proxy?

In order, what was tried and why it didn't hold up (full detail in
[`docs/why-a-vpn.md`](docs/why-a-vpn.md)):

1. **Direct requests** from the server's own IP → blocked.
2. **Datacenter proxies** (Webshare free tier, 10 IPs) → blocked too — same reason,
   datacenter ASN, regardless of provider.
3. **Rotating proxy gateway** → `429` rate-limited, inconsistent.
4. **NordVPN SOCKS5** → deprecated on NordVPN's current infrastructure; dead on every
   server tested.
5. **NordVPN OpenVPN in an isolated container** → works, reliably, and only affects
   the one container that needs it.

### Already have a VPN subscription? Use it instead of NordVPN

The VPN piece is [gluetun](https://github.com/qdm12/gluetun), which supports 30+
providers out of the box — Surfshark, ExpressVPN, Mullvad, ProtonVPN, Private Internet
Access, IVPN, and more (full list in
[gluetun's docs](https://github.com/qdm12/gluetun-wiki/tree/main/setup)). You don't need
NordVPN specifically:

1. In `docker-compose.yml`, change `VPN_SERVICE_PROVIDER=nordvpn` to your provider's
   name (e.g. `surfshark`, `mullvad`, `expressvpn`).
2. Swap `.env`'s `NORDVPN_OPENVPN_USER`/`PASSWORD` for whatever credential shape your
   provider needs — most are still an OpenVPN username/password, but a few (Mullvad,
   ProtonVPN) use an account number or WireGuard key instead; gluetun's docs list the
   exact env vars per provider.
3. Everything else — the isolated network, Traefik wiring, the MCP server itself —
   stays exactly the same. Only the VPN container's config changes.

## Configuration

All secrets/config live in `.env` (see `.env.example`):

| Variable | Purpose |
|---|---|
| `NORDVPN_OPENVPN_USER` / `NORDVPN_OPENVPN_PASSWORD` | NordVPN "Service credentials" — dashboard → Manual setup, **not** your login password |
| `VPN_SERVER_COUNTRIES` | Which NordVPN country pool to connect through (default `Germany`) |
| `MCP_API_KEY` | Bearer-in-URL key clients must pass as `?key=` |
| `MCP_DOMAIN` | Public hostname Traefik should route (only used if you keep the Traefik labels) |

Other knobs:
- **No transcript truncation** by default — `Dockerfile` passes `--response-limit -1`.
- **Rate limit** — `RATE_LIMIT_PER_MIN` / `RATE_LIMIT_BURST` (Traefik path only).

## Running it standalone (no Traefik)

Don't have a reverse proxy? Remove the `networks:`/`labels:` blocks from
`mcp-youtube-transcript-vpn` in `docker-compose.yml` and add:

```yaml
ports:
  - "3003:3003"
```

The MCP server is now reachable at `http://your-host:3003/mcp` directly. Put it behind
your own TLS terminator (Caddy, nginx, Cloudflare Tunnel) or use it over plain HTTP on a
private network.

## Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| Client says "couldn't connect" / "invalid MCP server" | Using `/sse` instead of `/mcp` | Fix the URL — `/mcp` is the streamable-HTTP endpoint modern clients expect |
| `401` on every request, even with the right key | authcheck not receiving the key, or key mismatch | `docker logs mcp-youtube-transcript-authcheck --tail 20` |
| `IpBlocked` / `RequestBlocked` | VPN tunnel is down | `docker logs mcp-youtube-transcript-vpn --tail 30` — look for `AUTH_FAILED` or repeated reconnects |
| `mcp-youtube-transcript` stuck in `Created` | VPN container never went healthy | `docker inspect mcp-youtube-transcript-vpn --format '{{.State.Health.Status}}'` |
| `AUTH_FAILED` in gluetun logs | NordVPN service credentials expired/rotated | Regenerate "Service credentials" in the NordVPN dashboard and update `.env` |
| Want to confirm the VPN is actually in use | — | `docker exec mcp-youtube-transcript-vpn wget -qO- https://ipv4.icanhazip.com` should show the VPN's IP, not your host's |

## Why self-host this instead of a hosted API

- No per-request billing, no third-party quota to watch.
- Full transcripts, no arbitrary truncation.
- The VPN egress is yours — no shared IP pool getting rate-limited by someone else's traffic.
- ~30 lines of Python, two Docker Compose files. Nothing here is a black box.

## Contributing

Issues and PRs welcome — this is a small, focused project and easy to review end to end.
If you hit a YouTube-blocking scenario this setup doesn't handle, open an issue with the
error text; that's the most useful bug report you can give.

If this saved you the afternoon of proxy/VPN debugging it took to build, a ⭐ helps
other people find it.

## License

MIT — see [LICENSE](LICENSE).
