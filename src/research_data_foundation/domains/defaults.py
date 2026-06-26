from __future__ import annotations

from ..core import FoundationRegistry
from .ashare import ashare_datasets, ashare_pipelines, ashare_recipes, ashare_sources
from .ashare_intraday import ashare_intraday_datasets, ashare_intraday_pipelines, ashare_intraday_recipes, ashare_intraday_sources
from .global_reference import global_reference_datasets, global_reference_pipelines, global_reference_recipes, global_reference_sources
from .industry_evidence import industry_evidence_datasets, industry_evidence_pipelines, industry_evidence_recipes, industry_evidence_sources


def default_registry() -> FoundationRegistry:
    return FoundationRegistry.from_entries(
        sources=(
            *ashare_sources(),
            *ashare_intraday_sources(),
            *global_reference_sources(),
            *industry_evidence_sources(),
        ),
        datasets=(
            *ashare_datasets(),
            *ashare_intraday_datasets(),
            *global_reference_datasets(),
            *industry_evidence_datasets(),
        ),
        recipes=(
            *ashare_recipes(),
            *ashare_intraday_recipes(),
            *global_reference_recipes(),
            *industry_evidence_recipes(),
        ),
        pipelines=(
            *ashare_pipelines(),
            *ashare_intraday_pipelines(),
            *global_reference_pipelines(),
            *industry_evidence_pipelines(),
        ),
    )
