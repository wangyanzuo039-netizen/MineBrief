from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

_checkout = Path(__file__).resolve().parents[2]
ROOT = _checkout if (_checkout / "pyproject.toml").exists() else Path.cwd().resolve()


class Settings(BaseModel):
    mode: Literal["demo", "live"] = "demo"
    as_of: str = "2021-09-08"
    data_dir: Path = ROOT / "data"
    request_timeout: float = Field(default=20, gt=0, le=120)
    max_download_bytes: int = 35_000_000
    allowed_hosts: tuple[str, ...] = (
        "www.lme.com",
        "www.asx.com.au",
        "announcements.asx.com.au",
        "noramlithiumcorp.com",
        "www.pls.com",
        "pls.com",
        "pls.au",
        "www.pilbaraminerals.com.au",
        "news.google.com",
    )

    @classmethod
    def from_env(cls) -> Settings:
        mode = os.getenv("MINING_MODE", "demo")
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        return cls(
            mode=mode,  # type: ignore[arg-type]
            as_of=os.getenv("MINING_AS_OF", "2021-09-08" if mode == "demo" else today),
            data_dir=Path(os.getenv("MINING_DATA_DIR", str(ROOT / "data"))),
            request_timeout=float(os.getenv("MINING_HTTP_TIMEOUT", "20")),
        )

    def manifest(self) -> dict[str, Any]:
        return json.loads((self.data_dir / "manifest.json").read_text(encoding="utf-8-sig"))  # type: ignore[no-any-return]
