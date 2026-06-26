from __future__ import annotations

from collections.abc import Iterable

from ..core import UsagePolicy
from .schemas import FeatureError, FeatureInputSpec, FeatureSpec


def default_feature_specs() -> tuple[FeatureSpec, ...]:
    return (
        FeatureSpec(
            id="ashare.daily_momentum",
            title="A-share daily momentum",
            domain="ashare_core",
            version="v1",
            role="candidate_signal",
            inputs=(
                FeatureInputSpec(
                    "ashare.daily",
                    columns=("security_id", "trade_date", "pct_chg", "volume", "amount"),
                    supports=("candidate_generation", "market_context"),
                ),
            ),
            primary_key=("as_of", "window", "security_id"),
            analysis_columns=("momentum_score", "window_return_pct"),
            recommended_windows=(5, 20, 60),
            usage=UsagePolicy(
                allowed_uses=("candidate_generation", "market_context", "market_validation"),
                forbidden_uses=("company_business_exposure", "trade_execution"),
            ),
            description="Ranks A-share securities by recent return and turnover expansion from canonical EOD daily bars.",
        ),
        FeatureSpec(
            id="ashare.market_strength",
            title="A-share market index strength",
            domain="ashare_core",
            version="v1",
            role="market_context_signal",
            inputs=(
                FeatureInputSpec(
                    "ashare.index_daily",
                    columns=("index_id", "trade_date", "close", "pct_chg", "amount"),
                    supports=("market_context", "market_validation"),
                ),
                FeatureInputSpec(
                    "ashare.index_daily_basic",
                    role="degrade_if_missing",
                    columns=("index_id", "trade_date", "total_mv"),
                    supports=("market_context",),
                ),
            ),
            primary_key=("as_of", "window", "source_dataset", "index_id"),
            analysis_columns=("strength_score", "window_return_pct"),
            recommended_windows=(5, 20, 60),
            usage=UsagePolicy(
                allowed_uses=("market_context", "market_validation"),
                forbidden_uses=("candidate_generation", "company_business_exposure", "trade_execution"),
            ),
            description="Ranks broad A-share indices by window return and trading amount expansion. It is market context, not company evidence.",
        ),
        FeatureSpec(
            id="ashare.industry_strength",
            title="A-share industry index strength",
            domain="ashare_core",
            version="v1",
            role="market_context_signal",
            inputs=(
                FeatureInputSpec(
                    "ashare.sw_daily",
                    columns=("index_id", "trade_date", "close", "pct_chg", "volume"),
                    supports=("market_context", "market_validation"),
                ),
                FeatureInputSpec(
                    "ashare.ci_daily",
                    columns=("index_id", "trade_date", "close", "pct_chg", "volume"),
                    supports=("market_context", "market_validation"),
                ),
            ),
            primary_key=("as_of", "window", "source_dataset", "index_id"),
            analysis_columns=("strength_score", "window_return_pct"),
            recommended_windows=(5, 20, 60),
            usage=UsagePolicy(
                allowed_uses=("candidate_generation", "market_context", "market_validation"),
                forbidden_uses=("company_business_exposure", "trade_execution"),
            ),
            description="Ranks Shenwan and CITIC industry indices by window return and volume expansion. It is a sector signal, not business exposure proof.",
        ),
        FeatureSpec(
            id="ashare.concept_strength",
            title="A-share concept and sector strength",
            domain="ashare_core",
            version="v1",
            role="market_context_signal",
            inputs=(
                FeatureInputSpec(
                    "ashare.dc_index",
                    columns=("concept_id", "trade_date", "name", "pct_chg"),
                    supports=("candidate_generation", "market_context", "market_validation"),
                ),
            ),
            primary_key=("as_of", "window", "concept_id"),
            analysis_columns=("strength_score", "window_return_pct", "name"),
            recommended_windows=(5, 20, 60),
            usage=UsagePolicy(
                allowed_uses=("candidate_generation", "market_context", "market_validation"),
                forbidden_uses=("company_business_exposure", "trade_execution"),
            ),
            description="Ranks Eastmoney concepts and sectors by recent return. Concept strength is a market clue, not company exposure proof.",
        ),
        FeatureSpec(
            id="ashare.limit_sentiment",
            title="A-share limit-up sentiment",
            domain="ashare_core",
            version="v1",
            role="market_context_signal",
            inputs=(
                FeatureInputSpec(
                    "ashare.limit_list_d",
                    columns=("security_id", "trade_date", "name", "pct_chg", "limit"),
                    supports=("market_context", "market_validation"),
                ),
                FeatureInputSpec(
                    "ashare.limit_list_ths",
                    columns=("security_id", "trade_date", "board_tag", "open_num", "limit_order", "limit_amount"),
                    supports=("market_context", "market_validation"),
                ),
            ),
            primary_key=("as_of", "window", "trade_date"),
            analysis_columns=("sentiment_score", "limit_up_count", "ths_limit_up_count"),
            recommended_windows=(5, 20, 60),
            usage=UsagePolicy(
                allowed_uses=("candidate_generation", "market_context", "market_validation"),
                forbidden_uses=("company_business_exposure", "trade_execution"),
            ),
            description="Summarizes daily limit-up/down counts, board height, open counts, and sealed order amount. It is short-term sentiment only.",
        ),
        FeatureSpec(
            id="industry.report_attention",
            title="Industry report attention",
            domain="industry_evidence",
            version="v1",
            role="evidence_triage_signal",
            inputs=(
                FeatureInputSpec(
                    "industry.eastmoney_report_index",
                    columns=("query_date", "industry_name", "report_id", "published_at", "source_name"),
                    supports=("evidence_triage", "context"),
                ),
            ),
            primary_key=("as_of", "window", "industry_name"),
            analysis_columns=("attention_score", "report_count"),
            recommended_windows=(20,),
            usage=UsagePolicy(
                allowed_uses=("context", "evidence_triage", "research_prioritization"),
                forbidden_uses=("candidate_generation", "company_business_exposure"),
            ),
            description="Counts recent vendor report index entries by industry. It is a research attention signal, not company evidence.",
        ),
    )


class FeatureRegistry:
    def __init__(self, specs: Iterable[FeatureSpec]) -> None:
        self._specs = {spec.id: spec for spec in specs}

    @classmethod
    def builtin(cls) -> "FeatureRegistry":
        return cls(default_feature_specs())

    def get(self, feature_id: str) -> FeatureSpec | None:
        return self._specs.get(feature_id)

    def require(self, feature_id: str) -> FeatureSpec:
        spec = self.get(feature_id)
        if spec is None:
            raise FeatureError(f"{feature_id!r} is not registered in FeatureRegistry")
        return spec

    def list(self) -> list[FeatureSpec]:
        return [self._specs[feature_id] for feature_id in sorted(self._specs)]
