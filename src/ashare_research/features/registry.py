from __future__ import annotations

from typing import Iterable

from ..schemas import FeatureError, FeatureSpec


def default_feature_specs() -> list[FeatureSpec]:
    return [
        FeatureSpec(
            name="market_strength",
            title="市场指数强弱",
            version="v1",
            inputs=("index_daily", "index_dailybasic"),
            partition_keys=("as_of", "window"),
            primary_key=("as_of", "window", "ts_code"),
            description="指数窗口收益、成交放大和趋势位置。",
        ),
        FeatureSpec(
            name="industry_strength",
            title="行业指数强弱",
            version="v1",
            inputs=("sw_daily", "ci_daily"),
            partition_keys=("as_of", "window"),
            primary_key=("as_of", "window", "source_dataset", "ts_code"),
            description="申万和中信行业指数窗口收益、成交放大和趋势位置。",
        ),
        FeatureSpec(
            name="concept_strength",
            title="概念指数强弱",
            version="v1",
            inputs=("dc_index",),
            partition_keys=("as_of", "window"),
            primary_key=("as_of", "window", "source_dataset", "ts_code"),
            description="东方财富概念指数窗口涨幅、领涨成分、涨跌家数和成交热度。",
        ),
        FeatureSpec(
            name="limit_sentiment",
            title="涨停情绪",
            version="v1",
            inputs=("limit_list_d", "limit_list_ths"),
            partition_keys=("as_of", "window"),
            primary_key=("as_of", "window", "trade_date"),
            description="涨跌停数量、同花顺涨停池数量、开板次数和封单金额。",
        ),
        FeatureSpec(
            name="leader_validation",
            title="龙头认可验证",
            version="v1",
            inputs=("daily", "daily_basic", "stock_basic", "moneyflow_dc", "top_list", "limit_list_ths"),
            partition_keys=("as_of", "window"),
            primary_key=("as_of", "window", "ts_code"),
            description="用窗口涨幅、成交放大、市值、资金流、龙虎榜和涨停池验证龙头市场认可。",
        ),
        FeatureSpec(
            name="elasticity_candidates",
            title="高弹性候选",
            version="v1",
            inputs=("daily", "daily_basic", "stock_basic", "moneyflow_dc", "top_list", "limit_list_ths"),
            partition_keys=("as_of", "window"),
            primary_key=("as_of", "window", "ts_code"),
            description="用涨幅、成交放大、换手、资金流、涨停和规模惩罚筛选高弹性候选集合。",
        ),
    ]


class FeatureRegistry:
    def __init__(self, specs: Iterable[FeatureSpec]) -> None:
        self._specs = {spec.name: spec for spec in specs}

    @classmethod
    def builtin(cls) -> "FeatureRegistry":
        return cls(default_feature_specs())

    def get(self, name: str) -> FeatureSpec | None:
        return self._specs.get(name)

    def require(self, name: str) -> FeatureSpec:
        spec = self.get(name)
        if spec is None:
            raise FeatureError(f"{name!r} is not registered in FeatureRegistry")
        return spec

    def list(self) -> list[FeatureSpec]:
        return [self._specs[name] for name in sorted(self._specs)]
