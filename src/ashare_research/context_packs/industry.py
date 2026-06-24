from __future__ import annotations

from pathlib import Path
from typing import Any

from .builders import ContextPackBuilder


def build_industry_pack(
    industry: str,
    *,
    as_of: str,
    data_dir: Path | str | None = None,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    return ContextPackBuilder(data_dir).build_industry(
        industry=industry,
        as_of=as_of,
        output_path=output_path,
    )
