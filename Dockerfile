# Builds a patched jkawamoto/mcp-youtube-transcript (stdio MCP server, get_transcript
# tool only — get_timed_transcript/get_video_info/get_available_languages removed) and
# fronts it with mcp-proxy so it can sit behind Traefik like our other MCP services.
FROM python:3.13-slim-bookworm

WORKDIR /app

COPY vendor/mcp-youtube-transcript /app/mcp-youtube-transcript

RUN pip install --no-cache-dir \
    /app/mcp-youtube-transcript \
    "mcp-proxy>=0.4"

EXPOSE 3003

# --response-limit -1 disables pagination: full transcript, never truncated.
ENTRYPOINT ["mcp-proxy", "--port", "3003", "--host", "0.0.0.0", "--", \
    "mcp-youtube-transcript", "--response-limit", "-1"]
