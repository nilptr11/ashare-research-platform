# research_data_foundation

给 LLM / Codex 使用的 A 股研究数据底座。当前内核是 `research_data_foundation`，以 A 股 canonical EOD 为主域，同时提供跨市场参考和外部证据的按需获取入口。

本项目不做 Agent runtime、API 服务、自动化交易系统、固定投研工作流或外部数据湖。它只长期维护高复用、稳定、结构明确、时效语义清楚的本地事实层；网页、公告 PDF、招投标、政策、协会和外部 API 默认只登记获取方法，只有被研究结论使用的具体 claim 才进入 evidence，被分析确认的慢变量关系才进入 relations。

## 核心取舍

主要矛盾不是缺少更多流程，而是 LLM 需要一个可信、清晰、最小充分的数据底座：

- 哪些是结构化事实；
- 哪些只是筛查信号；
- 哪些是外部获取方法和已确认证据；
- 哪些是带来源或推理依据、置信度的慢变量关系；
- 缺数据时应该降级到什么程度。

因此项目只保留三层：

| 层 | 内容 | 作用 |
| --- | --- | --- |
| 数据事实层 | `data/raw`、`data/staging`、`data/mart`、`data/features`、`data/evidence`、`data/relations` | 提供来源留痕、统一事实、信号、已确认证据和 traceable 慢变量关系 |
| 研究纪律层 | `SKILL.md`、`references/data-map.md`、`references/source-registry.md`、`references/reasoning-policy.md`、`references/dataset-index.md`、`references/prompts/` | 告诉 LLM 怎么读数据、怎么降级、哪些结论不能越界 |
| 留痕层 | `data/runs`、`data/reports` | 记录一次研究用了什么材料和质量检查结果 |

## 系统架构

```text
用户问题 / 交易模式 / 研究假设
  -> LLM 临时归一化研究约束
     - 主要矛盾
     - 优先数据
     - 证据要求
     - 失效条件
  -> 读取最小必要数据
     - raw / staging：来源响应和来源口径清洗层
     - mart：统一结构化事实
     - feature：筛查、排序、交叉验证信号
     - evidence：已确认且可审计的外部 claim
     - relations：带来源或推理依据、置信度的慢变量关系
  -> 外部材料只在需要时按 source-registry discover / fetch
  -> 按 reasoning-policy 区分事实、推断、假设和缺口
  -> 对补到且用于结论的权威来源执行 evidence ingest
  -> 输出研究结论
  -> 对可复用产业链关系执行 rdf relations ingest
  -> 可选：用 runs + validated output 做留痕和质量检查
```

用户输入的交易模式用于帮助 LLM 决定“先看什么、什么能证明、什么只能作为线索”。

## 默认使用方式

```text
用户问题或假设
  -> 读 SKILL.md 和 references/data-map.md
  -> 检查数据日期、覆盖范围和质量
  -> 读取最小必要 mart / feature / evidence / relations
  -> 本地数据不足时按 references/source-registry.md 找获取方法
  -> 只 fetch 当次研究需要的外部材料
  -> 被用于结论的具体 claim 先验证并入库 evidence
  -> 输出事实、推断、假设、缺口和降级影响
  -> 需要复盘时 runs record 留痕
```

没有默认 playbook，也没有“按某个问题生成研究报告”的 CLI。特定研究模式可以沉淀在 `references/prompts/`，作为稳定研究约束，而不是让 LLM 每次临场归纳长文。

当前已沉淀：

- `references/prompts/industry-chain-trend.md`：产业主线扩散研究，适合强产业周期、结构性行情、产业链上中下游拆解、辐射行业和公司映射。

## 数据边界

- `mart`：统一结构化事实源。A 股核心维护组包括交易日历、股票身份、日线、日线指标、复权因子、涨跌停价格、指数、核心指数权重、行业、概念、涨跌停名单、同花顺涨停池、资金、融资融券、龙虎榜和北向成交；另有 `ashare.industry_members`、`ashare.ci_industry_members`、`ashare.concept_members`、`ashare.ths_index`、`ashare.ths_concept_members`、`ashare.ths_hot_rank`、`ashare.dc_hot_rank`、`ashare.limit_step`、`ashare.limit_concept_rank`、`ashare.kpl_limit_list`、`ashare.kpl_concept_members`、`ashare.main_business`、`ashare_financials` 域财务表、可选公告索引/正文、`ashare.intraday_snapshot`、`global.sec_filings`、`global.sec_ticker_cik`、`global.sec_companyfacts`、`industry.eastmoney_report_index`。
- `feature`：可复现筛查、排序和研究优先级信号。A 股核心 feature 包括 `ashare.daily_momentum`、`ashare.market_strength`、`ashare.industry_strength`、`ashare.concept_strength`、`ashare.limit_sentiment`；行业补证优先级 feature 是 `industry.report_attention`。
- `evidence`：项目内 mart 覆盖不了的产业价格、订单、产能、capex、政策、招投标等已确认外部 claim；高频稳定 HTTP JSON 来源可注册到 `data/evidence/sources/`，但仍按需 fetch，不默认全量抓取。
- `relations`：公司、产品、客户、产业链节点和关系等慢变量；Codex 分析后直接写入，每条记录必须带来源或推理依据、置信度和有效期。
- `data/runs` / `data/reports`：研究留痕和展示，不回流为事实源。

Feature 分数、概念成分、热榜、人气或涨停池不能单独证明公司业务暴露度。

## 常用命令

安装：

```bash
uv sync --group dev
```

列出注册来源、数据集和 feature：

```bash
uv run rdf inventory summary --as-of YYYYMMDD
uv run rdf inventory datasets --as-of YYYYMMDD --domain ashare_core
uv run rdf inventory datasets --use company_business_exposure
uv run rdf inventory features --as-of YYYYMMDD
uv run rdf inventory plan --as-of YYYYMMDD
uv run rdf inventory plan --as-of YYYYMMDD --coverage-status partial --no-features
uv run rdf sources list --as-of YYYYMMDD --limit-datasets 5
uv run rdf sources show tushare --as-of YYYYMMDD --use evidence --limit-datasets 10
uv run rdf datasets list --domain ashare_core
uv run rdf datasets list --domain ashare_financials
uv run rdf datasets search 资金流 --as-of YYYYMMDD --use market_validation
uv run rdf datasets search 公告 --as-of YYYYMMDD --use evidence
uv run rdf features list
```

`rdf inventory` 是 LLM 读取本地数据前的可发现性入口：它汇总 mart 最新分区、目标日期分区、行数、质量、来源 recipe、feature 分区、evidence 和 relations 记录数。它只报告本地状态，不触发抓取，也不改变数据。
`rdf inventory`、`rdf sources list/show` 和 `rdf datasets search` 都会返回 `coverage`：`full` 表示目标分区完整匹配，`partial` 表示只覆盖多键分区里的部分子分区，`latest_before` 表示按 as-of policy 读取目标日前最近快照，`latest` 表示未指定 as-of 时只取本地最新。只有 `full` 可当作目标分区完整覆盖；其他状态必须按局部样本或最近快照使用。
`rdf sources list/show` 是来源可发现性入口：它把 SourceSpec、recipes、pipelines、dataset contract、as-of 本地状态和用途边界合并为 source map，帮助 Codex 判断该找哪个来源、能读哪些本地分区、哪些结论不能越界。
`rdf datasets search` 是按研究意图找 mart dataset 的入口：它搜索 dataset contract、用途、字段、来源 recipe 和本地 inventory，返回匹配分数、用途边界、coverage、当前可用分区、建议读取命令和分区查看命令。它只做发现，不抓取、不推断公司暴露。
`rdf inventory features --as-of` 会列出 feature 的推荐窗口、已生成分区、输入 mart 可用分区数和是否可构建；窗口按本地已发布分区/交易日理解，不是自然日。
`rdf inventory plan` 是缺口转补数动作的入口：它根据 registry、本地状态和 `coverage` 输出推荐 dry-run、执行命令、前置条件和用途边界；默认纳入 `missing/degraded` 状态缺口以及 `none/partial` 目标覆盖缺口，因此 `ready + partial` 的多键分区也会进入恢复计划。它仍然只生成计划，不抓取、不写入。
`rdf ingest ... --dry-run` 是执行抓取前的结构化计划入口：它只解析 source、recipe、dataset、partition、请求参数、时间语义、用途边界和将写入的 raw/staging/mart 层，不请求外部来源，也不创建数据文件。
`rdf datasets partitions` 和 `rdf datasets latest` 只读取本地已发布 mart；latest 表示本地最新分区，不保证等于市场最新交易日。
`rdf datasets read`、`latest`、`scan` 和 `read-window` 都返回结构化 JSON：顶层包含 dataset、分区、行数、质量、temporal、usage、boundary、lineage 或分区列表，`records` 才是实际数据行。LLM 引用数据时应保留这些上下文，不要只复制 records。
`rdf datasets scan` 按部分分区过滤读取多键分区 dataset，例如只给 `publish_date=YYYYMMDD` 读取当日已解析公告正文，或只给 `period=YYYYMMDD` 读取该报告期已维护财务样本。它仍只读本地 mart，不抓取、不推断。
`period` 分区的 filing 数据会把 `--as-of YYYYMMDD` 映射为最近已完整到期的报告期，例如 20260624 映射为 20260331；主营构成、财务表和股东结构都按这个报告期口径判断本地覆盖。
`rdf datasets read-window` 按本地已发布分区向前取 N 个分区；对 `ashare.daily` 这类交易日分区，它表示近 N 个已入库交易日，不是自然日。

A 股收盘后核心数据以 Tushare 为 canonical EOD 主源。它适合维护历史和收盘后事实，不承担实时日线或盘中状态。
`--lookback-trading-days` 表示向前维护的交易日数量，不是自然日数量。
mart 表按 dataset contract 的分区和 primary key 规范化；ingestion 会过滤到请求分区，storage 会拒绝表内分区列与路径分区不一致的数据。若源返回同一主键的修订行，mart 保留 `update_flag` 更高或来源顺序更新的行，raw 层保留原始返回用于审计。

维护和读取 mart：

```bash
uv run rdf maintain ashare-core --as-of YYYYMMDD --lookback-trading-days 60 --refresh
uv run rdf maintain status ashare-core --as-of YYYYMMDD --lookback-trading-days 60
uv run rdf ingest dataset ashare.daily --recipe tushare.daily.to_ashare_daily --partition trade_date=YYYYMMDD --refresh
uv run rdf ingest recipe tushare.daily.to_ashare_daily --partition trade_date=YYYYMMDD --dry-run
uv run rdf ingest run ashare_core_eod_daily --partition trade_date=YYYYMMDD --refresh
uv run rdf ingest pipeline ashare_membership_weekly --partition snapshot_date=YYYYMMDD --refresh
uv run rdf ingest pipeline ashare_identity_weekly --partition snapshot_date=YYYYMMDD --refresh
uv run rdf ingest pipeline ashare_market_attention_daily --partition trade_date=YYYYMMDD --refresh
uv run rdf ingest pipeline ashare_short_term_sentiment_daily --partition trade_date=YYYYMMDD --refresh
uv run rdf ingest pipeline ashare_moneyflow_daily --partition trade_date=YYYYMMDD --refresh
uv run rdf ingest pipeline ashare_chips_on_demand --partition trade_date=YYYYMMDD --partition security_id=000001.SZ --refresh
uv run rdf ingest pipeline ashare_ownership_periodic --partition period=YYYYMMDD --refresh
uv run rdf ingest pipeline ashare_share_pledge_weekly --partition end_date=YYYYMMDD --refresh
uv run rdf ingest pipeline ashare_corporate_action_events_daily --partition ann_date=YYYYMMDD --refresh
uv run rdf ingest pipeline ashare_financial_event_daily --partition ann_date=YYYYMMDD --refresh
uv run rdf ingest pipeline ashare_block_trades_daily --partition trade_date=YYYYMMDD --refresh
uv run rdf maintain ashare-concept-members --snapshot-date YYYYMMDD --limit 20 --refresh
uv run rdf maintain ashare-ths-concepts --snapshot-date YYYYMMDD --limit 20 --refresh
uv run rdf maintain ashare-index-weights --snapshot-date YYYYMMDD --refresh
uv run rdf ingest pipeline global_reference_weekly --partition cik=0000320193 --dry-run
uv run rdf ingest pipeline global_reference_universe_weekly --partition snapshot_date=YYYYMMDD --dry-run
uv run rdf ingest pipeline global_reference_companyfacts_on_demand --partition cik=0000320193 --dry-run
uv run rdf maintain ashare-main-business --period YYYYMMDD --stock-snapshot-date YYYYMMDD --limit 20 --refresh
uv run rdf maintain ashare-main-business --period YYYYMMDD --security-id 000001.SZ --segment-types P,D --refresh
uv run rdf maintain ashare-financials --as-of YYYYMMDD --stock-snapshot-date YYYYMMDD --dataset-id ashare.income_statement --limit 20 --refresh
uv run rdf maintain ashare-financials --period YYYYMMDD --security-id 000001.SZ --dataset-id ashare.income_statement --refresh
uv run rdf maintain industry-report-index --query-date YYYYMMDD --lookback-days 30 --max-pages 1 --refresh
uv run rdf datasets meta ashare.daily --partition trade_date=YYYYMMDD
uv run rdf datasets search 日线 --as-of YYYYMMDD
uv run rdf datasets search 资金流 --as-of YYYYMMDD --use market_validation
uv run rdf datasets read ashare.daily --partition trade_date=YYYYMMDD --limit 20
uv run rdf datasets read ashare.price_limits --partition trade_date=YYYYMMDD --columns security_id up_limit down_limit --limit 20
uv run rdf datasets read ashare.limit_list_ths --partition trade_date=YYYYMMDD --columns security_id name price pct_chg board_tag limit_reason open_num limit_order limit_amount --limit 20
uv run rdf datasets read ashare.limit_step --partition trade_date=YYYYMMDD --columns security_id security_name limit_up_days --limit 20
uv run rdf datasets read ashare.limit_concept_rank --partition trade_date=YYYYMMDD --columns concept_id concept_name rank limit_up_count consecutive_limit_count up_stat --limit 20
uv run rdf datasets read ashare.kpl_limit_list --partition trade_date=YYYYMMDD --columns security_id security_name board_status theme_tags limit_reason limit_order turnover_rate --limit 20
uv run rdf datasets read ashare.kpl_concept_members --partition trade_date=YYYYMMDD --columns concept_id concept_name security_id security_name hot_num vendor_exposure_desc --limit 20
uv run rdf datasets read ashare.moneyflow_dc --partition trade_date=YYYYMMDD --columns security_id security_name net_amount net_amount_rate buy_elg_amount buy_lg_amount --limit 20
uv run rdf datasets read ashare.moneyflow_tushare --partition trade_date=YYYYMMDD --columns security_id net_mf_amount buy_lg_amount sell_lg_amount buy_elg_amount sell_elg_amount --limit 20
uv run rdf datasets read ashare.moneyflow_ths --partition trade_date=YYYYMMDD --columns security_id security_name net_amount net_d5_amount buy_lg_amount buy_lg_amount_rate --limit 20
uv run rdf datasets read ashare.moneyflow_board_dc --partition trade_date=YYYYMMDD --columns board_type subject_id subject_name rank net_amount net_amount_rate --limit 20
uv run rdf datasets read ashare.moneyflow_industry_ths --partition trade_date=YYYYMMDD --columns industry_id industry_name lead_stock net_amount company_num pct_chg --limit 20
uv run rdf datasets read ashare.moneyflow_concept_ths --partition trade_date=YYYYMMDD --columns concept_id concept_name lead_stock net_amount company_num pct_chg --limit 20
uv run rdf datasets read ashare.moneyflow_hsgt --partition trade_date=YYYYMMDD --columns north_money south_money hgt sgt --limit 20
uv run rdf datasets read ashare.index_weights --partition snapshot_date=YYYYMMDD --columns index_id security_id weight_trade_date weight --limit 20
uv run rdf datasets read ashare.northbound_eligible --partition trade_date=YYYYMMDD --columns security_id security_name connect_type connect_type_name --limit 20
uv run rdf datasets read ashare.chip_distribution_perf --partition trade_date=YYYYMMDD --partition security_id=000001.SZ --columns security_id winner_rate cost_50pct cost_85pct cost_95pct weight_avg --limit 20
uv run rdf datasets read ashare.chip_distribution_detail --partition trade_date=YYYYMMDD --partition security_id=000001.SZ --columns security_id price percent --limit 20
uv run rdf datasets read ashare.shareholder_count --partition period=YYYYMMDD --columns security_id ann_date holder_num --limit 20
uv run rdf datasets read ashare.top10_holders --partition period=YYYYMMDD --columns security_id ann_date holder_name holder_type hold_amount hold_ratio hold_change --limit 20
uv run rdf datasets read ashare.top10_float_holders --partition period=YYYYMMDD --columns security_id ann_date holder_name holder_type hold_amount hold_float_ratio hold_change --limit 20
uv run rdf datasets read ashare.share_pledge_stats --partition end_date=YYYYMMDD --columns security_id pledge_count unrest_pledge rest_pledge total_share pledge_ratio --limit 20
uv run rdf datasets read ashare.shareholder_trades --partition ann_date=YYYYMMDD --columns security_id holder_name holder_type in_de change_vol change_ratio after_share after_ratio avg_price --limit 20
uv run rdf datasets read ashare.repurchase_events --partition ann_date=YYYYMMDD --columns security_id end_date process_status volume amount high_limit low_limit --limit 20
uv run rdf datasets read ashare.earnings_forecast_events --partition ann_date=YYYYMMDD --columns security_id period forecast_type p_change_min p_change_max net_profit_min net_profit_max change_reason --limit 20
uv run rdf datasets read ashare.block_trades --partition trade_date=YYYYMMDD --columns security_id price volume amount buyer seller --limit 20
uv run rdf datasets partitions ashare.daily --limit 10
uv run rdf datasets latest ashare.daily --columns security_id trade_date close pct_chg --limit 100
uv run rdf datasets read-window ashare.daily --as-of YYYYMMDD --count 20 --columns security_id trade_date close pct_chg --limit 100
uv run rdf datasets read ashare.stock_basic --partition snapshot_date=YYYYMMDD --columns security_id symbol name fullname exchange list_date act_name act_ent_type --limit 20
uv run rdf datasets read ashare.company_profile --partition snapshot_date=YYYYMMDD --columns security_id exchange province city office employees main_business --limit 20
uv run rdf datasets read ashare.name_changes --partition snapshot_date=YYYYMMDD --columns security_id name start_date end_date change_reason --limit 20
uv run rdf datasets read ashare.sw_industry_classification --partition snapshot_date=YYYYMMDD --columns source_system index_id industry_name level industry_code parent_code --limit 20
uv run rdf datasets read ashare.industry_members --partition snapshot_date=YYYYMMDD --limit 20
uv run rdf datasets read ashare.ci_industry_members --partition snapshot_date=YYYYMMDD --limit 20
uv run rdf datasets read ashare.concept_members --partition snapshot_date=YYYYMMDD --partition concept_id=CONCEPT_ID --limit 20
uv run rdf datasets read ashare.ths_index --partition snapshot_date=YYYYMMDD --columns concept_id name index_type source_member_count --limit 20
uv run rdf datasets read ashare.ths_concept_members --partition snapshot_date=YYYYMMDD --partition concept_id=CONCEPT_ID --limit 20
uv run rdf datasets read ashare.ths_hot_rank --partition trade_date=YYYYMMDD --columns rank_type subject_id subject_name rank heat concept_tags_json --limit 20
uv run rdf datasets read ashare.dc_hot_rank --partition trade_date=YYYYMMDD --columns rank_type security_id security_name rank pct_chg price --limit 20
uv run rdf datasets read ashare.hsgt_top10 --partition trade_date=YYYYMMDD --columns security_id name market_type rank amount net_amount buy sell --limit 20
uv run rdf datasets read ashare.margin_detail --partition trade_date=YYYYMMDD --columns security_id name rzye rqye rzmre rzche rzrqye --limit 20
uv run rdf datasets read ashare.main_business --partition period=YYYYMMDD --partition security_id=000001.SZ --partition segment_type=P --limit 20
uv run rdf datasets scan ashare.main_business --partition period=YYYYMMDD --columns security_id segment_type item_name sales --limit 50
uv run rdf datasets read ashare.income_statement --partition period=YYYYMMDD --partition security_id=000001.SZ --limit 20
uv run rdf datasets scan ashare.income_statement --partition period=YYYYMMDD --columns security_id period total_revenue n_income --limit 50
uv run rdf announcements discover --start-date YYYYMMDD --end-date YYYYMMDD --security-id 000001.SZ --keyword 订单 --limit 20
uv run rdf announcements discover --start-date YYYYMMDD --keyword 减持 --category 持股变动 --dry-run
uv run rdf announcements fetch-text --publish-date YYYYMMDD --announcement-id ANNOUNCEMENT_ID --source-url SOURCE_URL --security-id 000001.SZ
uv run rdf datasets read ashare.announcements --partition publish_date=YYYYMMDD --limit 20
uv run rdf announcements search --as-of YYYYMMDD --lookback-days 7 --category 持股变动 --keyword 减持 --limit 20
uv run rdf datasets read ashare.announcement_text --partition publish_date=YYYYMMDD --partition announcement_id=ANNOUNCEMENT_ID --columns announcement_id security_id title text_length parse_status --limit 20
uv run rdf datasets scan ashare.announcement_text --partition publish_date=YYYYMMDD --columns announcement_id security_id title text_length parse_status --limit 50
uv run rdf datasets read industry.eastmoney_report_index --partition query_date=YYYYMMDD --columns query_date report_id title published_at source_name industry_name source_url --limit 20
uv run rdf datasets read global.sec_ticker_cik --partition snapshot_date=YYYYMMDD --limit 20
uv run rdf datasets read global.sec_companyfacts --partition cik=0000320193 --columns cik entity_name concept unit end_date filed_date form value --limit 20
```

CNINFO 公告默认走按需路径：`announcements discover` 远端查询候选但不写本地 mart，`announcements fetch-text` 只下载被选中的 PDF 正文并写入 `ashare.announcement_text`。`cninfo.announcements.to_ashare_announcements` 和 `maintain ashare-announcement-text --limit ...` 只作为可选批处理能力，不是研究前置；不要把按关键词查到的局部结果写成某个 `publish_date` 的全量公告索引。

盘中数据只作为 provisional overlay，不覆盖 `ashare.daily`：

```bash
uv run rdf ingest dataset ashare.intraday_snapshot --recipe eastmoney.push2.quote_snapshot.to_ashare_intraday_snapshot --partition snapshot_at=ISO_TIME --param secids=0.000001
uv run rdf datasets meta ashare.intraday_snapshot --partition snapshot_at=ISO_TIME
```

构建和读取 feature：

```bash
uv run rdf features build ashare.daily_momentum --as-of YYYYMMDD --window 20 --refresh
uv run rdf features build ashare.market_strength --as-of YYYYMMDD --window 20 --refresh
uv run rdf features build ashare.industry_strength --as-of YYYYMMDD --window 20 --refresh
uv run rdf features build ashare.concept_strength --as-of YYYYMMDD --window 20 --refresh
uv run rdf features build ashare.limit_sentiment --as-of YYYYMMDD --window 20 --refresh
uv run rdf features meta ashare.daily_momentum --as-of YYYYMMDD --window 20
uv run rdf features read ashare.daily_momentum --as-of YYYYMMDD --window 20 --limit 30
uv run rdf features read ashare.market_strength --as-of YYYYMMDD --window 20 --limit 30
uv run rdf features read ashare.industry_strength --as-of YYYYMMDD --window 20 --limit 30
uv run rdf features read ashare.concept_strength --as-of YYYYMMDD --window 20 --limit 30
uv run rdf features read ashare.limit_sentiment --as-of YYYYMMDD --window 20 --limit 30
```

`maintain ashare-core` 默认会按 5/20/60 个已入库交易日构建 A 股核心 feature；也可以按上面命令单独刷新。先用 `rdf inventory features --as-of YYYYMMDD` 查看每个窗口是否 buildable，再构建缺失窗口。Feature 只能做候选线索、市场强弱和交叉验证，不能证明公司业务暴露。
`rdf features read` 返回结构化 JSON：顶层包含 feature spec、输入 mart、质量、usage、boundary 和 `records`。引用 feature 结果时必须同时保留输入和边界，不能把 feature 排名或分数当成事实证据。

补证、入库 evidence，并沉淀 curated relations：

```bash
uv run rdf evidence validate evidence.json
uv run rdf evidence ingest evidence.json
uv run rdf evidence sources list
uv run rdf evidence sources add evidence-source.json
uv run rdf evidence sources fetch SOURCE_ID --param key=value
uv run rdf evidence from-dataset global.sec_filings --partition cik=0000320193
uv run rdf evidence from-dataset global.sec_ticker_cik --partition snapshot_date=YYYYMMDD
uv run rdf evidence from-dataset global.sec_companyfacts --partition cik=0000320193 --limit 50
uv run rdf evidence from-dataset ashare.shareholder_trades --partition ann_date=YYYYMMDD --limit 50
uv run rdf evidence from-dataset ashare.repurchase_events --partition ann_date=YYYYMMDD --limit 50
uv run rdf evidence from-dataset ashare.earnings_forecast_events --partition ann_date=YYYYMMDD --limit 50
uv run rdf evidence from-announcement-text --partition publish_date=YYYYMMDD --partition announcement_id=ANNOUNCEMENT_ID --query 关键词 --limit 20
uv run rdf evidence profile --topic commodity_price --limit 20
uv run rdf evidence source-candidates --min-records 3 --limit 20
uv run rdf evidence list --topic sec_filing --limit 20
uv run rdf evidence export evidence-slice.jsonl --company 000001.SZ --period YYYYMMDD
uv run rdf relations taxonomy
uv run rdf relations profile --limit 20
uv run rdf relations neighborhood --entity ENTITY --limit 50
uv run rdf relations ingest relations.json
uv run rdf relations list --predicate has_filing_id --limit 20
uv run rdf relations snapshot --subject 000001.SZ --output relation-snapshot.json
```

`rdf relations ingest` 是 Codex 或人工分析后沉淀产业链节点、产品暴露、上下游、客户或供应关系的唯一默认落库入口。它不是状态队列；可信度由来源或 evidence_id、置信度、有效期和后续复核来控制。
新架构不提供从 mart 或 evidence 自动派生 relations 的默认命令；需要沉淀关系时，由 Codex 或人工把可审计慢变量整理成 `relations.json` 后执行 `rdf relations ingest`。不要把 `ashare.industry_members`、`ashare.ci_industry_members` 这种高基数分类边批量写进 curated relations。
`rdf evidence sources` 用于沉淀可复用 HTTP JSON 补证入口，拉取结果只进入 evidence；不用于替代 mart 数据集、Tushare EOD 或官方公告正文校验。
`rdf evidence profile` 和 `rdf evidence source-candidates` 用于查看 evidence 覆盖与可复用来源候选；它们不改变 evidence 置信度，也不自动证明公司业务暴露。`source-candidates` 只提示未绑定正式 dataset 的外部数值证据。
`rdf evidence from-announcement-text` 只从 `ashare.announcement_text` 的 CNINFO PDF 正文抽取结果中定位关键词上下文，输出 snippet candidates 且 `ingested=false`；它帮助 Codex/LLM 摘录具体 claim，但不会自动写入 evidence，也不会把片段直接升级为业务结论。
`ashare.sw_industry_classification` 是申万行业层级字典，`ashare.industry_members`、`ashare.ci_industry_members` 分别是申万和中信行业分类事实，适合在 mart 中读取、分组和交叉验证，不是产业链关系库内容。
`ashare.concept_members` 是东方财富概念/板块成分分类事实，适合做候选池扩展、板块分组和市场线索追踪；它不证明公司业务暴露度，不默认写入 curated relations，重点候选仍需公告、财报、IR、合格 evidence 或 traceable relations 补证。
`ashare.ths_index` 和 `ashare.ths_concept_members` 是同花顺概念/行业/题材体系的清单和成分分类事实，适合与东财概念、同花顺涨停池题材标签交叉对照；它们不证明公司业务正宗、产品供给、客户订单或收入暴露，不默认写入 curated relations。
`ashare.ths_hot_rank` 和 `ashare.dc_hot_rank` 是同花顺/东方财富热榜注意力事实，适合候选扩展、市场关注度排序和题材热度交叉验证；排名、热度、概念标签和 `vendor_rank_reason` 都不能作为公司业务暴露或公告事实证据，不默认写入 curated relations。
`ashare.limit_step`、`ashare.limit_concept_rank`、`ashare.kpl_limit_list` 和 `ashare.kpl_concept_members` 是短线涨停/KPL 市场线索，可用于连板梯队、涨停题材和候选池验证；题材标签、KPL 描述和连板状态都不能作为公司业务暴露证据，不默认写入 curated relations。
`ashare.company_profile` 是上市公司基础资料 reference fact，可用于公司画像、注册地归一化、联系信息和主营文本初筛；`main_business`、`business_scope` 只能做 evidence triage，不能替代年报、公告或 IR 对业务暴露的证明。
`ashare.name_changes` 是历史股票名称 alias seed，可帮助 Codex/LLM 用曾用名、旧简称定位证券；它只证明名称历史，不证明公司业务、产品、客户或订单。
`ashare.stock_basic` 是 A 股证券身份快照，可用于代码、简称、公司全称、交易所、上市状态和实控人线索定位，并可预览 security/issuer/alias/controller 候选关系；它不能证明公司产品、客户、订单或业务暴露，实控人线索也需要官方披露交叉验证。
`ashare.price_limits` 是每日涨跌停价格边界 EOD core fact，可用于校验涨跌停状态、价格约束和日线质量；它不证明公司基本面、产品、客户、订单或业务暴露。
`ashare.limit_list_ths` 是同花顺涨停池 EOD enrichment fact，可用于短线情绪、连板高度、封单金额、开板次数和候选验证；`limit_reason` 是市场题材标签，不证明公司业务正宗、产品供给、客户订单或收入暴露。
`ashare.moneyflow_dc`、`ashare.moneyflow_tushare`、`ashare.moneyflow_ths`、`ashare.moneyflow_board_dc`、`ashare.moneyflow_industry_ths`、`ashare.moneyflow_concept_ths` 和 `ashare.moneyflow_hsgt` 是多来源资金流事实，可用于市场验证、关注度排序和板块/概念资金背景；资金流入流出不证明公司业务、产品、客户、订单或收入暴露，不默认写入 curated relations。
`ashare.index_weights` 是核心指数成分权重 snapshot fact，`snapshot_date` 表示本地快照日，`weight_trade_date` 表示该指数实际最近权重日；它适合指数归因、权重暴露和候选分层，不证明公司业务暴露。
`ashare.northbound_eligible` 是陆股通 A 股标的资格 reference fact，可用于北向可买股票池分组、候选过滤和跨市场资金背景；它不证明公司基本面、产品、客户、订单或业务暴露，不默认写入 curated relations。
`ashare.hsgt_top10` 是沪深股通十大成交股 EOD enrichment fact，可用于观察北向成交关注和市场验证；它不证明公司基本面、产品、客户、订单或业务暴露。
`ashare.margin_detail` 是融资融券明细 EOD enrichment fact，可用于观察杠杆资金、融资余额和融券状态的市场验证；它不证明公司基本面、产品、客户、订单或业务暴露。
`ashare.chip_distribution_perf` 和 `ashare.chip_distribution_detail` 是单股按需筹码分布事实，用于获利盘、成本分布和市场结构验证；不要默认全市场拉取，不证明公司基本面、产品、客户、订单或业务暴露，不默认写入 curated relations。
`ashare.shareholder_count`、`ashare.top10_holders`、`ashare.top10_float_holders` 和 `ashare.share_pledge_stats` 是所有权结构和质押统计事实，可用于股东户数变化、持有人集中度、质押风险和市场结构线索；`ashare.shareholder_trades` 与 `ashare.repurchase_events` 是股东增减持和回购事件结构化事实，`ashare.earnings_forecast_events` 是按公告日扫描的业绩预告事件流，可用 `rdf evidence from-dataset` 生成 `evidence_triage` 记录并作为公告补证入口；`ashare.block_trades` 是大宗交易事实，可做市场结构验证。它们都不能证明公司产品、客户、订单或业务暴露，不默认写入 curated relations；高置信公司动作和财务预告结论需回查官方公告正文。
`ashare.main_business` 可按报告期和股票池批量维护，也可单公司按需维护；它可形成主营构成 evidence，但高置信产品暴露关系仍要由 Codex 在回查官方公告或年报正文后人工/分析沉淀。`ashare.announcements` 是可选维护的 CNINFO 全市场索引，只证明官方披露入口，可预览 `security -> cninfo:org` 和 `org -> filing` 身份关系；它不是研究默认前置，标题不能替代正文事实。
`rdf announcements discover` 直接按公司、关键词、类别和时间窗口查询 CNINFO 远端，只返回候选且不写本地 mart；`rdf announcements search` 只在本地 `ashare.announcements` 中检索已有索引。两者结果都只做公告补证入口，不证明公告正文 claim。
`global.sec_ticker_cik` 和 `global.sec_companyfacts` 来自 SEC EDGAR S1 来源，只用于跨市场同业、海外客户/供应链背景、身份映射、财务事实和 evidence/context；不得进入 A 股主候选池或覆盖 A 股本地事实。
`ashare.announcement_text` 默认按需解析选中的 CNINFO PDF；raw 层保存 PDF 附件，mart 层保存正文抽取结果。它可作为具体 claim 摘录和校验材料；不要把整篇正文存在本身等同于某个具体业务 claim 已被证明。关键结论的默认路径是 `announcements fetch-text` 获取正文，再用 `rdf evidence from-announcement-text` 定位原文片段，最后由 Codex/人工确认 claim 后通过 `rdf evidence ingest` 沉淀。
`industry.eastmoney_report_index` 通过 `maintain industry-report-index` 维护，默认以 `query_date` 作为 as-of 上限并向前取自然日窗口，避免把 query_date 之后的研报带入当日研究。它是研报索引和 evidence seed，只能做补证优先级、行业关注度和外部观点线索；不能证明公司产品、客户、订单、收入暴露或产业链位置。
`ashare_financials` 域可按报告期和股票池批量维护，也可单公司按需维护；它可派生财务 evidence，用于收入、利润、资产负债、现金流、财务指标、快报、分红、审计意见、披露日期和业绩预告等财务事实；关键结论仍要回查官方披露正文。

记录研究留痕：

```bash
uv run rdf runs record --question "..." --as-of YYYYMMDD --mart-ref ashare.daily:trade_date=YYYYMMDD --feature-ref ashare.daily_momentum:as_of=YYYYMMDD,window=20 --validated-output model_output.validated.json
uv run rdf runs show RUN_ID
```

研究留痕只作为 `data/runs/` 下的记录材料，不回流为事实源。`rdf runs record` 会检查 mart/feature 分区、evidence_id、relation_id 是否存在，并对 validated output 的公司暴露证据、外部来源审计字段和高优先候选证据强度执行质量门；新内核不会把 runs/reports 当作 evidence 或 relations 的替代来源。

## 非目标

- 不输出买入、卖出、加仓、减仓、仓位、止盈止损或下单指令。
- 不把用户问题编译成固定 workflow。
- 不让外部搜索覆盖本地已有行情、公告、财务和资金事实。
- 不把 run、report、prompt 或模型记忆当事实源。
- 不把候选池状态解释为交易动作。

## 项目入口

- [SKILL.md](SKILL.md)：LLM / Codex 默认入口。
- [references/data-map.md](references/data-map.md)：本地数据有什么、能支持什么、不能支持什么。
- [references/dataset-index.md](references/dataset-index.md)：常用 dataset / feature 快速定位。
- [references/source-registry.md](references/source-registry.md)：本地数据不足时的权威补证来源。
- [references/source-expansion-notes.md](references/source-expansion-notes.md)：外部数据工具仓库可吸收端点和边界评估。
- [references/reasoning-policy.md](references/reasoning-policy.md)：事实、推断、假设和缺口的边界。
- [references/prompts/industry-chain-trend.md](references/prompts/industry-chain-trend.md)：产业主线扩散研究提示词。
