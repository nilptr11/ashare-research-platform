from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..storage import SourceFetchResult
from .base import SourceAdapterError
from .http import HttpTransport, urllib_get_json


SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_no_dash}/{primary_document}"


class SecEdgarSourceAdapter:
    source_id = "sec_edgar"

    def __init__(self, *, user_agent: str = "research-data-foundation/0.1", timeout: int = 30, transport: HttpTransport | None = None) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.transport = transport or urllib_get_json

    def fetch(
        self,
        api_name: str,
        params: dict[str, Any],
        fields: tuple[str, ...] | list[str] | None = None,
    ) -> SourceFetchResult:
        if api_name == "company_tickers":
            response = self.transport(SEC_COMPANY_TICKERS_URL, {}, {"User-Agent": self.user_agent}, self.timeout)
            payload = response.json()
            rows = company_ticker_rows(payload)
            return SourceFetchResult(
                source_id=self.source_id,
                api_name=api_name,
                params={},
                requested_at=now_iso(),
                frame=pd.DataFrame(rows),
                metadata={"adapter": "SecEdgarSourceAdapter", "url": response.url, "status": response.status},
            )

        if api_name not in {"submissions", "companyfacts"}:
            raise SourceAdapterError(f"SEC EDGAR api is not implemented: {api_name}")
        cik = normalize_cik(str(params.get("cik", "")))
        if not cik:
            raise SourceAdapterError(f"SEC {api_name} requires cik")
        url = SEC_COMPANYFACTS_URL.format(cik=cik) if api_name == "companyfacts" else SEC_SUBMISSIONS_URL.format(cik=cik)
        response = self.transport(url, {}, {"User-Agent": self.user_agent}, self.timeout)
        payload = response.json()
        rows = companyfacts_rows(payload, cik=cik) if api_name == "companyfacts" else submissions_rows(payload, cik=cik)
        return SourceFetchResult(
            source_id=self.source_id,
            api_name=api_name,
            params={"cik": cik},
            requested_at=now_iso(),
            frame=pd.DataFrame(rows),
            metadata={"adapter": "SecEdgarSourceAdapter", "url": response.url, "status": response.status},
        )


def company_ticker_rows(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    values = payload.values() if isinstance(payload, dict) else payload
    rows: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        cik = normalize_cik(str(item.get("cik_str", "")))
        ticker = str(item.get("ticker") or "").upper()
        title = str(item.get("title") or "")
        if not (cik and ticker and title):
            continue
        rows.append(
            {
                "cik": cik,
                "ticker": ticker,
                "title": title,
                "source_url": f"https://www.sec.gov/edgar/browse/?CIK={cik}",
            }
        )
    return rows


def companyfacts_rows(payload: dict[str, Any], *, cik: str) -> list[dict[str, Any]]:
    entity_name = str(payload.get("entityName") or "")
    facts = dict(payload.get("facts") or {})
    rows: list[dict[str, Any]] = []
    source_url = SEC_COMPANYFACTS_URL.format(cik=cik)
    for taxonomy, concepts in facts.items():
        if not isinstance(concepts, dict):
            continue
        for concept, concept_payload in concepts.items():
            if not isinstance(concept_payload, dict):
                continue
            label = str(concept_payload.get("label") or "")
            description = str(concept_payload.get("description") or "")
            units = concept_payload.get("units") or {}
            if not isinstance(units, dict):
                continue
            for unit, unit_facts in units.items():
                if not isinstance(unit_facts, list):
                    continue
                for fact in unit_facts:
                    if not isinstance(fact, dict):
                        continue
                    accession = str(fact.get("accn") or "")
                    rows.append(
                        {
                            "cik": cik,
                            "entity_name": entity_name,
                            "taxonomy": str(taxonomy),
                            "concept": str(concept),
                            "label": label,
                            "description": description,
                            "unit": str(unit),
                            "start_date": str(fact.get("start") or ""),
                            "end_date": str(fact.get("end") or ""),
                            "fiscal_year": "" if fact.get("fy") is None else str(fact.get("fy")),
                            "fiscal_period": str(fact.get("fp") or ""),
                            "form": str(fact.get("form") or ""),
                            "filed_date": str(fact.get("filed") or ""),
                            "accession_number": accession,
                            "frame": str(fact.get("frame") or ""),
                            "value": fact.get("val"),
                            "source_url": source_url,
                        }
                    )
    return rows


def submissions_rows(payload: dict[str, Any], *, cik: str) -> list[dict[str, Any]]:
    recent = dict(payload.get("filings", {}).get("recent", {}) or {})
    forms = list(recent.get("form") or [])
    filing_dates = list(recent.get("filingDate") or [])
    accessions = list(recent.get("accessionNumber") or [])
    primary_documents = list(recent.get("primaryDocument") or [])
    descriptions = list(recent.get("primaryDocDescription") or [])

    rows: list[dict[str, Any]] = []
    cik_int = str(int(cik))
    for index, form in enumerate(forms):
        accession = _at(accessions, index)
        primary_document = _at(primary_documents, index)
        rows.append(
            {
                "cik": cik,
                "form": form,
                "filingDate": _at(filing_dates, index),
                "accessionNumber": accession,
                "primaryDocument": primary_document,
                "description": _at(descriptions, index),
                "source_url": _archive_url(cik_int, accession, primary_document),
            }
        )
    return rows


def normalize_cik(value: str) -> str:
    digits = "".join(char for char in str(value or "") if char.isdigit())
    return digits.zfill(10) if digits else ""


def _archive_url(cik_int: str, accession: str, primary_document: str) -> str:
    if not accession or not primary_document:
        return ""
    return SEC_ARCHIVE_URL.format(
        cik_int=cik_int,
        accession_no_dash=accession.replace("-", ""),
        primary_document=primary_document,
    )


def _at(values: list[Any], index: int) -> Any:
    return values[index] if index < len(values) else ""


def now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
