from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..storage import SourceFetchResult
from .base import SourceAdapterError
from .http import HttpTransport, urllib_get_json


REPORT_API_URL = "https://reportapi.eastmoney.com/report/list"
REPORT_PDF_URL = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"
QUOTE_SNAPSHOT_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"


class EastmoneySourceAdapter:
    def __init__(
        self,
        *,
        source_id: str = "eastmoney_direct",
        timeout: int = 30,
        transport: HttpTransport | None = None,
    ) -> None:
        self.source_id = source_id
        self.timeout = timeout
        self.transport = transport or urllib_get_json

    def fetch(
        self,
        api_name: str,
        params: dict[str, Any],
        fields: tuple[str, ...] | list[str] | None = None,
    ) -> SourceFetchResult:
        if api_name == "push2.quote_snapshot":
            request_params = {
                "secids": str(params.get("secids", "") or ""),
                "snapshot_at": str(params.get("snapshot_at", "") or ""),
            }
            rows = self._quote_snapshot(request_params)
            return SourceFetchResult(
                source_id=self.source_id,
                api_name=api_name,
                params=request_params,
                requested_at=now_iso(),
                frame=pd.DataFrame(rows),
                metadata={"adapter": "EastmoneySourceAdapter", "endpoint": QUOTE_SNAPSHOT_URL},
            )
        if api_name != "reportapi.industry_reports":
            raise SourceAdapterError(f"Eastmoney api is not implemented: {api_name}")
        request_params = {
            "industry_code": str(params.get("industry_code", "*") or "*"),
            "begin": str(params.get("begin", "2024-01-01") or "2024-01-01"),
            "end": str(params.get("end", "2030-01-01") or "2030-01-01"),
            "max_pages": int(params.get("max_pages", 1) or 1),
        }
        rows = self._industry_reports(request_params)
        return SourceFetchResult(
            source_id=self.source_id,
            api_name=api_name,
            params=request_params,
            requested_at=now_iso(),
            frame=pd.DataFrame(rows),
            metadata={"adapter": "EastmoneySourceAdapter", "endpoint": REPORT_API_URL},
        )

    def _industry_reports(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        all_rows: list[dict[str, Any]] = []
        max_pages = max(int(params["max_pages"]), 1)
        for page in range(1, max_pages + 1):
            page_params = {
                "industryCode": params["industry_code"],
                "pageSize": "100",
                "industry": "*",
                "rating": "*",
                "ratingChange": "*",
                "beginTime": params["begin"],
                "endTime": params["end"],
                "pageNo": str(page),
                "fields": "",
                "qType": "1",
            }
            response = self.transport(
                REPORT_API_URL,
                page_params,
                {"User-Agent": "research-data-foundation/0.1", "Referer": "https://data.eastmoney.com/"},
                self.timeout,
            )
            payload = response.json()
            rows = list(payload.get("data") or [])
            if not rows:
                break
            all_rows.extend(add_report_source_urls(rows))
            total_page = int(payload.get("TotalPage") or 1)
            if page >= total_page:
                break
        return all_rows

    def _quote_snapshot(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        if not params["secids"]:
            raise SourceAdapterError("push2.quote_snapshot requires secids")
        request_params = {
            "secids": params["secids"],
            "fields": "f12,f14,f2,f3,f5,f6",
            "fltt": "2",
        }
        response = self.transport(
            QUOTE_SNAPSHOT_URL,
            request_params,
            {"User-Agent": "research-data-foundation/0.1", "Referer": "https://quote.eastmoney.com/"},
            self.timeout,
        )
        payload = response.json()
        rows = payload.get("data", {}).get("diff") if isinstance(payload, dict) else []
        if isinstance(rows, dict):
            rows = list(rows.values())
        output: list[dict[str, Any]] = []
        for row in list(rows or []):
            item = dict(row)
            item["snapshot_at"] = params["snapshot_at"] or now_iso()
            item["source_url"] = response.url
            output.append(item)
        return output


def add_report_source_urls(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        info_code = str(row.get("infoCode") or "")
        item = {
            "infoCode": info_code,
            "title": str(row.get("title") or ""),
            "publishDate": str(row.get("publishDate") or ""),
            "orgSName": str(row.get("orgSName") or ""),
            "industryName": str(row.get("industryName") or ""),
        }
        item["source_url"] = REPORT_PDF_URL.format(info_code=info_code) if info_code else "https://data.eastmoney.com/report/"
        output.append(item)
    return output


def now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
