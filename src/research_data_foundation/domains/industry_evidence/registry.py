from __future__ import annotations

from ...core import DatasetContract, IngestionRecipe, LineagePolicy, PipelineSpec, PipelineStep, SourceSpec, TemporalPolicy, UsagePolicy


def industry_evidence_sources() -> tuple[SourceSpec, ...]:
    return (
        SourceSpec(
            id="eastmoney_direct",
            title="Eastmoney Direct HTTP",
            source_role="research_evidence",
            authority_tier="S3",
            transport="http",
            rate_limit={"concurrency": 1, "min_interval_seconds": 1.5},
            auth={"type": "none"},
            notes="Direct HTTP access for Eastmoney-only datasets such as report lists and selected intraday observations.",
        ),
    )


def industry_evidence_datasets() -> tuple[DatasetContract, ...]:
    return (
        DatasetContract(
            id="industry.eastmoney_report_index",
            title="Eastmoney industry report index",
            domain="industry_evidence",
            market_scope="cn_ashare",
            role="evidence_seed",
            temporal=TemporalPolicy(
                temporal_mode="reference",
                finality="final",
                available_after="on_demand",
                as_of_policy="range",
            ),
            partition_keys=("query_date",),
            primary_key=("query_date", "report_id"),
            required_columns=("query_date", "report_id", "title", "published_at", "source_name", "source_url", "industry_name"),
            usage=UsagePolicy(
                allowed_uses=("evidence", "context"),
                forbidden_uses=("candidate_generation", "company_business_exposure"),
            ),
        ),
    )


def industry_evidence_recipes() -> tuple[IngestionRecipe, ...]:
    return (
        IngestionRecipe(
            id="eastmoney.reportapi.industry_reports.to_report_index",
            source_id="eastmoney_direct",
            source_api="reportapi.industry_reports",
            target_dataset_id="industry.eastmoney_report_index",
            schedule="research_on_demand",
            params_template={"industry_code": "*", "begin": "${params.begin}", "end": "${params.end}", "max_pages": "${params.max_pages}"},
            field_map={
                "infoCode": "report_id",
                "publishDate": "published_at",
                "orgSName": "source_name",
                "industryName": "industry_name",
            },
            lineage=LineagePolicy(raw_required=True, staging_required=True),
            selection_priority=10,
            notes="Research reports are evidence seeds only; they do not prove company business exposure.",
        ),
    )


def industry_evidence_pipelines() -> tuple[PipelineSpec, ...]:
    return (
        PipelineSpec(
            id="research_on_demand",
            title="On-demand research evidence ingestion",
            domain="industry_evidence",
            cadence="on_demand",
            steps=(PipelineStep("eastmoney.reportapi.industry_reports.to_report_index", required=False),),
            feature_ids=("industry.report_attention",),
        ),
    )
