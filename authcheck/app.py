import os
from urllib.parse import urlparse, parse_qs

from fastapi import FastAPI, Request, Response

API_KEY = os.environ["MCP_API_KEY"]

app = FastAPI()


@app.get("/verify")
async def verify(request: Request) -> Response:
    # Traefik ForwardAuth doesn't forward the original query string onto the
    # /verify request itself, but it does pass it via X-Forwarded-Uri.
    forwarded_uri = request.headers.get("x-forwarded-uri", "")
    key = parse_qs(urlparse(forwarded_uri).query).get("key", [None])[0]
    if key != API_KEY:
        return Response(status_code=401)
    return Response(status_code=200)
