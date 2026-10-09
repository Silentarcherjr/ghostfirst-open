"""Minimal client for the hosted GhostFirst API.

Only the public HTTP API is used (`POST /v1/scans`, `POST /v1/deep-checks`);
no engine code lives here. Errors are mapped to stable codes; server message
text is never passed on.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx

# Hosted staging API. Override with GHOSTFIRST_API_URL.
DEFAULT_API_URL = "https://ghostfirst.com"
TIMEOUT_SECONDS = 60.0


class GhostFirstError(Exception):
    """A typed API failure. `code` is stable (e.g. `rate_limited`)."""

    def __init__(self, code: str, *, status: Optional[int] = None,
                 retry_after_seconds: Optional[int] = None) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.retry_after_seconds = retry_after_seconds


def api_url_from_env() -> str:
    url = os.environ.get("GHOSTFIRST_API_URL", DEFAULT_API_URL).rstrip("/")
    parts = urlsplit(url)
    local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
    if parts.scheme != "https" and not (parts.scheme == "http" and local):
        raise ValueError("GHOSTFIRST_API_URL must use https (http only for localhost).")
    return url


@dataclass
class GhostFirstClient:
    base_url: str
    transport: Optional[httpx.AsyncBaseTransport] = None

    async def scan(self, url: str, *, confirm_sensitive_link: bool = False) -> dict[str, Any]:
        return await self._post("/v1/scans", url, confirm_sensitive_link)

    async def deep_check(self, url: str, *, confirm_sensitive_link: bool = False) -> dict[str, Any]:
        return await self._post("/v1/deep-checks", url, confirm_sensitive_link)

    async def _post(self, path: str, url: str, confirm: bool) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=TIMEOUT_SECONDS, transport=self.transport,
            headers={"User-Agent": "ghostfirst-mcp/0.1"},
        ) as client:
            try:
                response = await client.post(path, json={"url": url, "confirm_sensitive_link": confirm})
            except httpx.TimeoutException:
                raise GhostFirstError("request_timeout") from None
            except httpx.HTTPError:
                raise GhostFirstError("no_connection") from None
        if response.status_code == 200:
            return response.json()
        code = "unknown_error"
        retry_after = None
        try:
            detail = response.json().get("detail", {})
            if isinstance(detail, dict):
                code = str(detail.get("code") or code)
                retry_after = detail.get("retry_after_seconds")
        except ValueError:
            code = {429: "rate_limited", 502: "service_unavailable", 503: "server_busy",
                    504: "request_timeout"}.get(response.status_code, code)
        header = response.headers.get("Retry-After")
        if retry_after is None and header and header.isdigit():
            retry_after = int(header)
        raise GhostFirstError(code, status=response.status_code,
                              retry_after_seconds=retry_after if isinstance(retry_after, int) else None)
