from __future__ import annotations

from typing import Any, Protocol

from ..storage import SourceFetchResult


class SourceAdapterError(RuntimeError):
    """Raised when a source adapter cannot fetch data."""


class SourceAdapter(Protocol):
    source_id: str

    def fetch(
        self,
        api_name: str,
        params: dict[str, Any],
        fields: tuple[str, ...] | list[str] | None = None,
    ) -> SourceFetchResult:
        """Fetch a source API and return a normalized tabular result."""
