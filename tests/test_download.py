from unittest.mock import AsyncMock

import httpx
import pytest

from mining_brief.config import Settings
from mining_brief.network import SourceError, download


async def test_transient_download_retries_but_keeps_bound(monkeypatch):
    supplied = AsyncMock(side_effect=[httpx.ReadTimeout("timeout"), b"verified by caller"])
    monkeypatch.setattr("mining_brief.network._download_once", supplied)
    monkeypatch.setattr("mining_brief.network.asyncio.sleep", AsyncMock())
    assert await download("https://www.lme.com/x", Settings()) == b"verified by caller"
    assert supplied.await_count == 2
    supplied.reset_mock(side_effect=True)
    supplied.side_effect = httpx.ReadTimeout("timeout")
    with pytest.raises(httpx.ReadTimeout):
        await download("https://www.lme.com/x", Settings())
    assert supplied.await_count == 3


@pytest.mark.parametrize("status", [401, 403, 404])
async def test_access_or_missing_source_is_not_retried(monkeypatch, status):
    request = httpx.Request("GET", "https://www.lme.com/x")
    response = httpx.Response(status, request=request)
    supplied = AsyncMock(
        side_effect=httpx.HTTPStatusError("unavailable", request=request, response=response)
    )
    monkeypatch.setattr("mining_brief.network._download_once", supplied)
    with pytest.raises(httpx.HTTPStatusError):
        await download(str(request.url), Settings())
    assert supplied.await_count == 1


async def test_source_policy_rejection_is_not_retried(monkeypatch):
    supplied = AsyncMock(side_effect=SourceError("unsafe_url", "rejected"))
    monkeypatch.setattr("mining_brief.network._download_once", supplied)
    with pytest.raises(SourceError):
        await download("https://localhost/x", Settings())
    assert supplied.await_count == 1
