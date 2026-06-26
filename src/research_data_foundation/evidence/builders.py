from __future__ import annotations

from typing import Any

import pandas as pd

from .schemas import EvidenceRecord, EvidenceSourceRef


def evidence_from_table(dataset_id: str, frame: pd.DataFrame, *, meta: dict[str, Any]) -> list[EvidenceRecord]:
    if dataset_id == "global.sec_filings":
        return _sec_filing_evidence(frame, meta=meta)
    if dataset_id == "global.sec_ticker_cik":
        return _sec_ticker_cik_evidence(frame, meta=meta)
    if dataset_id == "global.sec_companyfacts":
        return _sec_companyfacts_evidence(frame, meta=meta)
    if dataset_id == "industry.eastmoney_report_index":
        return _eastmoney_report_evidence(frame, meta=meta)
    if dataset_id == "ashare.main_business":
        return _main_business_evidence(frame, meta=meta)
    if dataset_id == "ashare.announcements":
        return _announcement_evidence(frame, meta=meta)
    if dataset_id == "ashare.announcement_text":
        return _announcement_text_evidence(frame, meta=meta)
    if dataset_id == "ashare.shareholder_trades":
        return _shareholder_trade_event_evidence(frame, meta=meta)
    if dataset_id == "ashare.repurchase_events":
        return _repurchase_event_evidence(frame, meta=meta)
    if dataset_id == "ashare.earnings_forecast_events":
        return _earnings_forecast_event_evidence(frame, meta=meta)
    if dataset_id in FINANCIAL_DATASETS:
        return _financial_fact_evidence(dataset_id, frame, meta=meta)
    return []


FINANCIAL_DATASETS = {
    "ashare.income_statement": ("income_statement", ("total_revenue", "n_income")),
    "ashare.balance_sheet": ("balance_sheet", ("total_assets", "total_liab")),
    "ashare.cash_flow": ("cash_flow", ("n_cashflow_act",)),
    "ashare.financial_indicator": ("financial_indicator", ("eps",)),
    "ashare.earnings_express": ("earnings_express", ("revenue", "n_income")),
    "ashare.dividend": ("dividend", ("div_proc", "cash_div")),
    "ashare.audit_opinion": ("audit_opinion", ("audit_result", "audit_agency")),
    "ashare.disclosure_date": ("disclosure_date", ("pre_date", "actual_date")),
    "ashare.earnings_forecast": ("earnings_forecast", ("forecast_type", "change_reason")),
}


def _sec_filing_evidence(frame: pd.DataFrame, *, meta: dict[str, Any]) -> list[EvidenceRecord]:
    query_time = str(meta.get("published_at") or "")
    records: list[EvidenceRecord] = []
    for index, row in frame.reset_index(drop=True).iterrows():
        filing_date = _text(row, "filing_date")
        cik = _text(row, "cik")
        form = _text(row, "form")
        accession = _text(row, "accession_number")
        source_url = _text(row, "source_url")
        if not (filing_date and cik and form and accession and source_url):
            continue
        records.append(
            EvidenceRecord(
                claim=f"SEC EDGAR records CIK {cik} filing form {form} with accession {accession}.",
                topic="sec_filing",
                dataset_id="global.sec_filings",
                row_ref=f"row:{index}",
                market_scope="us",
                company=f"CIK {cik}",
                source=EvidenceSourceRef(
                    source_type="regulator",
                    source_name="SEC EDGAR",
                    source_url=source_url,
                    published_at=filing_date,
                    query_time=query_time,
                ),
                confidence="high",
                verification="official_filing_index",
                supports=("evidence", "cross_market_context"),
                maturity="fetched",
            )
        )
    return records


def _sec_ticker_cik_evidence(frame: pd.DataFrame, *, meta: dict[str, Any]) -> list[EvidenceRecord]:
    query_time = str(meta.get("published_at") or "")
    records: list[EvidenceRecord] = []
    for index, row in frame.reset_index(drop=True).iterrows():
        cik = _text(row, "cik")
        ticker = _text(row, "ticker")
        title = _text(row, "title")
        source_url = _text(row, "source_url")
        if not (cik and ticker and title and source_url):
            continue
        records.append(
            EvidenceRecord(
                claim=f"SEC company tickers mapping lists ticker {ticker} for CIK {cik} ({title}).",
                topic="sec_ticker_cik",
                dataset_id="global.sec_ticker_cik",
                row_ref=f"row:{index}",
                market_scope="us",
                company=title,
                source=EvidenceSourceRef(
                    source_type="regulator",
                    source_name="SEC company_tickers",
                    source_url=source_url,
                    published_at=query_time[:10] if query_time else "on_demand",
                    query_time=query_time,
                ),
                confidence="high",
                verification="official_sec_ticker_cik_mapping",
                supports=("evidence", "cross_market_context"),
                maturity="fetched",
            )
        )
    return records


def _sec_companyfacts_evidence(frame: pd.DataFrame, *, meta: dict[str, Any]) -> list[EvidenceRecord]:
    query_time = str(meta.get("published_at") or "")
    records: list[EvidenceRecord] = []
    for index, row in frame.reset_index(drop=True).iterrows():
        cik = _text(row, "cik")
        entity_name = _text(row, "entity_name") or f"CIK {cik}"
        concept = _text(row, "concept")
        label = _text(row, "label") or concept
        unit = _text(row, "unit")
        end_date = _text(row, "end_date")
        filed_date = _text(row, "filed_date")
        form = _text(row, "form")
        accession = _text(row, "accession_number")
        source_url = _text(row, "source_url")
        value = row.get("value")
        if not (cik and concept and unit and end_date and filed_date and source_url):
            continue
        records.append(
            EvidenceRecord(
                claim=(
                    f"SEC companyfacts reports {entity_name} ({cik}) {label}={value} {unit} "
                    f"for period ending {end_date}, filed {filed_date}"
                    f"{' on form ' + form if form else ''}."
                ),
                topic="sec_companyfact",
                dataset_id="global.sec_companyfacts",
                row_ref=f"row:{index}",
                market_scope="us",
                company=entity_name,
                metric=concept,
                value=None if pd.isna(value) else value,
                unit=unit,
                period=end_date,
                source=EvidenceSourceRef(
                    source_type="regulator",
                    source_name="SEC companyfacts",
                    source_url=source_url,
                    published_at=filed_date,
                    query_time=query_time,
                ),
                confidence="high",
                verification="official_sec_xbrl_companyfacts",
                supports=("evidence", "financial_analysis", "cross_market_context"),
                maturity="fetched",
                quality_flags=("xbrl_fact_requires_concept_context",) if accession else (),
            )
        )
    return records


def _eastmoney_report_evidence(frame: pd.DataFrame, *, meta: dict[str, Any]) -> list[EvidenceRecord]:
    query_time = str(meta.get("published_at") or "")
    records: list[EvidenceRecord] = []
    for index, row in frame.reset_index(drop=True).iterrows():
        report_id = _text(row, "report_id")
        title = _text(row, "title")
        industry = _text(row, "industry_name")
        source_name = _text(row, "source_name") or "Eastmoney Report API"
        source_url = _text(row, "source_url")
        published_at = _text(row, "published_at")[:10]
        if not (report_id and title and source_url and published_at):
            continue
        records.append(
            EvidenceRecord(
                claim=f"Eastmoney report index lists industry report '{title}' for {industry or 'unknown industry'}.",
                topic="industry_report",
                dataset_id="industry.eastmoney_report_index",
                row_ref=f"row:{index}",
                market_scope="cn_ashare",
                industry=industry or None,
                source=EvidenceSourceRef(
                    source_type="research_report",
                    source_name=source_name,
                    source_url=source_url,
                    published_at=published_at,
                    query_time=query_time,
                ),
                confidence="low",
                verification="vendor_report_index",
                supports=("context", "evidence"),
                maturity="fetched",
                quality_flags=("report_is_not_company_disclosure",),
            )
        )
    return records


def _main_business_evidence(frame: pd.DataFrame, *, meta: dict[str, Any]) -> list[EvidenceRecord]:
    query_time = str(meta.get("published_at") or "")
    partition = dict(meta.get("partition") or {})
    records: list[EvidenceRecord] = []
    for index, row in frame.reset_index(drop=True).iterrows():
        security_id = _text(row, "security_id") or str(partition.get("security_id") or "")
        period = _text(row, "period") or str(partition.get("period") or "")
        segment_type = _text(row, "segment_type") or str(partition.get("segment_type") or "")
        item_name = _text(row, "item_name")
        currency = _text(row, "currency") or "CNY"
        if not (security_id and period and segment_type and item_name):
            continue
        sales = row.get("sales")
        segment_label = "product" if segment_type == "P" else "district" if segment_type == "D" else segment_type
        records.append(
            EvidenceRecord(
                claim=(
                    f"Tushare fina_mainbz reports {security_id} {period} {segment_label} segment "
                    f"'{item_name}' with sales {sales} {currency}."
                ),
                topic="main_business_segment",
                dataset_id="ashare.main_business",
                row_ref=f"row:{index}",
                market_scope="cn_ashare",
                company=security_id,
                product=item_name if segment_type == "P" else None,
                metric="sales",
                value=None if pd.isna(sales) else sales,
                unit=currency,
                period=period,
                source=EvidenceSourceRef(
                    source_type="vendor",
                    source_name="Tushare Pro fina_mainbz",
                    source_url="https://tushare.pro/wctapi/documents/81.md",
                    published_at=period,
                    query_time=query_time,
                ),
                confidence="medium",
                verification="vendor_financial_statement_interface",
                supports=("evidence", "company_business_exposure"),
                maturity="fetched",
                quality_flags=("requires_official_report_cross_check",),
            )
        )
    return records


def _announcement_evidence(frame: pd.DataFrame, *, meta: dict[str, Any]) -> list[EvidenceRecord]:
    query_time = str(meta.get("published_at") or "")
    records: list[EvidenceRecord] = []
    for index, row in frame.reset_index(drop=True).iterrows():
        announcement_id = _text(row, "announcement_id")
        security_id = _text(row, "security_id")
        security_name = _text(row, "security_name")
        title = _text(row, "title")
        publish_date = _text(row, "publish_date")
        source_url = _text(row, "source_url")
        if not (announcement_id and security_id and title and publish_date and source_url):
            continue
        records.append(
            EvidenceRecord(
                claim=f"CNINFO records {security_name or security_id} ({security_id}) announcement '{title}' disclosed on {publish_date}.",
                topic="company_announcement",
                dataset_id="ashare.announcements",
                row_ref=f"row:{index}",
                market_scope="cn_ashare",
                company=security_name or security_id,
                source=EvidenceSourceRef(
                    source_type="official_platform",
                    source_name="CNINFO",
                    source_url=source_url,
                    published_at=publish_date,
                    query_time=query_time,
                ),
                confidence="high",
                verification="official_disclosure_index",
                supports=("evidence", "context"),
                maturity="fetched",
                quality_flags=("announcement_index_only", "pdf_not_parsed"),
            )
        )
    return records


def _announcement_text_evidence(frame: pd.DataFrame, *, meta: dict[str, Any]) -> list[EvidenceRecord]:
    query_time = str(meta.get("published_at") or "")
    records: list[EvidenceRecord] = []
    for index, row in frame.reset_index(drop=True).iterrows():
        announcement_id = _text(row, "announcement_id")
        security_id = _text(row, "security_id")
        security_name = _text(row, "security_name")
        title = _text(row, "title")
        publish_date = _text(row, "publish_date")
        source_url = _text(row, "source_url")
        parse_status = _text(row, "parse_status")
        text_length = row.get("text_length")
        if parse_status != "ok" or not (announcement_id and security_id and title and publish_date and source_url):
            continue
        records.append(
            EvidenceRecord(
                claim=(
                    f"CNINFO official PDF text was extracted for {security_name or security_id} ({security_id}) "
                    f"announcement '{title}' disclosed on {publish_date}; text_length={text_length}."
                ),
                topic="company_announcement_text",
                dataset_id="ashare.announcement_text",
                row_ref=f"row:{index}",
                market_scope="cn_ashare",
                company=security_name or security_id,
                metric="text_length",
                value=None if pd.isna(text_length) else text_length,
                unit="characters",
                period=publish_date,
                source=EvidenceSourceRef(
                    source_type="company_filing",
                    source_name="CNINFO official announcement PDF",
                    source_url=source_url,
                    published_at=publish_date,
                    query_time=query_time,
                ),
                confidence="high",
                verification="official_pdf_text_extracted",
                supports=("evidence", "context", "company_business_exposure"),
                maturity="fetched",
                quality_flags=("raw_filing_text_requires_claim_extraction",),
            )
        )
    return records


def _shareholder_trade_event_evidence(frame: pd.DataFrame, *, meta: dict[str, Any]) -> list[EvidenceRecord]:
    query_time = str(meta.get("published_at") or "")
    partition = dict(meta.get("partition") or {})
    records: list[EvidenceRecord] = []
    for index, row in frame.reset_index(drop=True).iterrows():
        ann_date = _text(row, "ann_date") or str(partition.get("ann_date") or "")
        security_id = _text(row, "security_id")
        holder_name = _text(row, "holder_name")
        holder_type = _text(row, "holder_type")
        direction = _text(row, "in_de")
        change_vol = row.get("change_vol")
        change_ratio = row.get("change_ratio")
        avg_price = row.get("avg_price")
        if not (ann_date and security_id and holder_name and direction):
            continue
        direction_label = "increase" if direction.upper() == "IN" else "decrease" if direction.upper() == "DE" else direction
        ratio_text = "" if pd.isna(change_ratio) else f", change_ratio={change_ratio}%"
        price_text = "" if pd.isna(avg_price) else f", avg_price={avg_price} CNY/share"
        records.append(
            EvidenceRecord(
                claim=(
                    f"Tushare stk_holdertrade reports {security_id} shareholder {holder_name}"
                    f"{' (' + holder_type + ')' if holder_type else ''} {direction_label} event announced on {ann_date}: "
                    f"change_vol={change_vol} shares{ratio_text}{price_text}."
                ),
                topic="shareholder_trade_event",
                dataset_id="ashare.shareholder_trades",
                row_ref=f"row:{index}",
                market_scope="cn_ashare",
                company=security_id,
                metric="change_vol",
                value=None if pd.isna(change_vol) else change_vol,
                unit="share",
                period=ann_date,
                source=EvidenceSourceRef(
                    source_type="vendor",
                    source_name="Tushare Pro stk_holdertrade",
                    source_url="https://tushare.pro/",
                    published_at=ann_date,
                    query_time=query_time,
                ),
                confidence="low",
                verification="vendor_structured_event_interface",
                supports=("evidence_triage", "market_context"),
                maturity="fetched",
                quality_flags=("requires_official_announcement_text", "not_company_business_exposure"),
            )
        )
    return records


def _repurchase_event_evidence(frame: pd.DataFrame, *, meta: dict[str, Any]) -> list[EvidenceRecord]:
    query_time = str(meta.get("published_at") or "")
    partition = dict(meta.get("partition") or {})
    records: list[EvidenceRecord] = []
    for index, row in frame.reset_index(drop=True).iterrows():
        ann_date = _text(row, "ann_date") or str(partition.get("ann_date") or "")
        security_id = _text(row, "security_id")
        process_status = _text(row, "process_status")
        end_date = _text(row, "end_date")
        volume = row.get("volume")
        amount = row.get("amount")
        high_limit = row.get("high_limit")
        low_limit = row.get("low_limit")
        if not (ann_date and security_id and process_status):
            continue
        amount_text = "" if pd.isna(amount) else f", amount={amount} CNY"
        volume_text = "" if pd.isna(volume) else f", volume={volume} shares"
        price_text = ""
        if not pd.isna(low_limit) or not pd.isna(high_limit):
            price_text = f", price_limit={'' if pd.isna(low_limit) else low_limit}-{'' if pd.isna(high_limit) else high_limit} CNY/share"
        records.append(
            EvidenceRecord(
                claim=(
                    f"Tushare repurchase reports {security_id} share repurchase event announced on {ann_date}: "
                    f"process_status={process_status}{'; end_date=' + end_date if end_date else ''}"
                    f"{volume_text}{amount_text}{price_text}."
                ),
                topic="share_repurchase_event",
                dataset_id="ashare.repurchase_events",
                row_ref=f"row:{index}",
                market_scope="cn_ashare",
                company=security_id,
                metric="amount",
                value=None if pd.isna(amount) else amount,
                unit="cny",
                period=ann_date,
                source=EvidenceSourceRef(
                    source_type="vendor",
                    source_name="Tushare Pro repurchase",
                    source_url="https://tushare.pro/",
                    published_at=ann_date,
                    query_time=query_time,
                ),
                confidence="low",
                verification="vendor_structured_event_interface",
                supports=("evidence_triage", "market_context"),
                maturity="fetched",
                quality_flags=("requires_official_announcement_text", "not_company_business_exposure"),
            )
        )
    return records


def _earnings_forecast_event_evidence(frame: pd.DataFrame, *, meta: dict[str, Any]) -> list[EvidenceRecord]:
    query_time = str(meta.get("published_at") or "")
    partition = dict(meta.get("partition") or {})
    records: list[EvidenceRecord] = []
    for index, row in frame.reset_index(drop=True).iterrows():
        ann_date = _text(row, "ann_date") or str(partition.get("ann_date") or "")
        security_id = _text(row, "security_id")
        period = _text(row, "period")
        forecast_type = _text(row, "forecast_type")
        forecast_summary = _text(row, "forecast_summary")
        change_reason = _text(row, "change_reason")
        if not (ann_date and security_id and period and forecast_type):
            continue
        metrics = {
            column: row.get(column)
            for column in ("p_change_min", "p_change_max", "net_profit_min", "net_profit_max", "last_parent_net")
            if column in row.index and not pd.isna(row.get(column))
        }
        metric_text = ", ".join(f"{key}={value}" for key, value in metrics.items())
        summary_text = f"; summary={forecast_summary}" if forecast_summary else ""
        reason_text = f"; change_reason={change_reason}" if change_reason else ""
        records.append(
            EvidenceRecord(
                claim=(
                    f"Tushare forecast reports {security_id} earnings forecast event announced on {ann_date} "
                    f"for period {period}: forecast_type={forecast_type}"
                    f"{'; ' + metric_text if metric_text else ''}{summary_text}{reason_text}."
                ),
                topic="earnings_forecast_event",
                dataset_id="ashare.earnings_forecast_events",
                row_ref=f"row:{index}",
                market_scope="cn_ashare",
                company=security_id,
                metric=",".join(metrics.keys()) if metrics else "forecast_type",
                value=dict(metrics) | {"forecast_type": forecast_type},
                period=period,
                source=EvidenceSourceRef(
                    source_type="vendor",
                    source_name="Tushare Pro forecast",
                    source_url="https://tushare.pro/",
                    published_at=ann_date,
                    query_time=query_time,
                ),
                confidence="low",
                verification="vendor_structured_event_interface",
                supports=("evidence_triage", "financial_analysis", "market_context"),
                maturity="fetched",
                quality_flags=("requires_official_announcement_text", "not_company_business_exposure"),
            )
        )
    return records


def _financial_fact_evidence(dataset_id: str, frame: pd.DataFrame, *, meta: dict[str, Any]) -> list[EvidenceRecord]:
    topic, metric_columns = FINANCIAL_DATASETS[dataset_id]
    query_time = str(meta.get("published_at") or "")
    partition = dict(meta.get("partition") or {})
    records: list[EvidenceRecord] = []
    for index, row in frame.reset_index(drop=True).iterrows():
        security_id = _text(row, "security_id") or str(partition.get("security_id") or "")
        period = _text(row, "period") or str(partition.get("period") or "")
        ann_date = _text(row, "ann_date") or period
        if not (security_id and period):
            continue
        metrics = {
            column: row.get(column)
            for column in metric_columns
            if column in row.index and not pd.isna(row.get(column))
        }
        metric_text = ", ".join(f"{key}={value}" for key, value in metrics.items()) or "no key metric populated"
        records.append(
            EvidenceRecord(
                claim=f"Tushare {topic} reports {security_id} period {period}: {metric_text}.",
                topic=topic,
                dataset_id=dataset_id,
                row_ref=f"row:{index}",
                market_scope="cn_ashare",
                company=security_id,
                metric=",".join(metrics.keys()) if metrics else None,
                value=dict(metrics) if metrics else None,
                period=period,
                source=EvidenceSourceRef(
                    source_type="vendor",
                    source_name=f"Tushare Pro {topic}",
                    source_url="https://tushare.pro/",
                    published_at=ann_date,
                    query_time=query_time,
                ),
                confidence="medium",
                verification="vendor_financial_statement_interface",
                supports=("evidence", "financial_analysis"),
                maturity="fetched",
                quality_flags=("requires_official_filing_cross_check",),
            )
        )
    return records


def _text(row: pd.Series, column: str) -> str:
    value = row.get(column)
    if pd.isna(value):
        return ""
    return str(value).strip()
