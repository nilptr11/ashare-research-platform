from __future__ import annotations

from pathlib import Path
from typing import Any

from .builders import ContextPackBuilder


def build_industry_chain_pack(
    theme: str,
    *,
    as_of: str,
    windows: list[int] | None = None,
    data_dir: Path | str | None = None,
    output_path: Path | str | None = None,
    preview_limit: int = 20,
) -> dict[str, Any]:
    return ContextPackBuilder(data_dir).build_industry_chain(
        theme=theme,
        as_of=as_of,
        windows=windows,
        output_path=output_path,
        preview_limit=preview_limit,
    )
