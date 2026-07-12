# Contributing

This is a small, focused project — two Docker Compose services and a ~150-line Python
patch on top of [jkawamoto/mcp-youtube-transcript](https://github.com/jkawamoto/mcp-youtube-transcript).
Contributions are welcome, and the whole thing is small enough to review end to end in
one sitting.

## Reporting a bug

The most useful bug report includes:

1. Which tool you called (`get_transcript` or `search_videos`) and the arguments.
2. The exact error text.
3. Output of `docker logs mcp-youtube-transcript-vpn --tail 30` if the error looks
   YouTube-blocking-related (`IpBlocked`, `RequestBlocked`, `Sign in to confirm you're
   not a bot`).

Check the [troubleshooting table](README.md#troubleshooting) first — VPN auth issues
and `/sse` vs `/mcp` mixups account for most reported issues.

## Proposing a change

- Changes to the MCP server itself live in
  `vendor/mcp-youtube-transcript/src/mcp_youtube_transcript/__init__.py`. This is a
  vendored + patched copy of the upstream project (not a git submodule), so edits go
  directly in this repo.
- Changes to deployment/infra go in `docker-compose.yml` / `Dockerfile` /
  `authcheck/`.
- If you're adding a new tool, follow the existing pattern: a small Pydantic model for
  the return type, a `_helper` function that does the work, and an `@mcp.tool()` wrapper
  that's just argument marshalling. Keep tool descriptions short and the docstring as the
  tool description an LLM will see.

## Local testing

```bash
docker compose build
docker compose up -d
docker logs -f mcp-youtube-transcript
```

To exercise a tool call without a full MCP client, you can use `curl` against the
`streamablehttp` endpoint — see the example `initialize` → `tools/call` sequence in
[`docs/why-a-vpn.md`](docs/why-a-vpn.md) for the request shape.

## What's especially useful to contribute

- Reports of YouTube-blocking behavior this setup doesn't handle (new block patterns,
  new error strings) — these keep the troubleshooting table accurate.
- Support for additional gluetun-backed VPN providers being documented with exact env
  var mappings, if you've verified one beyond what's already listed.
- Anything that reduces the container count or simplifies the network wiring without
  losing the isolation property (only the MCP server's traffic goes through the VPN).
