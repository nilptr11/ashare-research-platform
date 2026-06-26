---
name: ashare-research-data-foundation
description: Use when an LLM agent researches A-share market themes, stock candidates, industry-chain decomposition, company exposure, evidence gaps, or market structure with this repository. This skill provides a prepared data foundation and research discipline, not an automated workflow or trading system.
---

# A 股研究数据底座

本项目给 LLM / Codex 提供 A 股研究数据底座。用户提出方向或假设；LLM 读取本地已准备数据、识别缺口、必要时按来源注册主动获取外部材料，并输出可追溯研究结论。

项目不做 Agent runtime、API 服务、自动化交易系统、固定投研 workflow、外部数据湖或交易执行。外部网页、公告 PDF、招投标、政策、协会和 API 默认只登记获取方法；只有研究结论用到的具体 claim 才进入 evidence，分析确认的慢变量关系才进入 relations。

## 使用顺序

1. 把用户问题当作研究假设，不要直接当结论。
2. 读 `references/data-map.md`，确认本地已有数据、适用边界和盲区。
3. 检查数据日期、覆盖范围和质量；优先使用最小必要数据。
4. 本地数据足够时，直接读取相关 mart、feature、evidence、relations。
5. 本地数据不足时，读 `references/source-registry.md`，确认权威或可解释来源的获取方法；只 fetch 当次研究需要的外部材料。
6. 用 `references/reasoning-policy.md` 区分事实、推断、假设和缺口。
7. 需要复盘时，用 run 留痕记录问题、数据引用、证据、relations 快照和质量检查。

## 交易模式输入

用户可能用自然语言描述任意交易模式，例如价投、中短线、产业主线、龙头、事件驱动或混合模式。不要把交易模式当固定流程，也不要临场复述交易动作。

若用户指定已沉淀提示词，先读对应文件；否则只在当前研究中临时归一化为：

- 主要矛盾；
- 优先读取的数据；
- 哪些信号只能做线索；
- 哪些证据才能支撑结论；
- 失效条件和输出边界。

归一化结果用于指导当次研究的数据选择、证据判断和输出边界。

当前已沉淀的研究提示词：

- `references/prompts/industry-chain-trend.md`：产业主线扩散研究，用于强产业周期、结构性行情、产业链上中下游拆解、辐射行业和公司映射。

## 补证和产业链梳理

当本地 evidence 或 relations 不足以支撑产业链、公司暴露、客户、订单、产能、收入构成等结论时，继续按 `references/source-registry.md` 补权威来源。不要为了“以后可能会用”批量抓取外部网页或 API；先拿到获取方式和查询边界，再按研究问题缩小范围。

外部补证不能只写“来源：年报/公告/网页”。每条用于支撑结论的外部来源至少写清：

- 来源类型和来源名；
- URL 或接口；
- 发布日期；
- 抓取或查询时间；
- 支撑的具体 claim；
- 证据强弱和不确定性。

补到可审计来源且用于支撑关键结论时，Codex 应先用 `rdf evidence validate` 检查，再用 `rdf evidence ingest` 入库，并在结论中引用返回的 `evidence_id`。

产业链研究要先梳理上游、中游、下游、设备、材料、零部件、应用等节点，再把公司映射到节点。公司映射应能落到“节点 -> 公司 -> 证据 -> 强弱 -> 缺口”。凡是当次分析形成的可复用产业链节点、产品暴露、上下游、客户或供应关系，Codex 应直接用 `rdf relations ingest` 落到 relations，并在结论中引用 relation `id`。当次结论必须同时给出来源、日期和证据强弱。

候选池必须先从本地 feature / mart 的市场线索生成，再补公司证据。手写的已知公司名单只能作为先验观察单独标注，不能混进主筛选排序。没有可审计公司证据的公司，不应进入重点研究，只能列为市场线索或证据待补。

## 数据层级

| 层级 | 路径 | 作用 | 边界 |
| --- | --- | --- | --- |
| mart | `data/mart/` | 行情、指数、行业、财务、资金、可选公告索引/正文等结构化事实 | 优先事实源；外部局部查询结果不能伪装成全量分区 |
| feature | `data/features/` | 可复现筛查、排序、聚合信号 | 不能单独当事实结论 |
| evidence | `data/evidence/` | 产业价格、订单、产能、capex、政策、招投标等已确认外部 claim；可复用来源在 `data/evidence/sources/` | 补 mart 覆盖不了的事实；来源入口不等于证据 |
| relations | `data/relations/` | 公司、产品、客户、产业链节点和关系 | 慢变量关系库；每条记录必须带来源或推理依据、置信度和有效期 |
| runs / reports | `data/runs/`、`data/reports/` | 研究留痕和展示 | 不是事实源 |

## 研究纪律

- 不输出买入、卖出、加仓、减仓、仓位、止盈止损、下单等交易执行指令。
- 不用概念成分、热榜、人气或涨停池直接证明公司业务暴露度。
- 公司产品、客户、订单、产能、收入构成必须有公告、财报、IR、交易所问询、合格 evidence 或 traceable relations 支撑。
- 重点候选必须逐一有可审计证据链；缺 URL、发布日期或查询时间时，结论降级。
- Feature 只用于发现候选、强弱排序和交叉验证入口。
- 缺数据时写明缺口和影响，不用模型记忆补成确定事实。
- 用户给出的逻辑、小作文、研报摘要或其他 AI 结论默认是待验证假设。

## 最小命令面

CLI 只用于维护、检查、抽样、补证和留痕，不是 LLM 的固定研究流程。

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
uv run rdf datasets list --domain ashare_enrichment
uv run rdf datasets list --domain ashare_financials
uv run rdf datasets list --domain ashare_intraday
uv run rdf datasets meta ashare.daily --partition trade_date=YYYYMMDD
uv run rdf datasets read ashare.daily --partition trade_date=YYYYMMDD --limit 20
uv run rdf datasets read ashare.price_limits --partition trade_date=YYYYMMDD --columns security_id up_limit down_limit --limit 20
uv run rdf datasets read ashare.limit_list_ths --partition trade_date=YYYYMMDD --columns security_id name price pct_chg board_tag limit_reason open_num limit_order limit_amount --limit 20
uv run rdf datasets read ashare.index_weights --partition snapshot_date=YYYYMMDD --columns index_id security_id weight_trade_date weight --limit 20
uv run rdf datasets partitions ashare.daily --limit 10
uv run rdf datasets latest ashare.daily --columns security_id trade_date close pct_chg --limit 100
uv run rdf datasets read-window ashare.daily --as-of YYYYMMDD --count 20 --columns security_id trade_date close pct_chg --limit 100
uv run rdf ingest dataset ashare.daily --recipe tushare.daily.to_ashare_daily --partition trade_date=YYYYMMDD
uv run rdf ingest recipe tushare.daily.to_ashare_daily --partition trade_date=YYYYMMDD --dry-run
uv run rdf ingest run ashare_core_eod_daily --partition trade_date=YYYYMMDD
uv run rdf maintain ashare-core --as-of YYYYMMDD --lookback-trading-days 60
uv run rdf maintain status ashare-core --as-of YYYYMMDD --lookback-trading-days 60
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
uv run rdf ingest pipeline global_reference_weekly --partition cik=0000320193 --dry-run
uv run rdf ingest pipeline global_reference_universe_weekly --partition snapshot_date=YYYYMMDD --dry-run
uv run rdf ingest pipeline global_reference_companyfacts_on_demand --partition cik=0000320193 --dry-run
uv run rdf maintain ashare-main-business --period YYYYMMDD --stock-snapshot-date YYYYMMDD --limit 20 --refresh
uv run rdf maintain ashare-main-business --period YYYYMMDD --security-id 000001.SZ --segment-types P,D --refresh
uv run rdf maintain ashare-concept-members --snapshot-date YYYYMMDD --limit 20 --refresh
uv run rdf maintain ashare-ths-concepts --snapshot-date YYYYMMDD --limit 20 --refresh
uv run rdf maintain ashare-index-weights --snapshot-date YYYYMMDD --refresh
uv run rdf maintain ashare-financials --as-of YYYYMMDD --stock-snapshot-date YYYYMMDD --dataset-id ashare.income_statement --limit 20 --refresh
uv run rdf maintain ashare-financials --period YYYYMMDD --security-id 000001.SZ --dataset-id ashare.income_statement --refresh
uv run rdf maintain industry-report-index --query-date YYYYMMDD --lookback-days 30 --max-pages 1 --refresh
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
uv run rdf datasets read ashare.northbound_eligible --partition trade_date=YYYYMMDD --columns security_id security_name connect_type connect_type_name --limit 20
uv run rdf datasets read ashare.hsgt_top10 --partition trade_date=YYYYMMDD --columns security_id name market_type rank amount net_amount buy sell --limit 20
uv run rdf datasets read ashare.margin_detail --partition trade_date=YYYYMMDD --columns security_id name rzye rqye rzmre rzche rzrqye --limit 20
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
uv run rdf datasets read ashare.main_business --partition period=YYYYMMDD --partition security_id=000001.SZ --partition segment_type=P --limit 20
uv run rdf datasets read ashare.income_statement --partition period=YYYYMMDD --partition security_id=000001.SZ --limit 20
uv run rdf announcements discover --start-date YYYYMMDD --end-date YYYYMMDD --security-id 000001.SZ --keyword 订单 --limit 20
uv run rdf announcements discover --start-date YYYYMMDD --keyword 减持 --category 持股变动 --dry-run
uv run rdf announcements fetch-text --publish-date YYYYMMDD --announcement-id ANNOUNCEMENT_ID --source-url SOURCE_URL --security-id 000001.SZ
uv run rdf datasets read ashare.announcements --partition publish_date=YYYYMMDD --limit 20
uv run rdf announcements search --as-of YYYYMMDD --lookback-days 7 --category 持股变动 --keyword 减持 --limit 20
uv run rdf datasets read ashare.announcement_text --partition publish_date=YYYYMMDD --partition announcement_id=ANNOUNCEMENT_ID --columns announcement_id security_id title text_length parse_status --limit 20
uv run rdf datasets read industry.eastmoney_report_index --partition query_date=YYYYMMDD --columns query_date report_id title published_at source_name industry_name source_url --limit 20
uv run rdf datasets read global.sec_ticker_cik --partition snapshot_date=YYYYMMDD --limit 20
uv run rdf datasets read global.sec_companyfacts --partition cik=0000320193 --columns cik entity_name concept unit end_date filed_date form value --limit 20
uv run rdf ingest dataset ashare.intraday_snapshot --recipe eastmoney.push2.quote_snapshot.to_ashare_intraday_snapshot --partition snapshot_at=ISO_TIME --param secids=0.000001
uv run rdf features list
uv run rdf features build ashare.daily_momentum --as-of YYYYMMDD --window 20
uv run rdf features build ashare.market_strength --as-of YYYYMMDD --window 20
uv run rdf features build ashare.industry_strength --as-of YYYYMMDD --window 20
uv run rdf features build ashare.concept_strength --as-of YYYYMMDD --window 20
uv run rdf features build ashare.limit_sentiment --as-of YYYYMMDD --window 20
uv run rdf features meta ashare.daily_momentum --as-of YYYYMMDD --window 20
uv run rdf features read ashare.daily_momentum --as-of YYYYMMDD --window 20 --limit 30
uv run rdf features read ashare.market_strength --as-of YYYYMMDD --window 20 --limit 30
uv run rdf features read ashare.industry_strength --as-of YYYYMMDD --window 20 --limit 30
uv run rdf features read ashare.concept_strength --as-of YYYYMMDD --window 20 --limit 30
uv run rdf features read ashare.limit_sentiment --as-of YYYYMMDD --window 20 --limit 30
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
uv run rdf runs record --question "..." --as-of YYYYMMDD --mart-ref ashare.daily:trade_date=YYYYMMDD --validated-output model_output.validated.json
uv run rdf runs show RUN_ID
```

`rdf inventory` 是先看本地数据覆盖和质量的入口：它只读取 meta、records 和 registry，不抓取数据，不替代 `maintain status`，也不把 missing/degraded 自动补成可用事实。
`rdf inventory`、`rdf sources list/show` 和 `rdf datasets search` 都会返回 `coverage`：`full` 表示目标分区完整匹配，`partial` 表示只覆盖多键分区里的部分子分区，`latest_before` 表示按 as-of policy 读取目标日前最近快照，`latest` 表示未指定 as-of 时只取本地最新。只有 `full` 可当作目标分区完整覆盖；其他状态必须按局部样本或最近快照使用。
`rdf sources list/show` 是来源地图入口：它把来源、recipes、pipelines、dataset contract、as-of 本地状态和用途边界放在一起，帮助 Codex 判断该找哪个来源、能读哪些分区、哪些结论不能越界。
`rdf inventory features --as-of` 会列出 feature 的推荐窗口、已生成分区、输入 mart 可用分区数和是否可构建；窗口按本地已发布分区/交易日理解，不是自然日。
`rdf inventory plan` 把状态缺口和 `coverage` 缺口转成推荐 dry-run、执行命令、前置条件和用途边界；默认纳入 `missing/degraded` 状态缺口以及 `none/partial` 目标覆盖缺口，因此 `ready + partial` 的多键分区也会进入恢复计划。它只生成补数计划，不抓取、不写入。
`rdf ingest ... --dry-run` 是执行抓取前的结构化计划入口：它只解析 source、recipe、dataset、partition、请求参数、时间语义、用途边界和将写入的 raw/staging/mart 层，不请求外部来源，也不创建数据文件。
`rdf datasets partitions` 和 `rdf datasets latest` 只读取本地已发布 mart；latest 表示本地最新分区，不保证等于市场最新交易日。
`period` 分区的 filing 数据会把 `--as-of YYYYMMDD` 映射为最近已完整到期的报告期，例如 20260624 映射为 20260331；主营构成、财务表和股东结构都按这个报告期口径判断本地覆盖。
`rdf datasets read-window` 按本地已发布分区向前取 N 个分区；对 `ashare.daily` 这类交易日分区，它表示近 N 个已入库交易日，不是自然日。
`--lookback-trading-days` 是交易日数量，不是自然日数量。
mart 表按 dataset contract 的分区和 primary key 规范化；ingestion 会过滤到请求分区，storage 会拒绝表内分区列与路径分区不一致的数据。财报等来源返回同一主键的修订行时，读取 mart 得到的是去重后的最新版本，raw 层仍保留原始返回用于审计。
A 股核心 feature 包括 `ashare.daily_momentum`、`ashare.market_strength`、`ashare.industry_strength`、`ashare.concept_strength`、`ashare.limit_sentiment`，推荐窗口为 5/20/60 个已入库交易日。Feature 只能做候选线索、市场强弱和交叉验证，不能证明公司业务暴露。
`rdf evidence sources` 只用于复用结构稳定的 HTTP JSON 补证入口；优先用 `--dry-run` 或 source spec 告诉 Codex 如何获取，只有当次研究用到的结果才 fetch 并进入 evidence。它不能替代 mart、官方公告正文或关键 claim 摘录。
`rdf evidence profile` 和 `rdf evidence source-candidates` 只用于查看证据覆盖和可复用来源候选；candidate 不是事实增强，也不自动提高证据置信度。
`rdf evidence from-announcement-text` 只定位 CNINFO PDF 正文片段，输出 snippet candidates 且不落库；用于帮助 Codex/LLM 摘录具体 claim，不能直接替代 `rdf evidence ingest`。
`rdf relations ingest` 是 Codex 或人工分析后沉淀慢变量关系的默认入口；新架构不提供从 mart 或 evidence 自动派生 relations 的默认命令。不要把 `ashare.industry_members`、`ashare.ci_industry_members` 的高基数行业分类批量写入 curated relations。
`rdf runs record` 只做留痕和质量门检查，不回流为事实源；它会校验记录的 mart/feature/evidence/relations 引用是否存在，并阻断 feature-only 公司业务暴露、未记录 evidence/relation 引用和缺审计字段的外部来源。
`ashare.stock_basic` 是证券身份快照 reference fact，可定位证券代码、简称、公司全称、交易所、上市状态和实控人线索；它不能证明业务暴露，实控人线索也需官方披露交叉验证。
`ashare.company_profile` 是上市公司基础资料 reference fact，可用于公司画像、注册地归一化、联系信息和主营文本初筛；主营和经营范围文本只能做 evidence triage，不能替代官方披露正文证据。
`ashare.name_changes` 是历史股票名称 reference fact，可用于曾用名和旧简称检索；它不能证明业务暴露、产品、客户或订单事实。
`ashare.price_limits` 是每日涨跌停价格边界 EOD core fact，可用于校验涨跌停状态、价格约束和日线质量；它不能证明公司基本面、产品、客户、订单或业务暴露。
`ashare.limit_list_ths` 是同花顺涨停池 EOD enrichment fact，可用于短线情绪、连板高度、封单金额、开板次数和候选验证；`limit_reason` 是市场题材标签，不能证明公司业务正宗、产品供给、客户订单或收入暴露。
`ashare.index_weights` 是核心指数成分权重 snapshot fact，`snapshot_date` 表示本地快照日，`weight_trade_date` 表示该指数实际最近权重日；它适合指数归因、权重暴露和候选分层，不能证明公司业务暴露。
`ashare.northbound_eligible` 是陆股通 A 股标的资格 reference fact，可用于北向可买股票池分组、候选过滤和跨市场资金背景；它不能证明公司基本面、产品、客户、订单或业务暴露，不默认进入 curated relations。
`ashare.hsgt_top10` 是沪深股通十大成交股 EOD enrichment fact，可用于北向成交关注和市场验证；它不能证明公司基本面、产品、客户、订单或业务暴露。
`ashare.margin_detail` 是融资融券明细 EOD enrichment fact，可用于杠杆资金、融资余额和融券状态的市场验证；它不能证明公司基本面、产品、客户、订单或业务暴露。
`ashare.chip_distribution_perf` 和 `ashare.chip_distribution_detail` 是单股按需筹码分布事实，可用于获利盘、成本分布和市场结构验证；不要默认全市场拉取，不能证明公司基本面、产品、客户、订单或业务暴露，不默认进入 curated relations。
`ashare.shareholder_count`、`ashare.top10_holders`、`ashare.top10_float_holders` 和 `ashare.share_pledge_stats` 是所有权结构和质押统计事实，可用于股东户数变化、持有人集中度、质押风险和市场结构线索；`ashare.shareholder_trades` 与 `ashare.repurchase_events` 是股东增减持和回购事件结构化事实，`ashare.earnings_forecast_events` 是按公告日扫描的业绩预告事件流，可用 `rdf evidence from-dataset` 生成 `evidence_triage` 记录并作为公告补证入口；`ashare.block_trades` 是大宗交易事实，可做市场结构验证。它们都不能证明公司产品、客户、订单或业务暴露，不默认进入 curated relations；高置信公司动作和财务预告结论需回查官方公告正文。
`ashare.sw_industry_classification` 只表示申万行业层级字典，`ashare.industry_members`、`ashare.ci_industry_members` 只表示申万/中信行业分类，不证明公司业务暴露度。
`ashare.concept_members` 只表示东方财富概念/板块成分分类事实，可用于候选池扩展和市场线索分组；不能证明公司业务正宗或产品、客户、订单事实，不默认进入 curated relations。
`ashare.ths_index` 和 `ashare.ths_concept_members` 只表示同花顺概念/行业/题材清单和成分分类事实，可用于题材体系对照、候选扩展和市场线索分组；不能证明公司业务正宗或产品、客户、订单事实，不默认进入 curated relations。
`ashare.ths_hot_rank` 和 `ashare.dc_hot_rank` 只表示同花顺/东方财富热榜注意力事实，可用于候选扩展、市场关注度排序和题材热度交叉验证；排名、热度、概念标签和平台生成理由都不能作为公司业务暴露证据，不默认进入 curated relations。
`ashare.limit_step`、`ashare.limit_concept_rank`、`ashare.kpl_limit_list` 和 `ashare.kpl_concept_members` 只表示短线涨停/KPL 市场线索，可用于连板梯队、涨停题材和候选池验证；题材标签、KPL 描述和连板状态都不能作为公司业务暴露证据，不默认进入 curated relations。
`ashare.moneyflow_*` 只表示多来源资金流和南北向汇总事实，可用于市场验证、关注度排序和板块/概念资金背景；资金流入流出不能作为公司业务暴露证据，不默认进入 curated relations。
`ashare.announcements` 是可选维护的 CNINFO 全市场官方披露索引，可预览 `security -> cninfo:org`、`org -> filing` 和公告 ID 关系；标题和 PDF metadata 不能替代正文事实，也不是研究默认前置。
`rdf announcements discover` 按公司、关键词、类别和时间窗口远端查询 CNINFO，只返回候选且不写本地 mart；`rdf announcements search` 只检索本地已有 `ashare.announcements`。二者结果都只是公告补证入口，不证明公告正文 claim。
`ashare.announcement_text` 默认通过 `rdf announcements fetch-text` 对选中的 CNINFO PDF 按需解析；它是正文抽取结果，可作为具体 claim 摘录和校验的上游证据源。不要把整篇正文存在本身等同于某个具体业务 claim 已被证明。关键结论应先用 `rdf evidence from-announcement-text` 定位原文片段，再确认 claim 并显式 ingest evidence。
`industry.eastmoney_report_index` 通过 `rdf maintain industry-report-index` 维护，默认以 `query_date` 作为 as-of 上限并向前取自然日窗口，避免把 query_date 之后的研报带入当日研究。它是研报索引和 evidence seed，只能做补证优先级、行业关注度和外部观点线索；不能证明公司产品、客户、订单、收入暴露或产业链位置。
`ashare.main_business` 可按报告期和股票池批量维护，也可单公司按需维护；它支持主营构成和业务暴露线索，高置信结论仍需官方公告、年报、IR 或问询回复交叉验证。
`ashare_financials` 域可按报告期和股票池批量维护，也可单公司按需维护；它包含利润表、资产负债表、现金流量表、财务指标、业绩快报、分红、审计意见、披露日期和业绩预告，是财务事实和 evidence seed，不是交易执行信号。
`global.sec_ticker_cik` 和 `global.sec_companyfacts` 是 SEC EDGAR S1 跨市场参考事实，可用于海外同业、客户/供应链背景、身份映射、财务事实、evidence 和 context；不得生成 A 股主候选池。

默认不要新增“按问题生成研究报告”的命令。LLM 应直接读取数据和证据，自行推理。
