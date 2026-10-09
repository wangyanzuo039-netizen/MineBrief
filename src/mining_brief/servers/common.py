from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from mining_brief.network import SourceError
from mining_brief.schemas import failure

logger = logging.getLogger("mining_brief.server")


async def guarded(call: Callable[[], Awaitable[dict[str, Any]]], mode: str) -> dict[str, Any]:
    try:
        return await call()
    except SourceError as exc:
        return failure(exc.code, str(exc), mode=mode)
    except (ValueError, FileNotFoundError, KeyError):
        return failure(
            "invalid_input_or_data", "参数或数据配置无效，检查日期、商品及 manifest", mode=mode
        )
    except httpx.HTTPError:
        return failure(
            "source_unavailable", "来源无法访问、超时或需要授权", mode=mode, retryable=True
        )
    except Exception:
        logger.error("provider_failed", exc_info=False)
        return failure("internal_error", "工具内部错误，请检查脱敏服务日志", mode=mode)
