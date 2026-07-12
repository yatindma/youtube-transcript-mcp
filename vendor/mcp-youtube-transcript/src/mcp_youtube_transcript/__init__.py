#  __init__.py
#
#  Copyright (c) 2025-2026 Junpei Kawamoto
#
#  This software is released under the MIT License.
#
#  http://opensource.org/licenses/mit-license.php
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache, partial
from itertools import islice
from typing import Any, AsyncIterator, Tuple
from typing import Final
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from mcp import ServerSession
from mcp.server import FastMCP
from mcp.server.fastmcp import Context
from pydantic import Field, BaseModel, AwareDatetime
from youtube_transcript_api import YouTubeTranscriptApi, FetchedTranscriptSnippet
from youtube_transcript_api.proxies import WebshareProxyConfig, GenericProxyConfig, ProxyConfig
from yt_dlp import YoutubeDL
from yt_dlp.extractor.youtube import YoutubeIE, YoutubeSearchIE


@dataclass(frozen=True)
class AppContext:
    http_client: requests.Session
    ytt_api: YouTubeTranscriptApi
    dlp: YoutubeDL


@asynccontextmanager
async def _app_lifespan(_server: FastMCP, proxy_config: ProxyConfig | None) -> AsyncIterator[AppContext]:
    ytdlp_params: dict[str, Any] = {"quiet": True}
    if proxy_config is not None:
        proxy_dict = proxy_config.to_requests_dict()
        proxy_url = proxy_dict.get("https") or proxy_dict.get("http")
        if proxy_url:
            ytdlp_params["proxy"] = proxy_url

    with requests.Session() as http_client, YoutubeDL(params=ytdlp_params, auto_init=False) as dlp:
        dlp.add_info_extractor(YoutubeIE())
        dlp.add_info_extractor(YoutubeSearchIE())
        ytt_api = YouTubeTranscriptApi(http_client=http_client, proxy_config=proxy_config)
        yield AppContext(http_client=http_client, ytt_api=ytt_api, dlp=dlp)


class Transcript(BaseModel):
    """Transcript of a YouTube video."""

    title: str = Field(description="Title of the video")
    transcript: str = Field(description="Transcript of the video")
    next_cursor: str | None = Field(description="Cursor to retrieve the next page of the transcript", default=None)


class SearchResult(BaseModel):
    """A single YouTube search result."""

    title: str = Field(description="Title of the video")
    url: str = Field(description="URL of the video")
    uploader: str = Field(description="Channel that uploaded the video")
    upload_date: AwareDatetime | None = Field(description="When the video was uploaded", default=None)
    duration: float | None = Field(description="Duration of the video in seconds", default=None)
    view_count: int | None = Field(description="Number of views", default=None)


def _parse_video_id(url: str) -> str:
    parsed_url = urlparse(url)
    if parsed_url.hostname == "youtu.be":
        return parsed_url.path.lstrip("/")
    elif parsed_url.path.startswith(("/shorts/", "/embed/", "/live/")):
        return parsed_url.path.split("/")[2]
    else:
        q = parse_qs(parsed_url.query).get("v")
        if q is None:
            raise ValueError(f"couldn't find a video ID from the provided URL: {url}.")
        return q[0]


@lru_cache
def _get_transcript_snippets(ctx: AppContext, video_id: str, lang: str) -> Tuple[str, list[FetchedTranscriptSnippet]]:
    if lang == "en":
        languages = ["en"]
    else:
        languages = [lang, "en"]

    page = ctx.http_client.get(
        f"https://www.youtube.com/watch?v={video_id}", headers={"Accept-Language": ",".join(languages)}
    )
    page.raise_for_status()
    soup = BeautifulSoup(page.text, "html.parser")
    title = soup.title.string if soup.title and soup.title.string else "Transcript"

    transcripts = ctx.ytt_api.fetch(video_id, languages=languages)
    return title, transcripts.snippets


def _search_videos(ctx: AppContext, query: str, max_results: int) -> list[SearchResult]:
    # extract_flat: use the search-result listing data directly instead of visiting
    # each video's page. Keeps one unavailable/region-locked video from failing the
    # whole search, and avoids max_results extra requests.
    ctx.dlp.params["extract_flat"] = True
    try:
        info = ctx.dlp.extract_info(f"ytsearch{max_results}:{query}", download=False)
    finally:
        ctx.dlp.params["extract_flat"] = False

    results = []
    for entry in info.get("entries") or []:
        if entry is None:
            continue
        upload_date = None
        if entry.get("upload_date"):
            upload_date = datetime.strptime(entry["upload_date"], "%Y%m%d").replace(tzinfo=timezone.utc)
        results.append(
            SearchResult(
                title=entry.get("title", ""),
                url=entry.get("webpage_url") or entry.get("url", ""),
                uploader=entry.get("uploader", ""),
                upload_date=upload_date,
                duration=entry.get("duration"),
                view_count=entry.get("view_count"),
            )
        )
    return results


def server(
    response_limit: int | None = None,
    webshare_proxy_username: str | None = None,
    webshare_proxy_password: str | None = None,
    http_proxy: str | None = None,
    https_proxy: str | None = None,
) -> FastMCP:
    """Initializes the MCP server."""

    proxy_config: ProxyConfig | None = None
    if webshare_proxy_username and webshare_proxy_password:
        proxy_config = WebshareProxyConfig(webshare_proxy_username, webshare_proxy_password)
    elif http_proxy or https_proxy:
        proxy_config = GenericProxyConfig(http_proxy, https_proxy)

    mcp = FastMCP("Youtube Transcript", lifespan=partial(_app_lifespan, proxy_config=proxy_config))

    @mcp.tool()
    async def get_transcript(
        ctx: Context[ServerSession, AppContext],
        url: str = Field(description="The URL of the YouTube video"),
        lang: str = Field(description="The preferred language for the transcript", default="en"),
        next_cursor: str | None = Field(description="Cursor to retrieve the next page of the transcript", default=None),
    ) -> Transcript:
        """Retrieves the transcript of a YouTube video."""

        title, snippets = _get_transcript_snippets(ctx.request_context.lifespan_context, _parse_video_id(url), lang)
        transcripts = (item.text for item in snippets)

        if response_limit is None or response_limit <= 0:
            return Transcript(title=title, transcript="\n".join(transcripts))

        res = ""
        cursor = None
        for i, line in islice(enumerate(transcripts), int(next_cursor or 0), None):
            if len(res) + len(line) + 1 > response_limit:
                cursor = str(i)
                break
            res += f"{line}\n"

        return Transcript(title=title, transcript=res[:-1], next_cursor=cursor)

    @mcp.tool()
    def search_videos(
        ctx: Context[ServerSession, AppContext],
        query: str = Field(description="Search terms"),
        max_results: int = Field(description="Maximum number of results to return", default=10, ge=1, le=25),
    ) -> list[SearchResult]:
        """Searches YouTube for videos matching a query."""
        return _search_videos(ctx.request_context.lifespan_context, query, max_results)

    return mcp


__all__: Final = ["server", "Transcript", "SearchResult"]
