from __future__ import annotations

from typing import Iterable

from ..schemas import FeatureError, FeatureInputSpec, FeatureSpec


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
            analysis_columns=("strength_score",),
            input_specs=(
                FeatureInputSpec("index_daily", "price_volume", supports=("市场强弱判断",)),
                FeatureInputSpec("index_dailybasic", "valuation_liquidity", supports=("市场估值和换手辅助判断",)),
            ),
            supports=("市场强弱判断", "指数成交趋势判断"),
        ),
        FeatureSpec(
            name="industry_strength",
            title="行业指数强弱",
            version="v1",
            inputs=("sw_daily", "ci_daily"),
            partition_keys=("as_of", "window"),
            primary_key=("as_of", "window", "source_dataset", "ts_code"),
            description="申万和中信行业指数窗口收益、成交放大和趋势位置。",
            analysis_columns=("strength_score", "industry_name"),
            input_specs=(
                FeatureInputSpec("sw_daily", "sw_industry_price", supports=("申万行业强弱排序",)),
                FeatureInputSpec("ci_daily", "ci_industry_price", supports=("中信行业强弱排序",)),
                FeatureInputSpec("index_member_all", "sw_industry_hierarchy", role="degrade_if_missing", supports=("申万行业名称和层级识别",)),
                FeatureInputSpec("ci_index_member", "ci_industry_hierarchy", role="degrade_if_missing", supports=("中信行业名称和层级识别",)),
            ),
            supports=("行业强弱排序", "行业层级识别"),
        ),
        FeatureSpec(
            name="concept_strength",
            title="概念指数强弱",
            version="v1",
            inputs=("dc_index",),
            partition_keys=("as_of", "window"),
            primary_key=("as_of", "window", "source_dataset", "ts_code"),
            description="东方财富概念指数窗口涨幅、领涨成分、涨跌家数和成交热度。",
            analysis_columns=("strength_score", "name", "latest_pct_chg"),
            input_specs=(
                FeatureInputSpec("dc_index", "concept_market", supports=("题材强弱排序", "题材扩散初步确认")),
            ),
            supports=("题材强弱排序", "题材扩散初步确认"),
        ),
        FeatureSpec(
            name="limit_sentiment",
            title="涨停情绪",
            version="v1",
            inputs=("limit_list_d", "limit_list_ths"),
            partition_keys=("as_of", "window"),
            primary_key=("as_of", "window", "trade_date"),
            description="涨跌停数量、同花顺涨停池数量、开板次数和封单金额。",
            analysis_columns=("sentiment_score",),
            input_specs=(
                FeatureInputSpec("limit_list_d", "limit_count", supports=("涨跌停数量判断",)),
                FeatureInputSpec("limit_list_ths", "limit_pool", supports=("涨停池封单和连板辅助判断",)),
            ),
            supports=("短线情绪判断", "涨停结构判断"),
        ),
        FeatureSpec(
            name="leader_validation",
            title="龙头认可验证",
            version="v1",
            inputs=("daily", "daily_basic", "stock_basic", "moneyflow_dc", "top_list", "limit_list_ths"),
            partition_keys=("as_of", "window"),
            primary_key=("as_of", "window", "ts_code"),
            description="用窗口涨幅、成交放大、市值、资金流、龙虎榜和涨停池验证龙头市场认可。",
            analysis_columns=("leader_score", "sw_l1_name", "sw_l2_name", "sw_l3_name"),
            input_specs=(
                FeatureInputSpec("daily", "price_volume", supports=("龙头价格和成交趋势判断",)),
                FeatureInputSpec("daily_basic", "valuation_liquidity", supports=("市值和换手辅助判断",)),
                FeatureInputSpec("stock_basic", "stock_identity", role="degrade_if_missing", supports=("个股名称和基础行业识别",)),
                FeatureInputSpec("moneyflow_dc", "moneyflow", role="degrade_if_missing", supports=("资金确认",)),
                FeatureInputSpec("top_list", "top_list", role="degrade_if_missing", supports=("龙虎榜验证",)),
                FeatureInputSpec("limit_list_ths", "limit_pool", role="degrade_if_missing", supports=("涨停池验证",)),
                FeatureInputSpec("index_member_all", "sw_industry", role="degrade_if_missing", supports=("申万行业层级识别",)),
            ),
            supports=("龙头候选筛查", "市场认可度验证"),
        ),
        FeatureSpec(
            name="elasticity_candidates",
            title="高弹性候选",
            version="v1",
            inputs=("daily", "daily_basic", "stock_basic", "moneyflow_dc", "top_list", "limit_list_ths"),
            partition_keys=("as_of", "window"),
            primary_key=("as_of", "window", "ts_code"),
            description="用涨幅、成交放大、换手、资金流、涨停和规模惩罚筛选高弹性候选集合。",
            analysis_columns=("elasticity_score", "sw_l1_name", "sw_l2_name", "sw_l3_name"),
            input_specs=(
                FeatureInputSpec("daily", "price_volume", supports=("弹性价格和成交趋势判断",)),
                FeatureInputSpec("daily_basic", "valuation_liquidity", supports=("换手和市值辅助判断",)),
                FeatureInputSpec("stock_basic", "stock_identity", role="degrade_if_missing", supports=("个股名称和基础行业识别",)),
                FeatureInputSpec("moneyflow_dc", "moneyflow", role="degrade_if_missing", supports=("资金确认",)),
                FeatureInputSpec("top_list", "top_list", role="degrade_if_missing", supports=("龙虎榜验证",)),
                FeatureInputSpec("limit_list_ths", "limit_pool", role="degrade_if_missing", supports=("涨停池验证",)),
                FeatureInputSpec("index_member_all", "sw_industry", role="degrade_if_missing", supports=("申万行业层级识别",)),
            ),
            supports=("高弹性候选筛查", "交易弹性排序"),
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
