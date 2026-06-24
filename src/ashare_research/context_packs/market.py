from __future__ import annotations

from pathlib import Path
from typing import Any

from .builders import ContextPackBuilder


def build_market_structure_pack(
    *,
    as_of: str,
    trade_days: int = 120,
    data_dir: Path | str | None = None,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    return ContextPackBuilder(data_dir).build_market_structure(
        as_of=as_of,
        trade_days=trade_days,
        output_path=output_path,
    )
