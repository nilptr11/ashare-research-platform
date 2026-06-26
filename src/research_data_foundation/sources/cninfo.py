from __future__ import annotations

import hashlib
from io import BytesIO
from datetime import datetime
from typing import Any
from urllib import parse
from zoneinfo import ZoneInfo

import pandas as pd

from ..storage import SourceArtifact, SourceFetchResult
from .base import SourceAdapterError
from .http import HttpBinaryTransport, HttpTransport, urllib_get_bytes, urllib_post_json


CNINFO_ANNOUNCEMENT_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_URL = "https://static.cninfo.com.cn/{path}"
CNINFO_ANNOUNCEMENT_COLUMNS = (
    "publish_date",
    "publish_time",
    "announcement_id",
    "security_code",
    "security_id",
    "security_name",
    "org_id",
    "title",
    "short_title",
    "announcement_type",
    "announcement_type_name",
    "column_id",
    "page_column",
    "adjunct_url",
    "source_url",
    "adjunct_type",
    "adjunct_size",
)
CNINFO_ANNOUNCEMENT_TEXT_COLUMNS = (
    "publish_date",
    "announcement_id",
    "security_id",
    "security_name",
    "title",
    "source_url",
    "pdf_sha256",
    "pdf_bytes",
    "text",
    "text_length",
    "page_count",
    "parse_status",
    "parse_message",
)


class CninfoSourceAdapter:
    source_id = "cninfo"

    def __init__(
        self,
        *,
        timeout: int = 30,
        transport: HttpTransport | None = None,
        binary_transport: HttpBinaryTransport | None = None,
    ) -> None:
        self.timeout = timeout
        self.transport = transport or urllib_post_json
        self.binary_transport = binary_transport or urllib_get_bytes

    def fetch(
        self,
        api_name: str,
        params: dict[str, Any],
        fields: tuple[str, ...] | list[str] | None = None,
    ) -> SourceFetchResult:
        if api_name == "announcement_pdf_text":
            return self._announcement_pdf_text(params)
        if api_name != "announcements":
            raise SourceAdapterError(f"CNINFO api is not implemented: {api_name}")
        request_params = {
            "start_date": hyphen_date(str(params.get("start_date", "") or params.get("publish_date", ""))),
            "end_date": hyphen_date(str(params.get("end_date", "") or params.get("publish_date", ""))),
            "column": str(params.get("column", "szse") or "szse"),
            "plate": str(params.get("plate", "") or ""),
            "stock": str(params.get("stock", "") or ""),
            "category": str(params.get("category", "") or ""),
            "keyword": str(params.get("keyword", "") or ""),
            "page_size": min(positive_int(params.get("page_size", 30), "page_size"), 30),
            "max_pages": positive_int(params.get("max_pages", 20), "max_pages"),
        }
        if not request_params["start_date"] or not request_params["end_date"]:
            raise SourceAdapterError("CNINFO announcements requires start_date and end_date")
        rows = self._announcements(request_params)
        return SourceFetchResult(
            source_id=self.source_id,
            api_name=api_name,
            params=request_params,
            requested_at=now_iso(),
            frame=pd.DataFrame(rows, columns=list(CNINFO_ANNOUNCEMENT_COLUMNS)),
            metadata={"adapter": "CninfoSourceAdapter", "endpoint": CNINFO_ANNOUNCEMENT_URL},
        )

    def _announcement_pdf_text(self, params: dict[str, Any]) -> SourceFetchResult:
        source_url = normalize_pdf_url(str(params.get("source_url") or params.get("adjunct_url") or ""))
        if not source_url:
            raise SourceAdapterError("CNINFO announcement_pdf_text requires source_url or adjunct_url")
        publish_date = compact_date(str(params.get("publish_date", "")))
        announcement_id = text(params.get("announcement_id"))
        security_id = text(params.get("security_id"))
        security_name = text(params.get("security_name"))
        title = text(params.get("title"))
        requested_at = now_iso()
        response = self.binary_transport(source_url, {}, cninfo_pdf_headers(), self.timeout)
        pdf_bytes = response.content
        pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        extracted = extract_pdf_text(pdf_bytes)
        row = {
            "publish_date": publish_date,
            "announcement_id": announcement_id,
            "security_id": security_id,
            "security_name": security_name,
            "title": title,
            "source_url": source_url,
            "pdf_sha256": pdf_sha256,
            "pdf_bytes": len(pdf_bytes),
            "text": extracted["text"],
            "text_length": len(extracted["text"]),
            "page_count": extracted["page_count"],
            "parse_status": extracted["status"],
            "parse_message": extracted["message"],
        }
        filename = f"{announcement_id or pdf_sha256}.pdf"
        return SourceFetchResult(
            source_id=self.source_id,
            api_name="announcement_pdf_text",
            params={
                "publish_date": publish_date,
                "announcement_id": announcement_id,
                "security_id": security_id,
                "source_url": source_url,
            },
            requested_at=requested_at,
            frame=pd.DataFrame([row], columns=list(CNINFO_ANNOUNCEMENT_TEXT_COLUMNS)),
            metadata={
                "adapter": "CninfoSourceAdapter",
                "endpoint": source_url,
                "pdf_sha256": pdf_sha256,
            },
            artifacts=(SourceArtifact(filename=filename, content=pdf_bytes, content_type="application/pdf"),),
        )

    def _announcements(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for column, plate in cninfo_market_specs(str(params["column"]), str(params.get("plate", ""))):
            for page in range(1, int(params["max_pages"]) + 1):
                form = {
                    "pageNum": str(page),
                    "pageSize": str(params["page_size"]),
                    "column": column,
                    "tabName": "fulltext",
                    "plate": plate,
                    "stock": params["stock"],
                    "searchkey": params["keyword"],
                    "secid": "",
                    "category": params["category"],
                    "trade": "",
                    "seDate": f"{params['start_date']}~{params['end_date']}",
                    "sortName": "",
                    "sortType": "",
                    "isHLtitle": "true",
                }
                response = self.transport(CNINFO_ANNOUNCEMENT_URL, form, cninfo_headers(), self.timeout)
                payload = response.json()
                if not isinstance(payload, dict):
                    raise SourceAdapterError("CNINFO announcements returned non-object JSON")
                rows = list(payload.get("announcements") or [])
                if not rows:
                    break
                normalized_rows = normalize_announcements(rows)
                new_rows = []
                for row in normalized_rows:
                    announcement_id = str(row.get("announcement_id") or "")
                    if announcement_id and announcement_id in seen_ids:
                        continue
                    if announcement_id:
                        seen_ids.add(announcement_id)
                    new_rows.append(row)
                if not new_rows:
                    break
                output.extend(new_rows)
                total_pages = int(payload.get("totalpages") or page)
                if page >= total_pages or not bool(payload.get("hasMore")):
                    break
        return output


def cninfo_market_specs(column_value: str, plate_value: str = "") -> tuple[tuple[str, str], ...]:
    columns = tuple(dict.fromkeys(item.strip() for item in column_value.split(",") if item.strip()))
    if not columns:
        columns = ("szse",)
    if len(columns) == 1 and plate_value:
        return ((columns[0], plate_value),)
    mapping = {
        "szse": ("szse", "sz"),
        "sse": ("sse", "sh"),
        "bse": ("bse", "bj"),
        "bj": ("bse", "bj"),
    }
    return tuple(mapping.get(column, (column, plate_value)) for column in columns)


def normalize_announcements(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        security_code = text(row.get("secCode"))
        security_id = infer_ashare_security_id(security_code)
        if not security_id:
            continue
        adjunct_url = text(row.get("adjunctUrl"))
        publish_time = cninfo_time(row.get("announcementTime"))
        output.append(
            {
                "publish_date": compact_date(publish_time[:10]) if publish_time else "",
                "publish_time": publish_time,
                "announcement_id": text(row.get("announcementId")),
                "security_code": security_code,
                "security_id": security_id,
                "security_name": text(row.get("secName") or row.get("tileSecName")),
                "org_id": text(row.get("orgId")),
                "title": text(row.get("announcementTitle")),
                "short_title": text(row.get("shortTitle")),
                "announcement_type": text(row.get("announcementType")),
                "announcement_type_name": text(row.get("announcementTypeName")),
                "column_id": text(row.get("columnId")),
                "page_column": text(row.get("pageColumn")),
                "adjunct_url": adjunct_url,
                "source_url": CNINFO_STATIC_URL.format(path=adjunct_url) if adjunct_url else "",
                "adjunct_type": text(row.get("adjunctType")),
                "adjunct_size": row.get("adjunctSize"),
            }
        )
    return output


def cninfo_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 research-data-foundation/0.1",
        "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
        "X-Requested-With": "XMLHttpRequest",
    }


def cninfo_pdf_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 research-data-foundation/0.1",
        "Referer": "https://www.cninfo.com.cn/",
    }


def normalize_pdf_url(value: str) -> str:
    raw = text(value)
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = parse.urlparse(raw)
        if parsed.netloc != "static.cninfo.com.cn":
            raise SourceAdapterError(f"unsupported CNINFO PDF host: {parsed.netloc}")
        return raw
    return CNINFO_STATIC_URL.format(path=raw.lstrip("/"))


def extract_pdf_text(pdf_bytes: bytes) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError as error:  # pragma: no cover - dependency is declared.
        raise SourceAdapterError("pypdf is required for CNINFO PDF text extraction") from error
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        page_texts = []
        for page in reader.pages:
            page_texts.append(page.extract_text() or "")
        output = "\n\n".join(text for text in page_texts if text.strip()).strip()
        return {
            "text": output,
            "page_count": len(reader.pages),
            "status": "ok" if output else "empty_text",
            "message": "",
        }
    except Exception as error:
        return {
            "text": "",
            "page_count": 0,
            "status": "parse_error",
            "message": str(error),
        }


def infer_ashare_security_id(code: str) -> str:
    if len(code) != 6 or not code.isdigit():
        return ""
    if code.startswith("6"):
        return f"{code}.SH"
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return ""


def cninfo_time(value: Any) -> str:
    try:
        timestamp = int(value) / 1000
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(timestamp, ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def compact_date(value: str) -> str:
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return datetime.strptime(text[:10], "%Y-%m-%d").strftime("%Y%m%d")
    if len(text) >= 8:
        return datetime.strptime(text[:8], "%Y%m%d").strftime("%Y%m%d")
    return ""


def hyphen_date(value: str) -> str:
    compact = compact_date(value)
    if not compact:
        return ""
    return datetime.strptime(compact, "%Y%m%d").strftime("%Y-%m-%d")


def positive_int(value: Any, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as error:
        raise SourceAdapterError(f"{field_name} must be a positive integer") from error
    if normalized <= 0:
        raise SourceAdapterError(f"{field_name} must be a positive integer")
    return normalized


def text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
