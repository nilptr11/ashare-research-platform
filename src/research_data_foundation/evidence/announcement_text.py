from __future__ import annotations

from typing import Any

import pandas as pd


def announcement_text_snippet_candidates(
    frame: pd.DataFrame,
    *,
    meta: dict[str, Any],
    query: str,
    context_chars: int = 120,
    limit: int = 20,
    case_sensitive: bool = False,
) -> dict[str, Any]:
    query_text = query.strip()
    if not query_text:
        raise ValueError("query is required")
    if context_chars < 0:
        raise ValueError("context_chars must be non-negative")

    records = list(
        _iter_snippet_records(
            frame,
            meta=meta,
            query=query_text,
            context_chars=context_chars,
            limit=limit,
            case_sensitive=case_sensitive,
        )
    )
    return {
        "schema": "rdf.announcement_text_snippet_candidates.v1",
        "dataset_id": "ashare.announcement_text",
        "partition": dict(meta.get("partition") or {}),
        "query": query_text,
        "case_sensitive": case_sensitive,
        "context_chars": context_chars,
        "records_total": len(records),
        "records": records,
        "ingested": False,
        "note": (
            "Snippet candidates locate text in official CNINFO PDF extracts. "
            "They are not evidence records until a concrete claim is reviewed and ingested."
        ),
    }


def _iter_snippet_records(
    frame: pd.DataFrame,
    *,
    meta: dict[str, Any],
    query: str,
    context_chars: int,
    limit: int,
    case_sensitive: bool,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if limit < 0:
        limit = 0
    query_for_match = query if case_sensitive else query.casefold()
    query_time = str(meta.get("published_at") or "")

    for index, row in frame.reset_index(drop=True).iterrows():
        if limit and len(records) >= limit:
            break
        parse_status = _text(row, "parse_status")
        if parse_status and parse_status != "ok":
            continue
        text = _text(row, "text")
        if not text:
            continue
        haystack = text if case_sensitive else text.casefold()
        search_from = 0
        while True:
            if limit and len(records) >= limit:
                break
            match_start = haystack.find(query_for_match, search_from)
            if match_start < 0:
                break
            match_end = match_start + len(query_for_match)
            snippet_start = max(match_start - context_chars, 0)
            snippet_end = min(match_end + context_chars, len(text))
            records.append(
                {
                    "dataset_id": "ashare.announcement_text",
                    "partition": dict(meta.get("partition") or {}),
                    "row_ref": f"row:{index}",
                    "announcement_id": _text(row, "announcement_id"),
                    "security_id": _text(row, "security_id"),
                    "security_name": _text(row, "security_name"),
                    "title": _text(row, "title"),
                    "publish_date": _text(row, "publish_date"),
                    "source": {
                        "source_type": "company_filing",
                        "source_name": "CNINFO official announcement PDF",
                        "source_url": _text(row, "source_url"),
                        "published_at": _text(row, "publish_date"),
                        "query_time": query_time,
                    },
                    "query": query,
                    "match_text": text[match_start:match_end],
                    "match_start": match_start,
                    "match_end": match_end,
                    "snippet_start": snippet_start,
                    "snippet_end": snippet_end,
                    "snippet": text[snippet_start:snippet_end],
                    "text_length": _int_or_none(row.get("text_length")) or len(text),
                    "parse_status": parse_status or "ok",
                    "verification": "official_pdf_text_snippet_candidate",
                    "supports": ("claim_extraction", "company_business_exposure_review"),
                    "quality_flags": (
                        "snippet_requires_claim_confirmation",
                        "do_not_ingest_without_explicit_claim",
                    ),
                }
            )
            search_from = match_end if match_end > search_from else search_from + 1
    return records


def _text(row: pd.Series, column: str) -> str:
    value = row.get(column)
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _int_or_none(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
