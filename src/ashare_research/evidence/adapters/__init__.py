"""Adapter namespace for stable external evidence sources."""

from .registry import EvidenceAdapterRegistry
from .runner import EvidenceAdapterRunner
from .schemas import EvidenceAdapterError, EvidenceAdapterSpec, spec_from_candidate, validate_adapter_spec

__all__ = [
    "EvidenceAdapterError",
    "EvidenceAdapterRegistry",
    "EvidenceAdapterRunner",
    "EvidenceAdapterSpec",
    "spec_from_candidate",
    "validate_adapter_spec",
]
