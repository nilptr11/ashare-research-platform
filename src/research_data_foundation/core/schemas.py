from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class SchemaError(ValueError):
    """Raised when a research data foundation schema is invalid."""


SOURCE_ROLES = {
    "canonical_eod",
    "official_disclosure",
    "intraday_observation",
    "ashare_enrichment",
    "cross_market_reference",
    "research_evidence",
}
AUTHORITY_TIERS = {"S0", "S1", "S2", "S3", "S4"}
TRANSPORTS = {"sdk", "http", "file", "manual"}
TEMPORAL_MODES = {"eod", "intraday_snapshot", "event", "filing", "reference"}
FINALITY_VALUES = {"final", "provisional", "revised"}
AVAILABLE_AFTER_VALUES = {"post_close", "realtime", "delayed", "on_demand"}
AS_OF_POLICIES = {"exact", "latest_before", "range"}
DOMAINS = {
    "ashare_core",
    "ashare_financials",
    "ashare_intraday",
    "ashare_enrichment",
    "global_reference",
    "industry_evidence",
    "relation_graph",
}
DATASET_ROLES = {
    "core_fact",
    "financial_fact",
    "reference_fact",
    "enrichment_fact",
    "provisional_observation",
    "evidence_seed",
    "feature_signal",
}
ALLOWED_USES = {
    "candidate_generation",
    "market_context",
    "feature_input",
    "market_validation",
    "context",
    "cross_market_context",
    "cross_market_validation",
    "evidence",
    "company_business_exposure",
    "evidence_triage",
    "research_prioritization",
    "ashare_primary_candidate_generation",
    "financial_analysis",
    "disclosure_context",
    "trade_execution",
}
CADENCES = {"daily_eod", "intraday", "weekly", "on_demand", "manual"}


@dataclass(frozen=True)
class TemporalPolicy:
    temporal_mode: str
    finality: str
    available_after: str
    as_of_policy: str = "exact"

    def __post_init__(self) -> None:
        _require_choice("temporal_mode", self.temporal_mode, TEMPORAL_MODES)
        _require_choice("finality", self.finality, FINALITY_VALUES)
        _require_choice("available_after", self.available_after, AVAILABLE_AFTER_VALUES)
        _require_choice("as_of_policy", self.as_of_policy, AS_OF_POLICIES)


@dataclass(frozen=True)
class UsagePolicy:
    allowed_uses: tuple[str, ...]
    forbidden_uses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.allowed_uses:
            raise SchemaError("UsagePolicy.allowed_uses is required")
        _require_choices("allowed_uses", self.allowed_uses, ALLOWED_USES)
        _require_choices("forbidden_uses", self.forbidden_uses, ALLOWED_USES)
        overlap = set(self.allowed_uses) & set(self.forbidden_uses)
        if overlap:
            raise SchemaError(f"UsagePolicy has overlapping allowed/forbidden uses: {sorted(overlap)}")

    def permits(self, use: str) -> bool:
        return use in self.allowed_uses and use not in self.forbidden_uses

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_uses": list(self.allowed_uses),
            "forbidden_uses": list(self.forbidden_uses),
        }


@dataclass(frozen=True)
class SourceSpec:
    id: str
    title: str
    source_role: str
    authority_tier: str
    transport: str
    rate_limit: dict[str, Any] = field(default_factory=dict)
    auth: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        _require_identifier("SourceSpec.id", self.id)
        if not self.title:
            raise SchemaError(f"{self.id}: SourceSpec.title is required")
        _require_choice("source_role", self.source_role, SOURCE_ROLES)
        _require_choice("authority_tier", self.authority_tier, AUTHORITY_TIERS)
        _require_choice("transport", self.transport, TRANSPORTS)


@dataclass(frozen=True)
class DatasetContract:
    id: str
    title: str
    domain: str
    market_scope: str
    role: str
    temporal: TemporalPolicy
    partition_keys: tuple[str, ...]
    primary_key: tuple[str, ...]
    required_columns: tuple[str, ...]
    usage: UsagePolicy
    units: dict[str, str] = field(default_factory=dict)
    analysis_columns: tuple[str, ...] = ()
    empty_policy: str = "forbid_empty"

    def __post_init__(self) -> None:
        _require_identifier("DatasetContract.id", self.id)
        if not self.title:
            raise SchemaError(f"{self.id}: DatasetContract.title is required")
        _require_choice("domain", self.domain, DOMAINS)
        if not self.market_scope:
            raise SchemaError(f"{self.id}: market_scope is required")
        _require_choice("role", self.role, DATASET_ROLES)
        if not self.partition_keys:
            raise SchemaError(f"{self.id}: partition_keys is required")
        if not self.primary_key:
            raise SchemaError(f"{self.id}: primary_key is required")
        if not self.required_columns:
            raise SchemaError(f"{self.id}: required_columns is required")
        if self.empty_policy not in {"forbid_empty", "allow_empty"}:
            raise SchemaError(f"{self.id}: invalid empty_policy {self.empty_policy!r}")
        missing_required_pk = [column for column in self.primary_key if column not in self.required_columns]
        if missing_required_pk:
            raise SchemaError(f"{self.id}: primary_key columns must be required: {missing_required_pk}")

    def permits(self, use: str) -> bool:
        return self.usage.permits(use)


@dataclass(frozen=True)
class LineagePolicy:
    raw_required: bool = True
    staging_required: bool = True


@dataclass(frozen=True)
class IngestionRecipe:
    id: str
    source_id: str
    source_api: str
    target_dataset_id: str
    schedule: str
    params_template: dict[str, Any] = field(default_factory=dict)
    fields: tuple[str, ...] = ()
    fanout_params: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    pagination: dict[str, Any] = field(default_factory=dict)
    field_map: dict[str, str] = field(default_factory=dict)
    numeric_columns: tuple[str, ...] = ()
    lineage: LineagePolicy = field(default_factory=LineagePolicy)
    selection_priority: int = 100
    notes: str = ""

    def __post_init__(self) -> None:
        _require_identifier("IngestionRecipe.id", self.id)
        _require_identifier("source_id", self.source_id)
        _require_identifier("target_dataset_id", self.target_dataset_id)
        if not self.source_api:
            raise SchemaError(f"{self.id}: source_api is required")
        if not self.schedule:
            raise SchemaError(f"{self.id}: schedule is required")
        if self.selection_priority < 0:
            raise SchemaError(f"{self.id}: selection_priority must be non-negative")


@dataclass(frozen=True)
class PipelineStep:
    recipe_id: str
    required: bool = False
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier("PipelineStep.recipe_id", self.recipe_id)
        _require_choices("depends_on", self.depends_on, set(self.depends_on))


@dataclass(frozen=True)
class PipelineSpec:
    id: str
    title: str
    domain: str
    cadence: str
    steps: tuple[PipelineStep, ...]
    feature_ids: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        _require_identifier("PipelineSpec.id", self.id)
        if not self.title:
            raise SchemaError(f"{self.id}: PipelineSpec.title is required")
        _require_choice("domain", self.domain, DOMAINS)
        _require_choice("cadence", self.cadence, CADENCES)
        if not self.steps:
            raise SchemaError(f"{self.id}: steps is required")
        step_ids = [step.recipe_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise SchemaError(f"{self.id}: duplicate pipeline recipe steps")
        for step in self.steps:
            unknown_dependencies = [recipe_id for recipe_id in step.depends_on if recipe_id not in step_ids]
            if unknown_dependencies:
                raise SchemaError(f"{self.id}: unknown step dependencies: {unknown_dependencies}")


def _require_identifier(field_name: str, value: str) -> None:
    if not value or not str(value).strip():
        raise SchemaError(f"{field_name} is required")


def _require_choice(field_name: str, value: str, choices: set[str]) -> None:
    if value not in choices:
        raise SchemaError(f"{field_name} must be one of {sorted(choices)}, got {value!r}")


def _require_choices(field_name: str, values: tuple[str, ...], choices: set[str]) -> None:
    invalid = [value for value in values if value not in choices]
    if invalid:
        raise SchemaError(f"{field_name} contains invalid values {invalid}; allowed: {sorted(choices)}")
