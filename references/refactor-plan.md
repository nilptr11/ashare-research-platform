# 结构性重构方案

本方案以“最合适的目标结构”为准，不以兼容现有 CLI、旧 `DatasetSpec`、旧 `daily.py` 或旧数据目录为约束。

项目仍以 A 股研究为主域，但内部架构应升级为研究数据底座而不是外部数据湖：A 股核心 EOD 是稳定锚点，盘中数据是临时观测层，跨市场数据是参考和证据层，外部网页/API/PDF 默认登记获取方式并按需 fetch，只有被研究结论使用的 claim 才进入 evidence，关系图谱用于沉淀分析确认后的慢变量关系。

## 目标定位

本项目不是交易系统、Agent runtime 或 API 服务，而是给 LLM / Codex 使用的研究数据底座。

目标能力：

- 维护稳定、可复现的 A 股收盘后核心事实库；
- 支持盘中临时观察，但不让其覆盖收盘后事实；
- 支持港股、美股、SEC、Yahoo、东财全球资讯等跨市场参考；
- 支持研报、新闻、政策、协会、招投标、公司公告等外部材料按需获取；只将被使用的具体 claim 入 evidence；
- 支持产业链、公司、产品、客户、供应、同业和跨市场映射关系沉淀；
- 对每条结论保留数据日期、来源、证据强弱和缺口。

## 设计原则

1. Tushare 是 A 股 canonical EOD 主源。
2. 实时源只作为 provisional overlay，不覆盖 canonical mart。
3. 跨市场数据可以参与研究，但默认只能做 reference、evidence 或 context。
4. Source、Dataset、Ingestion 必须解耦。
5. Raw、Staging、Mart 必须分层，避免来源字段污染统一事实层。
6. Feature 必须声明输入、用途、降级规则和可用于哪些研究阶段。
7. Evidence 和 Relations 是研究结论可信度的核心，不是附属日志。
8. Runs / Reports 只做留痕，不回流为事实源。

## 目标分层

```text
Source Adapter
  -> Raw Store
  -> Staging Dataset
  -> Mart Dataset
  -> Feature / Evidence / Relations
  -> Run Trace / Report
```

| 层 | 目标 | 说明 |
| --- | --- | --- |
| source | 访问外部数据源 | 只负责请求、限流、鉴权、错误归一化和响应元信息 |
| raw | 原始响应留痕 | 保存请求参数、响应摘要、原始表格或 JSONL |
| staging | 来源口径清洗层 | 保留 source 字段和 source 语义，做轻量结构化 |
| mart | 统一事实层 | 项目内标准字段、分区、质量检查和 lineage |
| feature | 可复现信号层 | 排序、筛查、交叉验证；不能单独证明公司事实 |
| evidence | 可审计证据层 | 外部 claim、来源 URL、发布日期、查询时间、置信度 |
| relations | 慢变量关系层 | 公司、证券、产品、客户、供应链、产业链节点、跨市场映射 |
| runs/reports | 留痕展示层 | 记录引用材料、输出和质量门，不作为事实源 |

## 时间与事实模型

每个 dataset / feature / evidence source 都必须声明时间模式。

| 字段 | 可选值 | 含义 |
| --- | --- | --- |
| `temporal_mode` | `eod`, `intraday_snapshot`, `event`, `filing`, `reference` | 数据时间语义 |
| `finality` | `final`, `provisional`, `revised` | 是否可视为最终事实 |
| `available_after` | `post_close`, `realtime`, `delayed`, `on_demand` | 可用时点 |
| `as_of_policy` | `exact`, `latest_before`, `range` | 研究引用时如何匹配时间 |

Tushare A 股日线示例：

```yaml
source_role: canonical_eod
temporal_mode: eod
finality: final
available_after: post_close
```

腾讯 / 东财 / mootdx 盘中行情示例：

```yaml
source_role: intraday_observation
temporal_mode: intraday_snapshot
finality: provisional
available_after: realtime
```

SEC filing 示例：

```yaml
source_role: cross_market_reference
temporal_mode: filing
finality: final
available_after: on_demand
```

## 数据域

| Domain | 作用 | 是否参与 A 股主候选池 |
| --- | --- | --- |
| `ashare_core` | A 股收盘后核心事实 | 是 |
| `ashare_intraday` | A 股盘中临时观察 | 只能辅助，必须标注 provisional |
| `ashare_enrichment` | A 股增强事实和补充来源 | 可参与，但需声明 source role |
| `global_reference` | 美股、港股、SEC、Yahoo 等跨市场参考 | 默认不参与，只做验证和背景 |
| `industry_evidence` | 产业、政策、价格、协会、研报、新闻 | 不生成主候选，只支撑结论 |
| `relation_graph` | 公司、产品、客户、供应、同业、跨市场映射 | 可用于验证和扩展研究路径 |

## Source / Dataset / Recipe 解耦

旧结构把 `DatasetSpec.source` 和 `DatasetSpec.source_api` 直接绑在一起。目标结构拆为三类 registry。

### SourceSpec

描述数据源本身：

```yaml
id: tushare
title: Tushare Pro
source_role: canonical_eod
authority_tier: S3
transport: sdk
rate_limit:
  policy: provider_default
auth:
  type: token
```

```yaml
id: eastmoney_direct
title: Eastmoney Direct HTTP
source_role: enrichment_or_intraday
authority_tier: S3
transport: http
rate_limit:
  concurrency: 1
  min_interval_seconds: 1.5
```

```yaml
id: sec_edgar
title: SEC EDGAR
source_role: cross_market_reference
authority_tier: S1
transport: http
rate_limit:
  max_qps: 10
auth:
  type: user_agent
```

### DatasetContract

描述项目内数据是什么，而不是怎么抓：

```yaml
id: ashare.daily
domain: ashare_core
market_scope: cn_ashare
role: core_fact
temporal_mode: eod
finality: final
partition:
  keys: [trade_date]
primary_key: [trade_date, security_id]
required_columns:
  - security_id
  - trade_date
  - open
  - high
  - low
  - close
  - pct_chg
  - volume
  - amount
allowed_uses:
  - candidate_generation
  - market_context
  - feature_input
```

```yaml
id: global.sec_filings
domain: global_reference
market_scope: us
role: reference_fact
temporal_mode: filing
finality: final
partition:
  keys: [cik]
primary_key: [cik, accession_number]
allowed_uses:
  - evidence
  - context
  - cross_market_context
```

### IngestionRecipe

描述如何从 source 生成 dataset：

```yaml
id: tushare.daily.to_ashare_daily
source: tushare
source_api: daily
target_dataset: ashare.daily
schedule: ashare_core_eod_daily
params:
  trade_date: ${partition.trade_date}
field_map:
  ts_code: security_id
  vol: volume
lineage:
  raw_required: true
  staging_required: true
```

一个 dataset 可以有多个 recipe：

```yaml
target_dataset: ashare.moneyflow
recipes:
  - tushare.moneyflow_dc
  - eastmoney.push2his.moneyflow
selection_policy:
  primary: tushare.moneyflow_dc
  fallback: eastmoney.push2his.moneyflow
  conflict_policy: keep_both_mark_conflict
```

## Pipeline 设计

旧 `daily.py` 应拆成 pipeline registry。

```text
pipelines/
  ashare_core_eod_daily.yaml
  ashare_intraday_snapshot.yaml
  ashare_enrichment_daily.yaml
  global_reference_weekly.yaml
  research_on_demand.yaml
```

### `ashare_core_eod_daily`

目标：维护 A 股 canonical EOD 基础库。

特点：

- 以 Tushare 为主；
- 收盘后运行；
- 输出 final mart；
- 构建 A 股核心 feature；
- 失败会阻断 A 股市场研究。

包含：

- 交易日历；
- 股票身份；
- 个股日线；
- 个股日线基础指标；
- 指数日线；
- 指数估值；
- 申万 / 中信行业；
- 东方财富概念指数；
- 涨跌停；
- 龙虎榜、资金流等可选增强项。

### `ashare_intraday_snapshot`

目标：盘中临时观察。

特点：

- 数据状态永远是 provisional；
- 不覆盖 `ashare_core`；
- 分区应包含 `snapshot_at`；
- 适合盘中问答、异动观察和收盘前假设生成。

候选来源：

- 腾讯实时行情；
- 东财 push2；
- mootdx；
- 同花顺热点 / 涨停池。

### `global_reference_weekly`

目标：低频维护跨市场参考。

特点：

- 不进入 A 股主候选池；
- 用于行业背景、海外同业、客户供应链、SEC 披露和关系沉淀。

候选来源：

- SEC submissions；
- SEC companyfacts XBRL；
- SEC ticker-CIK mapping；
- Yahoo quoteSummary；
- 港股 / 美股行情与财务摘要。

### `research_on_demand`

目标：按研究问题补证。

特点：

- 按问题触发；
- 主要输出 evidence 和 relations；
- 必须保留 source URL、发布日期、query time、claim 和证据强弱。

候选来源：

- 东财个股 / 行业研报；
- 巨潮公告原文；
- 交易所公告；
- 政策和协会；
- 招投标；
- 海外公司 filing。

## 目录结构

建议重构为：

```text
src/research_data_foundation/
  core/
    ids.py
    time.py
    quality.py
    lineage.py
    registry.py
    schemas.py
  sources/
    base.py
    transports.py
    tushare.py
    akshare.py
    eastmoney.py
    cninfo.py
    sec_edgar.py
    yahoo.py
  ingestion/
    recipes.py
    runner.py
    staging.py
    publisher.py
  datasets/
    contracts.py
    reader.py
    partitions.py
  domains/
    ashare/
      contracts.py
      recipes.py
      pipelines.py
      features.py
    global_reference/
      contracts.py
      recipes.py
      pipelines.py
    industry_evidence/
      sources.py
      policies.py
  features/
    registry.py
    runner.py
    scoring.py
  evidence/
    schemas.py
    store.py
    sources.py
    quality.py
  relations/
    schemas.py
    taxonomy.py
    store.py
    entity_resolution.py
  runs/
    recorder.py
    quality_gates.py
  cli/
    main.py
```

新的数据目录：

```text
data/
  raw/
    source_id/api_name/request_id/
  staging/
    dataset_id/partition=.../
  mart/
    domain/dataset_id/partition=.../
  features/
    domain/feature_id/as_of=.../
  evidence/
    records.jsonl
    sources/
  relations/
    records.jsonl
    snapshots/
  runs/
  reports/
```

## CLI 目标形态

旧 CLI 可以破坏式替换。

```bash
rdf sources list

rdf datasets list --domain ashare_core
rdf datasets meta ashare.daily --partition trade_date=YYYYMMDD
rdf datasets read ashare.daily --partition trade_date=YYYYMMDD

rdf maintain ashare-core --as-of YYYYMMDD --lookback-trading-days 60
rdf maintain status ashare-core --as-of YYYYMMDD --lookback-trading-days 60
rdf ingest run ashare_core_eod_daily --partition trade_date=YYYYMMDD
rdf ingest run ashare_intraday_snapshot --partition snapshot_at=ISO_TIME --param secids=0.000001
rdf ingest run global_reference_weekly --partition cik=0000320193
rdf ingest dataset ashare.daily --recipe tushare.daily.to_ashare_daily --partition trade_date=YYYYMMDD
rdf ingest dataset ashare.intraday_snapshot --recipe eastmoney.push2.quote_snapshot.to_ashare_intraday_snapshot --partition snapshot_at=ISO_TIME --param secids=0.000001

rdf features build ashare.daily_momentum --as-of YYYYMMDD --window 20
rdf features build ashare.market_strength --as-of YYYYMMDD --window 20
rdf features build ashare.industry_strength --as-of YYYYMMDD --window 20
rdf features build ashare.concept_strength --as-of YYYYMMDD --window 20
rdf features build ashare.limit_sentiment --as-of YYYYMMDD --window 20
rdf evidence ingest evidence.json
rdf relations ingest relations.json
```

命令名可保留 `ashare`，但内部概念不应继续被 A 股 daily 限制。若保留旧命令名，也只作为新 CLI 的品牌名，不做兼容适配。

## 关系图谱升级

跨市场后，需要扩展实体和关系。

新增实体类型：

- `filing_entity`
- `issuer`
- `exchange`
- `customer`
- `supplier`
- `peer_group`
- `country`
- `region`

新增关系：

- `listed_as`
- `has_filing_id`
- `customer_of`
- `supplier_to`
- `competes_with`
- `same_group_as`
- `maps_to_overseas_peer`
- `has_revenue_exposure`
- `has_geographic_exposure`

关系来源必须满足：

- URL、来源名、发布日期、查询时间；
- 或 evidence_id；
- 或 run raw_ref + 明确推理依据。

## Feature 规则

Feature 必须声明 allowed uses。

```yaml
id: ashare.daily_momentum
domain: ashare_core
allowed_uses:
  - candidate_generation
  - market_validation
forbidden_uses:
  - company_business_exposure
```

```yaml
id: global.overseas_peer_momentum
domain: global_reference
allowed_uses:
  - context
  - cross_market_validation
forbidden_uses:
  - ashare_primary_candidate_generation
```

A 股主候选池规则：

- 可使用 `ashare_core` mart；
- 可使用 `ashare` feature；
- 可使用 `ashare_enrichment` 作为辅助；
- 不可直接使用 `global_reference` 排名生成主候选；
- 不可用研报、新闻、热榜、概念成分证明业务暴露。

## 首批来源接入策略

### Tushare

定位：

- `canonical_eod`；
- A 股核心历史事实主源；
- 收盘后稳定更新；
- 不承担实时日线或盘中状态。

优先迁移：

- `trade_cal`
- `stock_basic`
- `daily`
- `daily_basic`
- `index_daily`
- `index_dailybasic`
- `sw_daily`
- `ci_daily`
- `dc_index`
- `limit_list_d`
- `top_list`
- `moneyflow_dc`
- 财务和主营构成按需维护。

### Eastmoney Direct

定位：

- `ashare_enrichment` 或 `intraday_observation`；
- 独有数据和实时观察；
- 必须串行限流，避免批量并发。

优先接入：

- 研报列表；
- 行业研报列表；
- 研报 PDF metadata；
- 个股新闻；
- 全球资讯；
- 盘中行情 snapshot；
- 盘中资金流。

### CNINFO

定位：

- `official_disclosure`；
- 公司事实强来源。

优先接入：

- orgId 动态映射；
- 公告检索；
- 公告详情 / PDF metadata。

### SEC EDGAR

定位：

- `cross_market_reference`；
- 海外公司强事实；
- 可用于客户、供应链、竞品、capex、收入区域等补证。

已接入：

- submissions；
- companyfacts；
- ticker to CIK mapping。

### Yahoo / Global Stock

定位：

- `cross_market_reference`；
- 行情、财务摘要、分析师、机构持仓、新闻。

延后接入：

- quoteSummary；
- chart；
- options。

## 重构阶段

### Phase 0: 决策冻结

产出：

- 本文档；
- 新架构术语表；
- 需要废弃的旧结构清单。

废弃：

- `DatasetSpec.source/source_api` 直接绑定；
- `daily.py` 硬编码任务作为唯一维护入口；
- 单层 `data/mart/DATASET/partition` 命名；
- 只支持 Tushare 的 `data build`。

### Phase 1: Core Schema

实现：

- `SourceSpec`
- `DatasetContract`
- `IngestionRecipe`
- `PipelineSpec`
- `UsagePolicy`
- `TemporalPolicy`
- `LineageRef`

验收：

- 可以注册同一 dataset 的多个 recipe；
- 可以声明 dataset 是否允许进入 A 股主候选池；
- 可以声明 source 的 finality、temporal mode 和 authority tier。

### Phase 2: Storage Kernel

实现：

- 新 raw store；
- 新 staging publisher；
- 新 mart publisher；
- 新 reader；
- 新 quality checker。

验收：

- raw / staging / mart 三层都有 lineage；
- mart meta 能追溯 source、recipe、request、quality 和时间语义。

### Phase 3: A 股 EOD 迁移

实现：

- Tushare source adapter；
- `ashare_core` contracts；
- `ashare_core_eod_daily` pipeline；
- A 股核心 features 迁移。

验收：

- 可以跑完整 A 股 EOD pipeline；
- `daily`, `daily_basic`, `index_daily`, `sw_daily`, `dc_index` 等可读；
- feature 构建只读新 mart。

### Phase 4: Evidence / Relations 升级

实现：

- 新 evidence source registry；
- 新 relation taxonomy；
- entity resolution；
- evidence quality gate。

验收：

- 研报、公告、SEC filing 都能进入 evidence；
- 公司、证券、产品、客户、供应、海外同业映射能进入 relations。

### Phase 5: A 股增强和跨市场参考

实现：

- Eastmoney direct；
- CNINFO direct；
- SEC EDGAR；
- Yahoo 基础能力。

验收：

- 东财研报作为 evidence seed；
- CNINFO 公告作为 official disclosure；
- SEC filing 作为 global reference evidence；
- 这些来源不会进入 A 股主候选池，除非 policy 显式允许。

### Phase 6: CLI / Docs / Skill 更新

实现：

- 新 CLI；
- 新 `SKILL.md`；
- 新 `references/data-map.md`；
- 新 `source-registry.md`；
- 新 reasoning policy。

验收：

- LLM 入口清楚区分 canonical EOD、intraday provisional、cross-market reference、evidence、relations；
- 输出纪律能被质量门检查。

## 不兼容清单

允许破坏：

- Python 包名；
- CLI 命令；
- dataset 名称；
- data 目录；
- tests；
- registry 文件结构；
- feature 分区路径；
- raw 文件格式；
- relation taxonomy。

必须保留的能力：

- A 股研究纪律；
- Tushare EOD 主源地位；
- mart / feature / evidence / relations / runs 的逻辑边界；
- 可审计来源；
- 缺口降级规则；
- 不输出交易执行指令。

## 第一轮实施建议

第一轮不要接太多来源。先做结构和两个试点。

1. 建新 package 骨架：`research_data_foundation`。
2. 实现核心 schema 和 registry。
3. 实现 raw / staging / mart 三层存储。
4. 迁移 Tushare `ashare.daily` 一个 dataset。
5. 迁移 `ashare_core_eod_daily` 的最小 pipeline。
6. 接入 `sec_edgar.submissions` 作为 cross-market reference 试点。
7. 接入 `eastmoney.reportapi.industry_reports` 作为 evidence seed 试点。
8. 基于试点调整 schema，再批量迁移其他 A 股 dataset。

## 当前落地状态与补回顺序

截至 2026-06-26，新内核已经恢复并验证：

- A 股核心 EOD：`ashare_core_eod_daily` 和 `maintain ashare-core`，Tushare 作为 canonical EOD 主源，`--lookback-trading-days` 按交易日计算。
- 核心 market datasets：交易日历、股票身份、个股日线、日线指标、复权因子、涨跌停价格、指数、核心指数权重、行业、概念、涨跌停名单、同花顺涨停池、资金、融资融券、龙虎榜、沪深股通十大成交股；`ashare.stock_basic` 已扩展公司全称、交易所、上市日期、实控人线索等身份字段。
- A 股核心 feature：`ashare.daily_momentum`、`ashare.market_strength`、`ashare.industry_strength`、`ashare.concept_strength`、`ashare.limit_sentiment`；行业补证优先级 feature：`industry.report_attention`。
- 第一批 global reference：SEC filing、SEC ticker-CIK mapping、SEC companyfacts，均只做跨市场 reference、evidence 或 context。
- 第一批 evidence / relations：东财行业研报索引、手工 evidence/relations ingest、从 evidence 派生 relations。
- 第一批 A 股 enrichment reference：`ashare.sw_industry_classification`、`ashare.industry_members` 和 `ashare.ci_industry_members`，分别从 Tushare `index_classify`、`index_member_all` / `ci_index_member` 维护申万行业层级、申万和中信行业成员快照；分类边不写入 curated relations。
- 第一批概念/板块成员分类事实：`ashare.concept_members`、`ashare.ths_index`、`ashare.ths_concept_members`，分别从 Tushare `dc_member`、`ths_index`、`ths_member` 维护东方财富和同花顺概念/题材体系，供候选扩展、分组读取和标签对照；不默认写入 curated relations，不能证明业务暴露。
- 第一批市场注意力事实：`ashare.ths_hot_rank`、`ashare.dc_hot_rank`，分别从 Tushare `ths_hot`、`dc_hot` 维护同花顺和东方财富热榜，用于候选扩展、关注度排序和题材热度交叉验证；排名、热度、概念标签和平台生成理由都不能证明业务暴露，不默认写入 curated relations。
- 第一批短线涨停/KPL 事实：`ashare.limit_step`、`ashare.limit_concept_rank`、`ashare.kpl_limit_list`、`ashare.kpl_concept_members`，用于连板梯队、涨停题材排行、开盘啦涨停池和题材成分候选；连板状态、题材标签和 KPL 描述都不能证明业务暴露，不默认写入 curated relations。
- 第一批多来源资金流事实：补宽 `ashare.moneyflow_dc`，新增 `ashare.moneyflow_tushare`、`ashare.moneyflow_ths`、`ashare.moneyflow_board_dc`、`ashare.moneyflow_industry_ths`、`ashare.moneyflow_concept_ths`、`ashare.moneyflow_hsgt`，用于市场验证、关注度排序和资金背景交叉验证；资金流入流出不能证明业务暴露，不默认写入 curated relations。
- 第一批陆股通标的资格事实：`ashare.northbound_eligible` 从 Tushare `stock_hsgt` 维护 `HK_SH` / `HK_SZ` 沪股通、深股通可买 A 股股票池，用于候选过滤、北向资金背景和跨市场验证；资格分类不能证明业务暴露，不默认写入 curated relations。
- 第一批筹码分布事实：`ashare.chip_distribution_perf` 和 `ashare.chip_distribution_detail` 从 Tushare `cyq_perf` / `cyq_chips` 维护单股单日筹码结构，用于获利盘、成本分布和市场结构验证；从旧版全市场 fanout 改为 on-demand，不证明业务暴露，不默认写入 curated relations。
- 第一批所有权结构和市场事件事实：`ashare.shareholder_count`、`ashare.top10_holders`、`ashare.top10_float_holders`、`ashare.share_pledge_stats`、`ashare.shareholder_trades`、`ashare.repurchase_events`、`ashare.earnings_forecast_events`、`ashare.block_trades` 分别从 Tushare `stk_holdernumber`、`top10_holders`、`top10_floatholders`、`pledge_stat`、`stk_holdertrade`、`repurchase`、`forecast`、`block_trade` 维护股东户数、十大股东/流通股东、股权质押统计、股东增减持、回购事件、业绩预告公告事件和大宗交易；用于所有权结构、公告补证入口、财务事件 triage 和市场结构验证，不证明业务暴露，不默认写入 curated relations。
- 第一批 A 股身份 reference：`ashare.stock_basic`、`ashare.name_changes` 和 `ashare.company_profile` 保留证券身份、曾用名和上市公司基础资料；需要沉淀身份或注册地区关系时由 Codex 或人工分析后写入 curated relations。
- 第一批公司事实补证入口：`ashare.main_business` 从 Tushare `fina_mainbz` 维护单公司或股票池批量的单报告期主营构成，可生成主营构成 evidence；产品/地区收入暴露关系必须分析后手工 ingest。
- 第一批官方公告入口：新增 CNINFO 远端按需发现、可选 `ashare.announcements` 全市场索引快照、按需 `ashare.announcement_text` PDF 正文解析；候选和标题只做 triage，披露主体、filing 关系和正文 claim 必须分析后手工 ingest。

补回优先级不按旧模块照搬，而按研究价值进入新分层。

### P1: 必须补回

| 能力 | 目标层 | 原因 | 设计边界 |
| --- | --- | --- | --- |
| 巨潮 / 交易所公告发现、PDF metadata 和正文取证 | source registry + on-demand mart + evidence | 公司事实、订单、客户、产能、问询回复必须有 S1 来源 | 已落 CNINFO 按需 discover、可选全市场索引、按需 PDF 正文抽取和正文片段候选；标题和整篇正文存在都不能自动替代具体 claim evidence，局部 discover 结果不能伪装成全量索引 |
| 主营构成 `fina_mainbz` / 财报摘要结构化 | mart + evidence seed | 判断业务暴露度和收入来源的基础 | 已落 `ashare.main_business`；支持按报告期和股票池限量批量维护，也支持单公司按需维护 |
| 证券-公司主体映射、简称/曾用名/统一社会信用代码等 alias | relations | 解决 LLM 查询时公司名、证券代码和披露主体不一致 | 已先用 `stock_basic`、`name_changes`、`company_profile` 和 CNINFO `org_id` 生成候选；后续补统一社会信用代码、公告主体、财报主体和官方披露交叉验证 |
| 申万 / 中信 / 东财 / 同花顺分类与概念成员快照 | mart + relations | 候选分组、行业扩散和关系检索需要稳定分类层 | 已落申万行业层级、申万行业成员、中信行业成员、东财概念/板块成分、同花顺概念/题材清单和成分；分类和概念只做线索，不得证明业务暴露 |
| 核心指数权重 | mart | 指数归因、权重暴露、基准成分和候选池分层需要稳定权重事实 | 已落 `ashare.index_weights`；按 `snapshot_date` 维护本地快照，`weight_trade_date` 表示实际最近权重日；指数成分和权重不证明业务暴露 |
| 涨跌停、涨停池、资金、龙虎榜、北向、融资融券、筹码、股东户数、十大股东、质押、股东增减持、回购、业绩预告事件、大宗交易和行业强弱 | mart + feature | 旧版短线情绪、杠杆资金、筹码结构、所有权结构、公告事件流和强弱验证值得保留 | 已落 `price_limits`、`limit_list_d`、`limit_list_ths`、`moneyflow_dc`、`top_list`、`northbound_eligible`、`hsgt_top10`、`margin_detail`、`chip_distribution_perf`、`chip_distribution_detail`、`shareholder_count`、`top10_holders`、`top10_float_holders`、`share_pledge_stats`、`shareholder_trades`、`repurchase_events`、`earnings_forecast_events`、`block_trades`、行业/概念行情 mart；已补 `market_strength`、`industry_strength`、`concept_strength`、`limit_sentiment`，只做筛查、排序、交叉验证 |

### P2: 应该补回

| 能力 | 目标层 | 原因 | 设计边界 |
| --- | --- | --- | --- |
| Yahoo chart/quoteSummary | global_reference + feature | 海外同业、跨市场估值和产业验证 | 不进入 A 股主候选池 |
| 东财 / 腾讯 / mootdx 盘中 fallback | ashare_intraday | 盘中异动观察和实时校验 | provisional overlay，不覆盖 Tushare EOD |
| 政策、协会、价格、招投标来源 | evidence | 产业链研究需要非公司披露证据 | 高频稳定后再升级为 mart |
| runs 质量门和研究复盘摘要 | runs / reports | 帮助审计一次研究是否越界 | 不回流为事实源 |

### 下一批实施建议

1. 完善 CNINFO 正文 claim evidence 沉淀：默认先 `announcements discover` 缩小范围，再 `announcements fetch-text` 获取选中 PDF，snippet candidate 只定位材料，关键 claim 仍需显式 evidence ingest。
2. 将报告期批量维护从限量验证推进到更大股票池：`ashare.main_business` 已支持股票池批量维护，下一步可按研究需要扩大 limit；保留 P/D 口径和官方报告回查状态。
3. 继续加强 alias relations：已从 `stock_basic` 派生 `security -> issuer`、简称 alias 和实控人候选，已从 `name_changes` 派生历史名称 alias，已从 `company_profile` 派生注册地区关系，也已从 CNINFO `org_id` 派生官方披露主体关系；下一步补统一社会信用代码、公告主体、财报主体和官方披露正文交叉验证。
4. 继续补 feature 但不越界：下一步可补资金扩散、北向/融资融券验证、龙虎榜和龙头验证；所有 feature 仍只做筛查、排序、交叉验证，不能证明公司业务暴露。
