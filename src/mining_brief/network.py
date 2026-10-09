"""Bounded downloads with allowlist, public-IP checks and per-hop validation."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from mining_brief.config import Settings


class SourceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_url(url: str, allowed_hosts: tuple[str, ...]) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise SourceError("unsafe_url", "仅允许配置中公开来源的 HTTPS URL")
    host = parsed.hostname
    if host is None:
        raise SourceError("unsafe_url", "URL 缺少主机")
    for entry in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(str(entry[4][0])).is_global:
            raise SourceError("unsafe_url", "来源解析到非公网地址")
    return url


async def download(url: str, settings: Settings) -> bytes:
    # A slow response body must not outlive the MCP tool's 60-second deadline.
    try:
        async with asyncio.timeout(min(45, settings.request_timeout * 3 + 2)):
            return await _download_with_retries(url, settings)
    except TimeoutError as exc:
        raise SourceError("source_timeout", "来源下载超过总时限，未使用未完整下载的内容") from exc


async def _download_with_retries(url: str, settings: Settings) -> bytes:
    """Retry only transient source failures, at most three attempts."""
    for attempt in range(3):
        try:
            return await _download_once(url, settings)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429 and exc.response.status_code < 500:
                raise
            if attempt == 2:
                raise
        except httpx.TransportError:
            if attempt == 2:
                raise
        await asyncio.sleep(0.5 * 2**attempt)
    raise AssertionError("unreachable retry state")


async def _download_once(url: str, settings: Settings) -> bytes:
    current = url
    async with httpx.AsyncClient(
        timeout=settings.request_timeout,
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "MiningBrief/0.1 (educational MCP demo)"},
    ) as client:
        for _ in range(5):
            validate_url(current, settings.allowed_hosts)
            async with client.stream("GET", current) as response:
                if response.is_redirect:
                    current = urljoin(current, response.headers["location"])
                    continue
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > settings.max_download_bytes:
                        raise SourceError("too_large", "来源超过下载大小限制")
                return bytes(content)
    raise SourceError("redirect_limit", "来源重定向次数过多")


def original_path(settings: Settings, entry: dict[str, str]) -> Path:
    path = (settings.data_dir / entry["path"]).resolve()
    if not path.is_relative_to(settings.data_dir.resolve()):
        raise SourceError("unsafe_path", "缓存文件超出数据目录")
    return path
