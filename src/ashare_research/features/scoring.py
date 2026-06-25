from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..schemas import FeatureError


DEFAULT_SCORING_PROFILE: dict[str, Any] = {
    "schema": "ashare.feature_scoring_profile.v1",
    "profile_id": "default.v1",
    "version": "v1",
    "description": "Default explainable screening profile. Scores are ranking signals, not strategy decisions.",
    "features": {
        "market_strength": {
            "weights": {"window_return": 1.0, "amount_excess": 2.0},
            "params": {"amount_excess_floor": -1.0, "amount_excess_cap": 3.0},
        },
        "industry_strength": {
            "weights": {"window_return": 1.0, "amount_excess": 2.0},
            "params": {"amount_excess_floor": -1.0, "amount_excess_cap": 3.0},
        },
        "concept_strength": {
            "weights": {"window_return": 1.0, "latest_pct": 0.5, "leading_pct": 0.3, "breadth": 2.0},
            "params": {},
        },
        "limit_sentiment": {
            "weights": {"up_count": 1.0, "down_count": -1.0, "ths_count": 0.5},
            "params": {},
        },
        "leader_validation": {
            "weights": {
                "window_return": 0.7,
                "amount_excess": 4.0,
                "large_cap": 1.0,
                "moneyflow_rate": 0.3,
                "top_list_count": 4.0,
                "limit_pool_count": 2.0,
            },
            "params": {"large_cap_divisor": 200000.0, "large_cap_cap": 8.0},
        },
        "elasticity_candidates": {
            "weights": {
                "window_return": 1.0,
                "amount_excess": 5.0,
                "turnover": 0.6,
                "moneyflow_rate": 0.7,
                "top_list_count": 1.5,
                "limit_pool_count": 3.0,
                "size_penalty": -1.0,
            },
            "params": {"size_penalty_divisor": 500000.0, "size_penalty_cap": 8.0},
        },
    },
}


@dataclass(frozen=True)
class FeatureScoreConfig:
    feature: str
    weights: dict[str, float] = field(default_factory=dict)
    params: dict[str, float] = field(default_factory=dict)

    def weight(self, name: str, default: float = 0.0) -> float:
        return float(self.weights.get(name, default))

    def param(self, name: str, default: float = 0.0) -> float:
        return float(self.params.get(name, default))

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "weights": dict(self.weights),
            "params": dict(self.params),
        }


@dataclass(frozen=True)
class ScoringProfile:
    profile_id: str
    version: str
    features: dict[str, FeatureScoreConfig]
    description: str = ""
    source_path: str | None = None
    schema: str = "ashare.feature_scoring_profile.v1"

    @classmethod
    def builtin(cls) -> "ScoringProfile":
        return cls.from_dict(DEFAULT_SCORING_PROFILE)

    @classmethod
    def from_file(cls, path: Path | str) -> "ScoringProfile":
        source = Path(path)
        if not source.exists():
            raise FeatureError(f"scoring profile not found: {source}")
        payload = json.loads(source.read_text(encoding="utf-8"))
        merged = _deep_merge(DEFAULT_SCORING_PROFILE, payload)
        return cls.from_dict(merged, source_path=str(source))

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, source_path: str | None = None) -> "ScoringProfile":
        if str(payload.get("schema", "ashare.feature_scoring_profile.v1")) != "ashare.feature_scoring_profile.v1":
            raise FeatureError("invalid scoring profile schema")
        raw_features = dict(payload.get("features") or {})
        features = {
            str(name): FeatureScoreConfig(
                feature=str(name),
                weights={str(key): float(value) for key, value in dict(config.get("weights") or {}).items()},
                params={str(key): float(value) for key, value in dict(config.get("params") or {}).items()},
            )
            for name, config in raw_features.items()
        }
        return cls(
            schema=str(payload.get("schema", "ashare.feature_scoring_profile.v1")),
            profile_id=str(payload.get("profile_id", "default.v1")),
            version=str(payload.get("version", "v1")),
            description=str(payload.get("description", "")),
            features=features,
            source_path=source_path,
        )

    def require(self, feature: str) -> FeatureScoreConfig:
        config = self.features.get(feature)
        if config is None:
            raise FeatureError(f"{feature}: scoring profile {self.profile_id!r} has no feature config")
        return config

    def metadata(self, feature: str) -> dict[str, Any]:
        config = self.require(feature)
        return {
            "schema": self.schema,
            "profile_id": self.profile_id,
            "version": self.version,
            "profile_hash": self.profile_hash(),
            "source_path": self.source_path,
            "feature": feature,
            "config": config.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "profile_id": self.profile_id,
            "version": self.version,
            "description": self.description,
            "features": {
                name: {"weights": dict(config.weights), "params": dict(config.params)}
                for name, config in sorted(self.features.items())
            },
        }

    def profile_hash(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = json.loads(json.dumps(base, ensure_ascii=False))
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(output.get(key), dict):
            output[key] = _deep_merge(output[key], value)
        else:
            output[key] = value
    return output
