# A 股研究数据平台重构架构

Status: implemented baseline
Updated: 2026-06-24
Scope: greenfield rewrite of `ashare-research-platform` from `ashare-data-provider`, data contracts, Codex research workflow
Rewrite mode: no compatibility guarantee

## 1. 目标

本项目应从“面向接口调用和本地 mart 的 A 股数据 Provider”升级为“可复现、可审计、可扩展的 A 股研究数据平台”。

目标架构围绕一条清晰链路展开：

```text
connectors
  -> raw_store
  -> datasets / mart / feature_mart
  -> evidence_store
  -> knowledge_base
  -> context_packs
  -> protocols
  -> reports / runs
```

核心目标：

- 分离原始事实、加工事实、分析特征、外部证据、慢变量知识、LLM 上下文和最终结论。
- 让每次分析都能追溯数据来源、采集时间、处理版本、上下文 hash、协议版本和输出校验结果。
- 让 LLM 读取稳定的 `context_packs`，而不是直接扫散落的 parquet、prompt 或临时脚本。
- 将行业证据采集从 prompt 实验升级为可落库、可复用、可 adapter 化的证据层。
- 现有 `maintenance`、`analysis_bundle`、`research_context` 等模块只作为需求参考，不保留兼容语义。

## 1.1 减法原则

本次重构按“可以不计成本、可以不兼容旧语义”的假设设计。

明确做减法：

- 不保留旧 CLI 输出格式。旧命令可以删除或重写，不做 wrapper 兼容。
- 不保留 `AShareProvider` 作为分析入口。Provider 概念只保留为 source connector 的内部实现。
- 不把 `analysis_bundle` 和 `research_context` 迁移成新实现；直接重建 `context_packs`。
- 不建设独立 Validator 平台。校验作为 `datasets`、`evidence`、`protocols`、`runs` 的内嵌质量门存在。
- 不设计后台 LLM API orchestration，也不生成额外中间执行产物。用户问题和 context pack 已足够驱动 Codex 分析；protocol 仅在用户指定或需要 run 留痕时作为可选分析模板。
- 不把所有特征都落成长期大表。只有复用、回测或 run 复现需要的特征进入 `feature_mart`。
- 不把 knowledge 做成自然语言 wiki。只保存结构化实体、别名、产业链节点、关系和映射。
- 不把 reports/runs 反向当事实源。报告中的新观点必须转成 evidence、knowledge proposal 或 protocol rule 后才能复用。

保留的硬边界：

- 行情、财务、公告等项目内事实以 mart 为准。
- 产业政策、招投标、capex、价格、产能等项目外事实以 evidence 为准。
- 行业链、别名、映射等慢变量以 knowledge 为准。
- LLM 默认读取用户问题、context pack、evidence 和 knowledge；protocol 只在用户指定、已有模板适配，或 run 留痕需要时读取。

## 1.2 命名决策

重构后的项目不再是“数据 Provider”，而是 A 股研究数据平台。项目名应从 `ashare-data-provider` 更改为 `ashare-research-platform`。

命名分层：

| 层级 | 名称 | 说明 |
| --- | --- | --- |
| 仓库名 / 项目名 | `ashare-research-platform` | 表达数据、证据、知识、上下文和 run 留痕的一体化研究平台 |
| Python distribution | `ashare-research-platform` | 与项目名一致，发布包名使用短横线 |
| Python package | `ashare_research` | 新代码包名，不沿用 `ashare_data_provider` |
| CLI | `ashare` | 保持简短稳定，作为用户进入项目能力的统一命令 |
| schema namespace | `ashare.*` | 保留领域命名，例如 `ashare.context_pack.market_structure.v1` |

不再推荐使用：

- `ashare-data-provider`：语义过窄，容易把系统拉回接口封装器。
- `ashare_data_provider`：仅作为旧代码迁移来源，不作为新包名。
- `ashare-data-lab`：实验感过强，不适合可复现研究平台。

## 2. 现状判断

旧项目提供了较好的业务基础：

- `provider.py` 和 `local_store.py` 提供 Tushare 调用和本地缓存。
- `maintenance.py` 已经包含 dataset spec、access audit、daily/backfill/check/report、mart 发布和质量检查。
- `data/mart` 已形成分区化事实表。
- `analysis_bundle.py` 能生成全市场 LLM bundle。
- `research_context.py` 和 `research_summary.py` 能生成单股上下文和摘要。
- `source_policy.json` 已有来源治理和外部来源约束。
- `prompts/industry-evidence-prompt.md` 已定义外部产业证据采集 schema。
- `references/analysis-capability-catalog.md` 和 `references/maintenance-dataset-catalog.md` 已说明部分读取边界。

这些旧模块已作为重构需求来源处理，不再作为运行入口。当前主干已切换到 `ashare_research` 和 `ashare` CLI：

- `Provider` 语义已删除，数据获取由 `connectors -> raw_store -> marts` 承担。
- 独立 `feature_mart` 已覆盖市场、行业、概念、涨停情绪、龙头验证和弹性候选。
- `evidence_store` 已支持 ingest、校验、评分、去重、adapter candidate、adapter spec 和 accepted adapter 运行。
- `knowledge_base` 已支持 proposal、accept、current、search 和 snapshot。
- `context_packs` 已支持 market/industry/stock 的确定性上下文生成。
- `protocols` 已支持 registered protocol、输出 JSON Schema 和质量门声明。
- `runs` 已支持 run manifest、artifact hash、quality gates、trace report 和 replay。
- `reports/runs` 已明确为输出和留痕，不能回流为事实源。

## 3. 分层职责

| 层级 | 职责 | 不做什么 | 主要产物 |
| --- | --- | --- | --- |
| `connectors` | 获取原始数据，记录请求、来源、权限、采集时间 | 不做分析判断，不计算策略指标 | raw records, request metadata |
| `raw_store` | 不可变保存原始响应和请求上下文 | 不作为 LLM 默认读取入口 | `data/raw/...` |
| `datasets` | 注册数据集、声明 schema、分区、主键、单位、质量规则 | 不写策略结论 | dataset catalog, quality report |
| `mart` | 发布规范化事实表 | 不保存模型推断 | `data/mart/{dataset}/...` |
| `feature_mart` | 计算可复用市场结构特征 | 不输出买卖建议，不写自然语言结论 | `data/features/{feature}/...` |
| `evidence_store` | 外部产业证据采集、去重、校验、评分、adapter 晋升 | 不覆盖项目内已有行情、财报、公告事实 | `data/evidence/...` |
| `knowledge_base` | 行业链、题材、实体、别名、关系图谱 | 不代表当日市场强弱 | `data/knowledge/...` |
| `context_packs` | 将事实、特征、证据和知识组合成 LLM 可读上下文 | 不直接生成结论 | `data/context_packs/...` |
| `protocols` | 沉淀可复用分析模板、输出 schema、禁区和缺口处理 | 不替代用户当次分析框架，不绑定单一行情场景 | protocol specs |
| `reports / runs` | 保存结构化输出、报告和全过程留痕 | 不回流覆盖事实层 | `reports/...`, `runs/...` |

## 4. 目标目录结构

建议长期目录：

```text
src/ashare_research/
  connectors/
    tushare.py
    akshare.py
    exchange_announcements.py
    cninfo.py
    policy.py
    tenders.py
  raw_store/
    store.py
    metadata.py
  datasets/
    catalog.py
    specs.py
    quality.py
    lineage.py
  marts/
    publisher.py
    reader.py
    partitions.py
  features/
    recipes.py
    market_strength.py
    industry_rotation.py
    concept_breadth.py
    leader_validation.py
    elasticity.py
    limit_sentiment.py
  evidence/
    schemas.py
    store.py
    quality.py
    scoring.py
    adapters/
  knowledge/
    schemas.py
    graph.py
    aliases.py
    taxonomy.py
  context_packs/
    schemas.py
    builders.py
    market.py
    industry.py
    stock.py
    evidence.py
  protocols/
    schemas.py
    registry.py
    specs/
  reports/
    renderers.py
  runs/
    manifest.py
    recorder.py
    quality_gates.py
    replay.py
```

建议数据目录：

```text
data/raw/
data/mart/
data/features/
data/evidence/
data/knowledge/
data/context_packs/
runs/
reports/
```

## 5. 旧模块处置策略

本次不是渐进式迁移，而是绿地重建。旧模块的价值是提供业务口径、测试样本和数据经验，不承担兼容约束。

Implementation note: 第一阶段重构已经将旧 `src/ashare_data_provider` 包和旧 `scripts/` 入口从代码树删除。下表中的旧路径仅用于记录迁移来源和口径出处。

Provider clarification: 删除旧 `AShareProvider` 不等于删除数据获取能力。新链路应由 `connectors` 获取 source records，`raw_store` 留存原始请求和响应，`marts/publisher.py` 发布规范化 mart。当前已落地 `TushareConnector -> RawStore -> MartPublisher -> ashare data build/update` 的最小闭环。

| 当前模块/目录 | 处置 | 新归属 |
| --- | --- | --- |
| `src/ashare_data_provider/client.py` | 复用请求细节，重写为 source connector | `connectors/tushare.py` |
| `src/ashare_data_provider/provider.py` | 删除 public provider 语义；不再作为统一分析 API | `connectors` 内部能力 |
| `src/ashare_data_provider/local_store.py` | 重写为不可变 raw store | `raw_store/store.py` |
| `src/ashare_data_provider/maintenance.py` | 拆解后废弃原文件 | `datasets`, `marts` |
| `data/mart` | 可以保留现有文件作 bootstrap，但新 schema 重新发布 | `mart` |
| `src/ashare_data_provider/analysis_bundle.py` | 废弃 bundle 语义，重建 context pack | `context_packs/market.py` |
| `src/ashare_data_provider/research_context.py` | 废弃旧 context schema，重建 stock context pack | `context_packs/stock.py` |
| `src/ashare_data_provider/research_summary.py` | 废弃旧 summary schema，报告由 Codex 分析后渲染 | `reports/renderers.py` |
| `prompts/industry-evidence-prompt.md` | 只作历史参考，不作为 runtime 输入；稳定后可重写为 protocol | `docs` 或 `protocols/specs` |
| `references/industry-evidence-design.md` | 合并进 evidence 设计，不作为 runtime 输入 | `docs`, `evidence` |
| `reports/*.json` | 只作历史样本；不读取为事实源 | `runs` fixtures 或丢弃 |

旧测试也不要求保持逐字输出兼容。只保留能验证业务事实的 fixtures，例如某日 mart 分区、覆盖率、空分区策略、涨停池样本、证据样本。

## 6. 数据契约

每个 dataset 必须有显式契约，不能只靠 parquet 列名推断语义。

建议 `DatasetSpec` 至少包含：

```json
{
  "name": "daily",
  "title": "A 股日线行情",
  "source": "tushare",
  "source_api": "daily",
  "partition_keys": ["trade_date"],
  "primary_key": ["trade_date", "ts_code"],
  "required_columns": ["ts_code", "trade_date", "open", "high", "low", "close", "pct_chg", "vol", "amount"],
  "column_types": {
    "ts_code": "string",
    "trade_date": "date_yyyymmdd",
    "close": "float64",
    "amount": "float64"
  },
  "units": {
    "vol": "手",
    "amount": "千元"
  },
  "empty_policy": "forbid_empty",
  "freshness": {
    "expected_lag": "T+0_after_20:00",
    "stale_after_days": 2
  },
  "lineage": {
    "raw_source_required": true,
    "source_policy_required": true
  }
}
```

关键要求：

- 所有金额单位必须写入 `units`，例如元、万元、千元，避免分析层混用。
- 所有分区表必须定义 `partition_keys`。
- 能唯一定位行的数据必须定义 `primary_key` 或 `unique_key`。
- 稀疏表必须写清 `empty_policy`，例如公告、业绩预告可以健康空分区，日线行情不能。
- 每个 mart 分区旁边必须有 `_meta.json`，包含行数、列、质量状态、来源摘要、发布版本、发布时间。
- LLM 默认不得读取没有契约的数据集。

## 7. Feature Mart 设计

`feature_mart` 保存分析特征，不保存最终结论。

示例 feature：

| Feature | 输入 | 输出 | 用途 |
| --- | --- | --- | --- |
| `market_strength` | `index_daily`, `index_dailybasic` | 指数 5/20/60 日强弱、成交、估值 | 判断市场环境 |
| `industry_strength` | `sw_daily`, `ci_daily`, `index_member_all`, `daily` | 行业涨跌、趋势、广度、成交放大 | 行业轮动 |
| `concept_strength` | `ths_index`, `ths_member`, `dc_index`, `dc_member`, `daily`, `moneyflow_cnt_ths` | 概念强弱、成分广度、资金 | 题材下钻 |
| `limit_sentiment` | `limit_list_d`, `limit_list_ths`, `limit_step`, `limit_cpt_list` | 涨停数量、连板高度、封板质量 | 短线情绪 |
| `leader_validation` | `daily`, `daily_basic`, `moneyflow_dc`, `top_list`, `ths_hot`, `dc_hot` | 大票/龙头是否验证方向 | 主线确认 |
| `elasticity_candidates` | `daily`, `daily_basic`, `limit_list_ths`, concept membership | 高弹性候选评分 | 候选池生成 |

Feature recipe 应声明：

```json
{
  "feature_name": "industry_strength",
  "version": "v1",
  "as_of": "20260623",
  "windows": [5, 20, 60],
  "inputs": [
    {"dataset": "daily", "window": "60_trade_days"},
    {"dataset": "daily_basic", "window": "60_trade_days"},
    {"dataset": "index_member_all", "snapshot": "latest"}
  ],
  "outputs": {
    "partition_keys": ["as_of", "window"],
    "primary_key": ["as_of", "window", "industry_code"]
  }
}
```

Feature 层可以输出评分，但评分必须是可复现算法结果，不能写“推荐买入”“确定主线”等结论。

## 8. Evidence Store 设计

外部证据用于补项目 mart 覆盖不了的产业事实，例如政策、订单、招投标、产能、库存、价格、海外 capex、行业协会数据。

Evidence record：

```json
{
  "evidence_id": "sha256(source_url + metric + period + value)",
  "claim": "Microsoft FY2026 Q1 capital expenditures were $34.9 billion, driven by cloud and AI demand.",
  "topic": "capex",
  "industry": "ai_infrastructure",
  "product": "data_center",
  "company": "Microsoft",
  "region": "United States",
  "metric": "capital_expenditures",
  "value": 34.9,
  "unit": "USD billion",
  "period": "FY2026 Q1",
  "frequency": "quarterly",
  "source_type": "company_ir",
  "source_name": "Microsoft Investor Relations",
  "source_url": "https://...",
  "published_at": "2025-10-29",
  "query_time": "2026-06-24T15:26:50+08:00",
  "confidence": "high",
  "verification": "official_single_source",
  "needs_adapter": true,
  "raw_excerpt": "short compliant excerpt",
  "supports": ["ai_infra_capex_trend"]
}
```

Evidence 规则：

- 项目 mart 已覆盖的行情、资金、公告、财务事实，不允许被外部证据覆盖。
- 公司级订单、客户、产能、产品进展，必须来自公告、年报、公司 IR、交易所问询回复或官方互动平台。
- 关键结论只接受项目 mart、官方披露、公司披露、协会/交易所/价格指数等 source_type 白名单内的可追溯来源。
- 数值证据必须有 `metric/value/unit/period`。
- 每条证据必须有 `source_url/published_at/query_time/confidence/verification`。
- 重复出现且影响评分、排名或回测的来源，必须晋升为 adapter candidate。

Evidence store 应提供：

- `ingest_evidence(json)`
- `validate_evidence(record)`
- `dedupe_evidence(records)`
- `score_confidence(record)`
- `find_evidence(topic, industry, company, period)`
- `collect_evidence(question, as_of)`
- `export_evidence_records(query, output_path)`

## 9. Knowledge Base 设计

`knowledge_base` 保存慢变量知识，不表示当日行情强弱。

建议知识类型：

| 类型 | 示例 | 用途 |
| --- | --- | --- |
| 实体别名 | `长飞光纤`, `YOFC`, `601869.SH` | 搜索、映射和去重 |
| 产品别名 | `空芯光纤`, `hollow-core fiber`, `HCF` | 外部证据检索 |
| 行业链节点 | `AI 算力 -> 高速互连 -> 光纤/CPO -> 材料` | 产业链拆解 |
| 公司-产品关系 | `三孚股份 -> 高纯四氯化硅` | 受益路径 |
| 题材-成分映射补充 | `金刚石散热 -> 培育钻石/第四代半导体` | 概念下钻 |
| 证据源地图 | 行业主题到优先 source group | 受控外部发现 |

Knowledge record：

```json
{
  "id": "company_product:sanfu:high_purity_silicon_tetrachloride",
  "subject": {"type": "company", "id": "603938.SH", "name": "三孚股份"},
  "predicate": "has_product_exposure",
  "object": {"type": "product", "id": "high_purity_silicon_tetrachloride", "name": "高纯四氯化硅"},
  "confidence": "medium",
  "source": {
    "source_type": "company_filing",
    "source_url": "https://...",
    "published_at": "2026-04-15"
  },
  "valid_from": "2026-04-15",
  "valid_to": null,
  "updated_at": "2026-06-24T00:00:00+08:00"
}
```

Knowledge 可以由 evidence 提炼而来，但必须保留原证据链接。

## 10. Context Packs

Context pack 是 LLM 默认读取的数据产品，必须由代码确定性生成。

Context pack 不应直接生成结论。它只组织事实、特征、证据、知识和缺口。

用户不需要手动生成 context pack。Codex 可以直接读取 mart/feature/evidence/knowledge，也可以在分析前调用 context builder 生成一个临时 context。只有当本次分析需要留痕或复盘时，context snapshot 才必须随 run 固化。

常见 pack：

```text
market_structure_pack_{as_of}.json
industry_pack_{industry}_{as_of}.json
stock_pack_{ts_code}_{as_of}.json
```

Market structure pack 示例结构：

```json
{
  "schema": "ashare.context_pack.market_structure.v1",
  "pack_id": "market_structure:20260623:120d:v1",
  "generated_at": "2026-06-24T15:30:00+08:00",
  "as_of": "20260623",
  "window": {"trade_days": 120, "start_trade_date": "20251219", "end_trade_date": "20260623"},
  "inputs": [
    {"kind": "mart", "dataset": "daily", "partitions": "120_trade_days", "content_hash": "..."},
    {"kind": "feature", "feature": "industry_strength", "version": "v1", "content_hash": "..."}
  ],
  "sections": {
    "market": {},
    "industry_strength": {},
    "concept_strength": {},
    "leader_validation": {},
    "limit_sentiment": {},
    "data_gaps": []
  },
  "constraints": {
    "latest_complete_trade_date": "20260623",
    "intraday_available": false
  }
}
```

Context pack 必须包含：

- schema version
- generated_at
- as_of
- input dataset/feature/evidence hash
- data freshness
- data gaps
- skipped sources
- source policy summary

## 11. Protocols

Protocol 是稳定研究流程的后置沉淀，不是分析前置依赖。

默认情况下，用户在 Codex 对话中给出的分析框架就是本次分析的约束。Codex 可以将它规范化为本次 run 的 `ad_hoc_protocol`，随 run 一起保存，不要求预先写入协议库。只有当某个框架被反复使用、输出结构稳定、质量门也稳定后，才沉淀为注册协议。

可选沉淀路径：

```text
Codex 对话中的一次性框架
  -> run 内 ad_hoc_protocol
  -> 可选进入 prompts/ 作为半稳定研究框架
  -> 反复验证后进入 protocols/ 作为稳定可校验协议
```

因此，重构早期不应急着整理策略或研究框架。项目先保证数据、证据、知识、context 和 runs 可靠；分析方法由用户当前提示词和 Codex 推理共同完成。

Protocol 可以有三种状态，但重构早期只要求支持 `ad_hoc_protocol`：

- `ad_hoc_protocol`：本次 run 临时生成，来源是用户当前提示词。
- `prompt_backed_protocol`：可选状态，来源是 `prompts/` 中的半稳定研究提示词。
- `registered_protocol`：稳定协议，进入 `protocols/`，具备输出 schema 和质量门。

Protocol 定义：

- 分析问题类型。
- 必读 context pack。
- 可选 context pack。
- 禁止使用的数据源或结论。
- 输出 JSON schema。
- 缺口处理规则。
- 事实、推断、假设的区分规则。
- 模型输出校验规则。

校验不做成独立平台。每个 protocol 只声明少量不可绕过的质量门：

| 质量门 | 目的 | 失败处理 |
| --- | --- | --- |
| `schema_gate` | 输出必须符合协议 schema | run 失败 |
| `freshness_gate` | 核心 context 日期必须满足协议要求 | 核心数据过期则阻断 |
| `gap_gate` | 关键缺口下不能输出确定结论 | 降级为条件推演或阻断 |
| `source_gate` | 外部证据必须符合 source policy | 移除证据或降级置信度 |
| `confidence_gate` | 置信度不能高于证据等级允许范围 | 降级置信度并写 warning |

反证检查、引用检查、claim scope 检查不做复杂自动推理；先由 protocol 要求 Codex 在输出中显式列出 `supporting_evidence`、`contradicting_evidence`、`missing_data` 和 `invalid_if`。Run 质量门只做字段存在性、来源合法性和置信度上限检查。

示例：

```json
{
  "protocol_id": "market_structure.v1",
  "title": "市场结构分析",
  "required_contexts": ["market_structure"],
  "optional_inputs": ["evidence_records", "knowledge_snapshot"],
  "required_sections": [
    "era_direction",
    "industry_chain",
    "revaluation_segments",
    "leader_validation",
    "elastic_candidates",
    "volume_trend_confirmation"
  ],
  "forbidden": [
    "Do not use reports/runs as factual source",
    "Do not use sources outside the evidence source_type whitelist",
    "Do not issue direct buy/sell advice"
  ],
  "output_schema": "ashare.protocol_output.market_structure.v1",
  "gap_policy": {
    "missing_market_data": "block",
    "missing_external_evidence": "degrade_with_gap",
    "missing_intraday_data": "state_no_realtime"
  }
}
```

现有 prompt 文件只作为历史参考，不作为新链路的运行依赖。只有未来某个研究框架反复使用且结构稳定后，才考虑升级为：

```text
protocols/specs/market_structure.v1.json
protocols/specs/industry_evidence_collection.v1.json
protocols/specs/single_stock_prism.v1.json
```

## 12. Codex 交互式分析和 Runs

真实入口是用户打开 Codex 进入本项目，然后直接给出分析请求：

```text
按这个框架做市场结构分析：...
分析 601869.SH 长飞光纤...
用 Prism 三层框架看创新药链...
```

Codex 本身就是分析工作台。项目不需要再提供一个“分析执行器”，只需要提供稳定的数据读取、证据、知识、context 和 run 留痕能力。

标准流程：

1. 用户在 Codex 中给出问题、分析框架、协议名或个股。
2. Codex 优先服从当次指令；只有用户指定或已有模板明显适配时才读取 registered protocol。
3. Codex 用项目 CLI/reader 检查 mart、feature、evidence、knowledge 的可用性。
4. Codex 直接读取 mart/feature/evidence/knowledge，或按需生成临时 context pack。
5. Codex 按用户问题、当次框架、项目基础数据和必要外部证据分析。
6. 如需要留痕，Codex 将 question、ad hoc/registered protocol、context、evidence、knowledge、输出和质量门写入 run 目录。

用户自然语言问题就是任务入口；protocol 是可选分析模板；context pack 只是可复现的事实快照，不是用户必须管理的前置产物。

Run 目录建议：

```text
runs/
  20260624T153000_market_structure_ai_infra/
    run.json
    question.md
    protocol.json
    context_pack.json
    evidence.jsonl
    knowledge_snapshot.json
    model_output.raw.md
    model_output.validated.json
    quality_gates.json
    report.md
    artifacts/
```

`run.json`：

```json
{
  "run_id": "20260624T153000_market_structure_ai_infra",
  "protocol_id": "market_structure.v1",
  "protocol_version": "v1",
  "created_at": "2026-06-24T15:30:00+08:00",
  "as_of": "20260623",
  "context_packs": [
    {"pack_id": "market_structure:20260623:120d:v1", "sha256": "..."}
  ],
  "evidence": {"path": "evidence.jsonl", "sha256": "..."},
  "knowledge": {"path": "knowledge_snapshot.json", "sha256": "..."},
  "model": {
    "provider": "openai",
    "name": "codex",
    "temperature": null
  },
  "quality_gates": {
    "schema_gate": "passed",
    "freshness_gate": "passed",
    "gap_gate": "passed",
    "source_gate": "passed",
    "confidence_gate": "warning"
  },
  "outputs": {
    "validated_json": "model_output.validated.json",
    "report": "report.md"
  }
}
```

`reports / runs` 只能是输出和留痕，不能回流为事实源。若报告中的观点需要沉淀，应由人工审核后转成 knowledge 或 protocol rule，并保留来源。

## 13. 读取原则

默认读取顺序：

1. `ashare data check` 判断数据可分析状态。
2. `feature_mart` 提供市场结构特征。
3. `evidence_store` 补产业外部证据。
4. `knowledge_base` 补慢变量关系和别名。
5. `context_packs` 组装 Codex 默认输入。
6. `protocols` 约束输出。
7. `runs` 保存留痕。

LLM 禁止默认直接读：

- `data/raw`
- 未注册 mart 表
- 没有 schema 的临时文件
- 历史 `reports/*.json` 作为事实源
- 未校验外部证据

允许直接读 mart 的场景：

- 数据工程排查。
- feature recipe 开发。
- 明确需要复核底层字段。

## 14. CLI 设计建议

CLI 按新架构重建，不保留旧命令兼容。

```text
ashare data list
ashare data build --as-of 20260623
ashare data check --as-of 20260623
ashare mart read daily --trade-date 20260623 --limit 5

ashare feature build industry-strength --as-of 20260623 --windows 5,20,60
ashare feature read industry-strength --as-of 20260623 --window 20

ashare evidence ingest evidence.json
ashare evidence search --industry ai_infrastructure --topic capex
ashare evidence collect --question "AI 算力硬件链是否被基本面验证"
ashare evidence export evidence.jsonl --industry ai_infrastructure --topic capex

ashare knowledge propose knowledge.json --reason "company filing checked"
ashare knowledge proposals
ashare knowledge accept <proposal_id>
ashare knowledge search --entity 长飞光纤
ashare knowledge snapshot --output data/knowledge/snapshot.json

ashare context build market-structure --as-of 20260623 --trade-days 120
ashare context build stock 601869.SH --as-of 20260623

ashare protocols list
ashare protocols validate market_structure.v1

ashare runs record --question "按我刚才给的框架分析 AI 算力硬件链" --as-of 20260623 --context-pack data/context_packs/market_structure/as_of=20260623/context.json
ashare runs record --question "按市场结构模板分析 AI 算力硬件链" --protocol market_structure.v1 --as-of 20260623 --context-pack data/context_packs/market_structure/as_of=20260623/context.json
ashare runs replay runs/20260624T153000_market_structure_ai_infra
```

## 15. 重建计划

本节是绿地重建计划，不要求旧入口兼容。旧代码可以在同一 PR 或连续 PR 中删除，只要新链路能覆盖目标能力。

### Phase 0: 契约冻结

交付：

- 本架构文档。
- 第一版 schema：`DatasetSpec`、`MartPartitionMeta`、`FeatureSpec`、`EvidenceRecord`、`KnowledgeSnapshot`、`ContextPack`、`AnalysisProtocol`、`RunManifest`、`AnalysisOutput`。
- 第一版 source policy registry。

验收：

- schema 有最小 fixture。
- 目录边界和事实源边界清楚。
- 旧 reports/runs 明确不可作为事实源。

### Phase 1: Storage 和 Dataset Kernel

交付：

- `raw_store`：不可变原始响应存储。
- `datasets/catalog.py`：数据集注册。
- `marts/reader.py` 和 `marts/publisher.py`：统一读写 mart。
- `datasets/quality.py`：分区级质量检查。

验收：

- 能发布并读取 `trade_cal`、`stock_basic`、`daily`、`daily_basic`、`index_daily`。
- 每个 mart 分区都有 `_meta.json`。
- 不需要手写 `glob + read_parquet + concat`。

### Phase 2: Connectors

Implementation note: 当前已落地 `ConnectorRegistry`、`connectors/tushare.py`、`connectors/akshare.py`、HTTP JSON connector、官方公告、巨潮、政策和招投标 connector wrapper、`raw_store/store.py`、`ashare connectors list/fetch` 以及 `ashare data build/update` 最小 mart 发布闭环。专用字段映射和站点级 adapter 可继续在各 connector 内加深，但 connector 边界已经切换到新架构。

交付：

- `connectors/tushare.py`
- `connectors/akshare.py`
- `connectors/official.py`
- `connectors/cninfo.py`
- `connectors/policy.py`
- `connectors/tenders.py`

验收：

- connector 只返回 raw records 和 source metadata。
- 权限、source policy、请求参数、采集时间都能追溯。
- connector 不计算特征、不写分析结论。

### Phase 3: Feature Mart

Implementation note: 当前已落地 `market_strength`、`industry_strength`、`concept_strength`、`limit_sentiment`、`leader_validation`、`elasticity_candidates` 的 v1 builder、store、CLI 和测试。Feature 只输出结构化特征和评分，不输出自然语言结论。

交付：

- `market_strength`
- `industry_strength`
- `concept_strength`
- `limit_sentiment`
- `leader_validation`
- `elasticity_candidates`

验收：

- 每个 feature 都声明输入、窗口、输出 schema 和版本。
- 同一 as_of 和同一输入 hash 下结果可复现。
- Feature 只输出结构化特征和评分，不输出自然语言结论。

### Phase 4: Evidence Store

Implementation note: 当前已落地 `EvidenceRecord`、`EvidenceStore`、证据校验、置信度评分、去重、JSON/JSONL ingest、search/list/export/collect CLI、adapter candidate 生成、`EvidenceAdapterSpec`、`EvidenceAdapterRegistry`、candidate -> proposed adapter spec 晋升、accepted adapter runner 和测试。`collect` 仍只记录开放式采集缺口，不伪装成外网搜索器；可复用数值来源应通过 accepted adapter spec 运行入库。

交付：

- `evidence/schemas.py`
- `evidence/store.py`
- `evidence/quality.py`
- `evidence/scoring.py`
- `evidence/adapters/` 骨架。

验收：

- Prompt evidence、curated evidence、adapter evidence 三类成熟度可区分。
- 缺 `source_url/published_at/query_time/confidence` 的证据不能入库。
- 高频数值证据能生成 adapter candidate。

### Phase 5: Knowledge Base

Implementation note: 当前已落地 `KnowledgeRecord`、`KnowledgeStore`、proposal/accept 决策流、current snapshot、alias index、edge list、CLI 和测试。CLI 不提供直接写 current 的命令；Codex 侧默认只能写入 `proposals.jsonl`，进入 `current.jsonl` 必须经过 `accept`。

交付：

- `knowledge/schemas.py`
- `knowledge/taxonomy.py`
- `knowledge/aliases.py`
- `knowledge/graph.py`
- `knowledge/proposals.py`

验收：

- Codex 只能写 proposed knowledge。
- current knowledge 必须来自 accepted proposal 或人工维护。
- 每个节点、别名、关系、映射都能追溯 evidence 或 source。

### Phase 6: Context Packs

Implementation note: 当前已落地 `ContextPackBuilder`、market/industry/stock pack、input hash、coverage、data_gaps、quality_flags、provenance、source policy summary、CLI 和测试。Context pack 在缺数据时仍会生成，但必须显式记录缺口。

交付：

- `context_packs/builders.py`
- `context_packs/market.py`
- `context_packs/industry.py`
- `context_packs/stock.py`

验收：

- Codex 默认只读用户问题、context pack、evidence 和 knowledge；如果用户指定协议或本次 run 需要记录分析合约，再读取 protocol。
- 每个 context pack 都包含 input hash、coverage、data_gaps、quality_flags 和 provenance。

### Phase 7: Runs 和轻量协议记录

Implementation note: 当前已落地 `ProtocolRegistry`、`market_structure.v1` 注册协议、`ashare protocols list/show/validate`、`source_policy`、`RunRecorder`、run manifest、artifact hash、quality gates、trace report、`ashare runs record/list/replay` 和测试。`runs record` 不调用模型，只保存 Codex 分析过程和输出留痕。

交付：

- `runs/manifest.py`
- `runs/recorder.py`
- `runs/quality_gates.py`
- `runs/replay.py`
- `protocols/schemas.py`
- 可选读取 `prompts/` 中的半稳定研究框架；没有也不影响运行

验收：

- 一次 run 能保存 question、ad_hoc_protocol 或 registered_protocol、context pack、evidence、knowledge、模型原始输出、结构化输出、quality gate 结果和报告。
- 缺关键行情数据时阻断。
- 缺外部产业证据时降级并写 gap。
- 置信度不能高于证据等级允许范围。

### Phase 8: 可复用协议模板沉淀

Implementation note: 当前已落地 `market_structure.v1` registered protocol、`protocols/output_schemas/market_structure.v1.json` 输出 JSON Schema、`ashare protocols output-schema` 和注册协议校验。它是可选模板，不是默认强制框架；未来只有反复使用且输出稳定的框架继续进入 `protocols/specs/*.json`。

交付：

- 从高频 run 中提炼可复用框架。
- 将可复用框架从 run 或 `prompts/` 升级为 `protocols/specs/*.json`。
- 首批候选协议可以是 `market_structure.v1`、`stock_validation.v1`、`industry_evidence_collection.v1`。

验收：

- 只有反复使用且输出结构稳定的框架进入 `protocols/`。
- 每个 registered protocol 都有输出 schema、禁区、缺口策略和质量门。

### Phase 9: 删除旧入口

交付：

- 删除或归档旧 `provider`、`maintenance`、`analysis_bundle`、`research_context`、`research_summary` 语义。
- README 改为新架构入口。
- 旧 reports 只留 fixtures 或移出事实路径。

验收：

- 新 CLI 能完成最小市场结构分析 run。
- 新 run 可 replay。
- 新报告能追溯到 mart、feature、evidence、knowledge 和 protocol。

## 16. 验收标准

项目完成重构后，应满足：

- 能明确回答“这条结论来自行情事实、外部证据、知识库还是模型推断”。
- 任意 context pack 都能追溯到 mart/feature/evidence/knowledge 的版本和 hash。
- 任意 report 都能追溯到 protocol、输入 context、模型输出和校验结果。
- 缺关键行情数据时，分析被阻断，而不是降级成主观判断。
- 缺外部产业证据时，分析可以降级，但必须输出 gap。
- 外部证据不能覆盖项目已有行情、财务、公告事实。
- 高频复用的外部数值证据能晋升为 adapter。
- LLM 默认读取 context pack，不直接读取 raw store 或散 parquet。

## 17. 设计禁区

- 不把 `reports/runs` 当事实源。
- 不让 connector 计算策略指标。
- 不让 feature mart 输出买卖建议。
- 不让 context pack 写最终结论。
- 不让 protocol 隐式调用未知数据源。
- 不让外部搜索覆盖项目内已有结构化事实。
- 不在 prompt 中临时定义核心评分口径。
- 不允许金额、成交额、流量等字段缺少单位说明。

## 18. 推荐下一步

优先落地顺序：

1. `DatasetCatalog` 和 `MartReader`。
2. `FeatureRecipe` 和 `feature_mart`。
3. `EvidenceStore`。
4. `ContextPack` schema。
5. `Runs` 留痕和 replay。
6. 轻量 `ad_hoc_protocol` 记录。

最小可用目标：

```text
用户在 Codex 中输入：按以下市场结构框架分析 AI 算力硬件链，截至 20260623。
```

Codex 应完成：

- 检查 mart ready 状态。
- 构建或读取市场结构 feature。
- 读取 AI 算力相关 evidence records。
- 读取相关 knowledge。
- 生成 context pack。
- 按 protocol 运行分析。
- 保存模型输出和质量门结果。
- 渲染最终报告。

此时项目才真正具备“可审计的 LLM 投研工作流”能力。
