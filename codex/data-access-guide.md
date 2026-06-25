# 数据访问指南

本文档是命令参考，不是默认研究流程。Codex 应先读 `SKILL.md` 和 `codex/data-map.md`，明确要验证的事实，再用这里的命令检查、抽样、补数或留痕。

## 读取优先级

1. 用户提供的数据和约束。
2. 本地数据地图：`codex/data-map.md`。
3. 本地 mart / feature / evidence / knowledge。
4. 数据不足时的权威来源：`codex/source-registry.md`。
5. 可选辅助：capability、context、protocol、playbook。
6. 不直接把 `data/raw` 当默认分析输入。

## 健康检查

```bash
uv run ashare daily status --as-of YYYYMMDD --format json
uv run ashare data check --as-of YYYYMMDD --format json
```

若状态不是 `ready`，结论必须降级，并说明 blocking、degraded 或 warnings 的影响。

## 数据目录

```bash
uv run ashare data list --format json
uv run ashare connectors list --format json
```

用它确认项目当前注册了哪些 dataset 和 connector。不要靠记忆假设某个接口存在。

## Mart

```bash
uv run ashare mart meta daily --trade-date YYYYMMDD
uv run ashare mart read daily --trade-date YYYYMMDD --limit 20 --format json
uv run ashare mart read dc_index --trade-date YYYYMMDD --format json
```

Mart 是项目内结构化事实源。行情、公告、财务、资金等事实优先使用 mart，外部搜索不能覆盖 mart 已有事实。

## Feature

```bash
uv run ashare feature meta concept_strength --as-of YYYYMMDD --window 20
uv run ashare feature read concept_strength --as-of YYYYMMDD --window 20 --limit 50 --format json
uv run ashare feature read leader_validation --as-of YYYYMMDD --window 20 --limit 50 --format json
uv run ashare feature read elasticity_candidates --as-of YYYYMMDD --window 20 --limit 50 --format json
```

使用 feature 前必须查看 meta 中的 `inputs`、`quality_status`、`quality`、窗口和分区日期。Feature 只做筛查、排序和线索发现，不能只凭分数下结论。

## Evidence

```bash
uv run ashare evidence search --industry INDUSTRY --format json
uv run ashare evidence search --company COMPANY --format json
uv run ashare evidence ingest evidence.json
uv run ashare evidence adapter-candidates --min-records 3
```

Evidence 用于补充项目内 mart 覆盖不了的产业事实，如价格、订单、产能、capex、政策、招投标和协会数据。

## Knowledge

```bash
uv run ashare knowledge taxonomy --format json
uv run ashare knowledge search --entity ENTITY --format json
uv run ashare knowledge propose knowledge.json --reason "source checked"
uv run ashare knowledge accept PROPOSAL_ID
```

Codex 默认只能写入 proposed knowledge。进入 current knowledge 的记录必须经过 accept。新增 knowledge 前必须遵守 taxonomy 中的实体类型、predicate 和关系方向。

## Capability 和 Context

```bash
uv run ashare capabilities list --format json
uv run ashare capabilities show CAPABILITY_ID --format json
uv run ashare context build market-structure --as-of YYYYMMDD --trade-days 120
uv run ashare context build industry INDUSTRY --as-of YYYYMMDD
uv run ashare context build stock TS_CODE --as-of YYYYMMDD
```

Capability 是问题到数据能力的索引。Context pack 是可选快照和下钻便利包。二者都不是默认研究入口，也不生成分析结论。

## Protocol 和 Run

```bash
uv run ashare protocols list --format json
uv run ashare protocols validate
uv run ashare protocols output-schema industry_chain_selection.v1
uv run ashare runs record --question "..." --protocol PROTOCOL_ID --as-of YYYYMMDD --validated-output output.json
```

Protocol 约束输出形状，`suggested_capabilities` 只提示可用数据能力。Run 记录分析过程和 artifact hash。Run 不回流为事实源。
