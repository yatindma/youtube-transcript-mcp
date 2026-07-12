# Why a VPN, not a proxy — the full story

This documents every approach that was actually tried while building this project, in
the order they were tried, including the ones that failed. If you're debugging your own
YouTube-IP-block issue, this should save you from repeating the same dead ends.

## The symptom

Running from a plain cloud VPS, both of the common Python libraries fail the same way:

```python
# youtube_transcript_api
RequestBlocked()
IpBlocked()

# yt-dlp
ERROR: [youtube] <id>: Sign in to confirm you're not a bot.
```

This is YouTube blocking the **server's IP address**, not anything about the request
itself. No header, cookie, or user-agent change fixes it, because the block is keyed on
IP reputation, not request fingerprint.

## Attempt 1 — Webshare free-tier datacenter proxies

[Webshare](https://www.webshare.io/) gives 10 free proxies on signup. These are
**datacenter proxies** (hosted on providers like Leaseweb, ColoCrossing, ServerMania,
HostRoyale). Verified against Webshare's own API that the account, credentials, and
IP-authorization were all correctly configured — the proxies worked fine for general
HTTP requests (`https://ipv4.webshare.io/` returned 200 through them).

Result against YouTube's transcript endpoint specifically: `IpBlocked` on every single
one. YouTube blocks the same datacenter ASN ranges these ISPs sit in, regardless of
which proxy reseller sits on top of them. This is a fundamental limit of the free
tier, not a config mistake — **datacenter IPs don't work for this, full stop, whichever
provider they come from.**

## Attempt 2 — Webshare's rotating gateway (`WebshareProxyConfig`)

`youtube_transcript_api` ships a `WebshareProxyConfig` helper that points at Webshare's
rotating endpoint (`p.webshare.io`) instead of a single fixed proxy IP. This behaved
differently — instead of an immediate block, it returned `429` (rate-limited) after
retries. Better signal (means some requests were getting through), but not reliable
enough to build on for a hosted service other people depend on.

## Attempt 3 — Webshare *paid residential* proxies

**This is the path that would most likely have worked without switching to a VPN at
all** — Webshare (and similar providers) sell residential/ISP proxy plans starting
around $2.99/mo, which route through real consumer ISP IP ranges rather than datacenter
ranges. YouTube generally does not block these the way it blocks datacenter IPs, because
a residential IP is indistinguishable from an ordinary user's home connection.

If you'd rather pay a few dollars a month than run a VPN container, this is a legitimate
alternative: sign up for a residential/ISP plan, and set `HTTP_PROXY`/`HTTPS_PROXY` (or
the library's native `WebshareProxyConfig`) to point at it instead of running gluetun at
all. It's simpler — one fewer container, no VPN credential management — and was not
pursued further here only because a VPN subscription was already available, not because
it doesn't work.

## Attempt 4 — NordVPN SOCKS5

NordVPN historically offered SOCKS5 proxy endpoints. As of testing, every server tried
(multiple `*.nordvpn.com:1080` servers across several countries) either timed out or
rejected the credentials outright. NordVPN's own documentation confirms SOCKS5 has been
deprecated across current infrastructure — this is not fixable client-side.

## Attempt 5 — SSH reverse tunnel through a personal laptop

Works: `ssh -N -R 1080:localhost:0 user@vps` turns a laptop's residential connection
into a SOCKS proxy the VPS can use. The catch is obvious — the tool's uptime becomes
tied to a laptop being powered on and connected, which defeats the point of hosting it
on a server at all. Fine for one-off manual testing, not for something meant to run
unattended.

## What actually shipped — NordVPN OpenVPN in an isolated container

[gluetun](https://github.com/qdm12/gluetun) running NordVPN's OpenVPN protocol (not
SOCKS5), in its own container, with only the MCP server's container attached to its
network namespace via `network_mode: "service:..."`. This:

- Reliably avoids the IP block (residential/consumer-facing VPN egress IPs).
- Runs unattended, 24/7, survives reboots (`restart: unless-stopped`).
- Only affects the one container that needs it — nothing else on the host's network
  changes.

It required one specific fix during setup: NordVPN's "Service credentials" (dashboard →
Manual setup tab) are the correct credential type for this — NordVPN account
login/password will not work for OpenVPN auth. If gluetun logs show `AUTH_FAILED`,
that's almost always either using the wrong credential type or a stale/regenerated
credential — see the main README's troubleshooting table.

## Summary table

| Approach | Cost | Result |
|---|---|---|
| Direct from VPS | Free | Blocked |
| Webshare free datacenter proxy | Free | Blocked |
| Webshare rotating gateway | Free | Rate-limited, unreliable |
| Webshare paid residential proxy | ~$3+/mo | Likely works (not needed once VPN was available) |
| NordVPN SOCKS5 | N/A | Deprecated, doesn't connect |
| SSH tunnel via laptop | Free | Works, but requires the laptop to stay on |
| NordVPN OpenVPN, isolated container | Existing VPN subscription | **Works reliably, unattended** |
