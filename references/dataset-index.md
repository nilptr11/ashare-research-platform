# 数据索引

本文件是给 LLM agent 快速定位数据用的索引。它不是完整契约；完整注册项以 `uv run rdf datasets list`、`uv run rdf features list` 和 mart/feature meta 为准。

## 使用方式

1. 先用 `references/data-map.md` 判断需要哪类事实。
2. 不确定 dataset id 时，先用 `rdf datasets search 关键词 --as-of YYYYMMDD` 按研究意图搜索本地 mart 和契约。
3. 在本索引中确认候选 dataset 或 feature 的用途边界。
4. 用 `rdf datasets meta` / `rdf features meta` 确认分区日期、行数、输入和质量。
5. 只读取与用户问题相关的最小样本或分区；读取结果里的分区、质量、temporal、usage、boundary 和 lineage 与 `records` 同等重要。

## 当前核心 Mart

| 目标 | Dataset | 分区 | 适合回答 | 边界 |
| --- | --- | --- | --- | --- |
| 交易日 | `ashare.trade_calendar` | `exchange=SSE` | 交易日判断、近 60 日维护窗口 | 不代表市场强弱 |
| 股票身份 | `ashare.stock_basic` | `snapshot_date=YYYYMMDD` | 股票池、简称、公司全称、交易所、上市/退市日期和实控人线索 | 不证明业务暴露、产品、客户或订单；实控人需官方披露交叉验证 |
| 上市公司资料 | `ashare.company_profile` | `snapshot_date=YYYYMMDD` | 注册地、办公地址、董秘、员工数和主营/经营范围文本初筛 | 主营/经营范围不能替代官方披露正文对业务暴露的证明 |
| 股票曾用名 | `ashare.name_changes` | `snapshot_date=YYYYMMDD` | 历史股票名称、旧简称和曾用名检索 | 不证明公司业务暴露、当前法律主体、产品、客户或订单 |
| A 股个股日线 | `ashare.daily` | `trade_date=YYYYMMDD` | 收盘后价格、涨跌幅、成交量、成交额；主候选池市场线索 | 不证明公司基本面或业务暴露 |
| 日线指标 | `ashare.daily_basic` | `trade_date=YYYYMMDD` | 换手、市值、估值、量比 | 估值需结合财务口径 |
| 涨跌停价格 | `ashare.price_limits` | `trade_date=YYYYMMDD` | 每日涨停价、跌停价、价格约束和日线质量校验 | 不证明公司基本面、产品、客户、订单或业务暴露 |
| 指数行情 | `ashare.index_daily`, `ashare.index_daily_basic` | `trade_date=YYYYMMDD` | 大盘、风格和估值环境 | 不直接推出个股结论 |
| 核心指数权重 | `ashare.index_weights` | `snapshot_date=YYYYMMDD` | 上证50、沪深300、中证500、中证1000等核心指数成分权重、指数归因和权重暴露 | 不证明公司基本面、产品、客户、订单或业务暴露；`weight_trade_date` 才是实际权重日 |
| 行业行情 | `ashare.sw_daily`, `ashare.ci_daily` | `trade_date=YYYYMMDD` | 行业强弱交叉验证 | 不能替代产业链拆解 |
| 概念和情绪 | `ashare.dc_index`, `ashare.limit_list_d`, `ashare.limit_list_ths`, `ashare.top_list`, `ashare.ths_hot_rank`, `ashare.dc_hot_rank` | `trade_date=YYYYMMDD` | 题材、短线情绪、同花顺涨停池、龙虎榜和热榜注意力线索 | 不证明公司正宗程度；涨停池题材标签、热榜排名、平台生成理由只作市场线索 |
| 短线涨停/KPL | `ashare.limit_step`, `ashare.limit_concept_rank`, `ashare.kpl_limit_list`, `ashare.kpl_concept_members` | `trade_date=YYYYMMDD` | 连板梯队、涨停题材排行、开盘啦涨停池和题材成分候选 | 不证明公司业务暴露；KPL 描述和题材标签只作 evidence triage 和市场线索 |
| 资金流 | `ashare.moneyflow_dc`, `ashare.moneyflow_tushare`, `ashare.moneyflow_ths`, `ashare.moneyflow_board_dc`, `ashare.moneyflow_industry_ths`, `ashare.moneyflow_concept_ths`, `ashare.moneyflow_hsgt` | `trade_date=YYYYMMDD` | 个股、板块、行业、概念和南北向资金流，市场验证和关注度排序 | 不能证明公司业务、产品、客户、订单或收入暴露；不默认进入 curated relations |
| 陆股通标的 | `ashare.northbound_eligible` | `trade_date=YYYYMMDD` | 沪股通/深股通可买 A 股股票池、候选过滤和北向背景 | 不证明公司基本面、产品、客户、订单或业务暴露；不默认进入 curated relations |
| 北向十大成交 | `ashare.hsgt_top10` | `trade_date=YYYYMMDD` | 沪深股通十大成交股、北向成交关注和市场验证 | 不证明公司基本面、产品、客户、订单或业务暴露 |
| 融资融券明细 | `ashare.margin_detail` | `trade_date=YYYYMMDD` | 融资余额、融券余额、融资买入/偿还、杠杆资金状态 | 不证明公司基本面、产品、客户、订单或业务暴露 |
| 筹码分布 | `ashare.chip_distribution_perf`, `ashare.chip_distribution_detail` | `trade_date=YYYYMMDD`, `security_id=000001.SZ` | 单股获利盘、成本分布、筹码价格分布和市场结构验证 | 按需拉取，不默认全市场维护；不证明公司基本面、产品、客户、订单或业务暴露 |
| 股东户数 | `ashare.shareholder_count` | `period=YYYYMMDD` | 定期股东户数、股东户数变化和筹码集中度线索 | 不证明公司产品、客户、订单、收入或业务暴露 |
| 十大股东 | `ashare.top10_holders` | `period=YYYYMMDD` | 定期前十大股东、持有人集中度和持股变化线索 | 不证明公司业务暴露、客户、订单或收入来源；不默认进入 curated relations |
| 十大流通股东 | `ashare.top10_float_holders` | `period=YYYYMMDD` | 定期前十大流通股东、流通盘筹码集中度和持股变化线索 | 不证明公司业务暴露、客户、订单或收入来源；不默认进入 curated relations |
| 股权质押统计 | `ashare.share_pledge_stats` | `end_date=YYYYMMDD` | 股权质押笔数、未解押/已解押数量、质押比例和所有权风险线索 | 周期事实，按 `latest_before` 使用；不证明业务暴露 |
| 股东增减持 | `ashare.shareholder_trades` | `ann_date=YYYYMMDD` | 股东增持/减持公告事件、变动数量、变动比例和公告补证入口；可用 `rdf evidence from-dataset` 生成 `evidence_triage` | 结构化来源只作 evidence triage；高置信结论需回查官方公告正文 |
| 回购事件 | `ashare.repurchase_events` | `ann_date=YYYYMMDD` | 回购进展、回购规模、价格区间和公告补证入口；可用 `rdf evidence from-dataset` 生成 `evidence_triage` | 结构化来源只作 evidence triage；高置信结论需回查官方公告正文 |
| 业绩预告事件 | `ashare.earnings_forecast_events` | `ann_date=YYYYMMDD` | 按公告日扫描的业绩预告事件、预告类型、净利润区间和变动原因；可用 `rdf evidence from-dataset` 生成 `evidence_triage` | 结构化来源只作 financial/event triage；高置信预告结论需回查官方公告正文 |
| 大宗交易 | `ashare.block_trades` | `trade_date=YYYYMMDD` | 大宗交易价格、成交量、买卖席位和市场结构验证 | 不证明公司基本面、产品、客户、订单或业务暴露 |
| 申万行业层级 | `ashare.sw_industry_classification` | `snapshot_date=YYYYMMDD` | 申万 2021 一、二、三级行业层级、行业代码、父级关系 | 不证明产品、客户、订单、收入或业务暴露度；不默认进入 curated relations |
| 申万行业成员 | `ashare.industry_members` | `snapshot_date=YYYYMMDD` | 股票行业分类、候选池分组、行业映射 | 不证明产品、客户、订单、收入或业务暴露度；不默认进入 curated relations |
| 中信行业成员 | `ashare.ci_industry_members` | `snapshot_date=YYYYMMDD` | 股票行业分类、候选池分组、申万/中信交叉验证 | 不证明产品、客户、订单、收入或业务暴露度；不默认进入 curated relations |
| 东财概念/板块成员 | `ashare.concept_members` | `snapshot_date=YYYYMMDD`, `concept_id=CONCEPT_ID` | 概念/板块成分、候选扩展、市场线索分组 | 不证明公司业务正宗、产品、客户、订单或收入暴露；不默认进入 curated relations |
| 同花顺概念/题材成员 | `ashare.ths_index`, `ashare.ths_concept_members` | `snapshot_date=YYYYMMDD`, `concept_id=CONCEPT_ID` | 同花顺概念/行业/题材清单和成分、涨停池标签对照、候选扩展 | 不证明公司业务正宗、产品、客户、订单或收入暴露；不默认进入 curated relations |
| 主营构成 | `ashare.main_business` | `period=YYYYMMDD`, `security_id=000001.SZ`, `segment_type=P/D` | 产品/地区收入构成、业务暴露线索和 evidence seed | 高置信结论需回查官方公告或年报正文 |
| 财务三表和指标 | `ashare.income_statement`, `ashare.balance_sheet`, `ashare.cash_flow`, `ashare.financial_indicator` | `period=YYYYMMDD`, `security_id=000001.SZ` | 收入、利润、资产负债、现金流、每股指标等财务事实 | 产品、客户、订单或产业链位置证明 |
| 财务披露事件 | `ashare.earnings_express`, `ashare.dividend`, `ashare.audit_opinion`, `ashare.disclosure_date`, `ashare.earnings_forecast` | `period=YYYYMMDD`, `security_id=000001.SZ` | 快报、分红、审计意见、披露日期、业绩预告 | 公告正文中的具体业务 claim |
| 官方公告索引 | `ashare.announcements` | `publish_date=YYYYMMDD` | 可选维护的 CNINFO 披露入口、org_id、PDF metadata 和公告 evidence seed | 标题不能替代正文事实；org_id 只证明披露主体身份；不是研究默认前置 |
| 官方公告正文 | `ashare.announcement_text` | `publish_date=YYYYMMDD`, `announcement_id=ANNOUNCEMENT_ID` | 按需解析的 CNINFO PDF 正文、PDF 哈希、页数、解析状态 | 不能自动证明具体业务 claim；仍需摘录具体 claim |
| A 股盘中快照 | `ashare.intraday_snapshot` | `snapshot_at=ISO_TIME` | 盘中价格、涨跌幅、成交额临时观察 | provisional 数据，不能覆盖 `ashare.daily`，不能生成主候选 |
| SEC filing 索引 | `global.sec_filings` | `cik=0000320193` | 海外公司披露、跨市场参考和 evidence context | 不直接生成 A 股主候选 |
| SEC ticker-CIK 映射 | `global.sec_ticker_cik` | `snapshot_date=YYYYMMDD` | 海外证券、issuer 和 CIK 身份映射 reference fact | 不直接生成 A 股主候选；不替代 A 股证券身份 |
| SEC companyfacts | `global.sec_companyfacts` | `cik=0000320193` | 海外公司 XBRL 财务事实、跨市场估值和 evidence seed | 不直接生成 A 股主候选；不证明 A 股公司业务暴露 |
| 东财行业研报索引 | `industry.eastmoney_report_index` | `query_date=YYYYMMDD` | 行业研究关注度、evidence seed | 不证明公司业务暴露 |

## Feature

`rdf features read` 与 mart 读取一样返回结构化 JSON；`records` 是信号值，顶层 `inputs`、`quality`、`usage` 和 `boundary` 决定它能不能用于当前结论。

| Feature | 分区 | 适合回答 | 必须回查 |
| --- | --- | --- | --- |
| `ashare.daily_momentum` | `as_of=YYYYMMDD`, `window=N` | A 股近期收益和成交扩张排序 | `ashare.daily`，以及公司证据 |
| `ashare.market_strength` | `as_of=YYYYMMDD`, `window=N` | 大盘、核心指数和风格环境强弱 | `ashare.index_daily` / `ashare.index_daily_basic`；不能推出个股业务结论 |
| `ashare.industry_strength` | `as_of=YYYYMMDD`, `window=N` | 申万/中信行业强弱排序和行业线索 | `ashare.sw_daily` / `ashare.ci_daily`；公司证据另补 |
| `ashare.concept_strength` | `as_of=YYYYMMDD`, `window=N` | 东方财富概念/板块强弱排序和题材线索 | `ashare.dc_index`、概念成分和公司证据 |
| `ashare.limit_sentiment` | `as_of=YYYYMMDD`, `window=N` | 涨跌停数量、同花顺涨停池、连板高度和短线情绪 | `ashare.limit_list_d` / `ashare.limit_list_ths`；不能证明基本面 |
| `industry.report_attention` | `as_of=YYYYMMDD`, `window=N` | 行业研报关注度和补证优先级 | `industry.eastmoney_report_index`，以及原始研报或公告 |

## 产业链和公司暴露

| 目标 | 优先数据 |
| --- | --- |
| 产业链拆解 | `references/source-registry.md`、evidence、traceable relations |
| 公司产品/客户/订单 | 公告、年报、半年报、IR、问询回复、合格 evidence、traceable relations |
| 公司主营构成 | `ashare.main_business`、定期报告、公告 |
| 公司财务事实 | `ashare.income_statement`、`ashare.balance_sheet`、`ashare.cash_flow`、`ashare.financial_indicator`、定期报告 |
| 产业价格/供需/capex/招投标 | evidence 或可复用来源拉取的 evidence |
| 候选池分层 | mart/feature 发现线索，evidence/relations/财务验证暴露度 |

## 最小确认命令

```bash
uv run rdf inventory summary --as-of YYYYMMDD
uv run rdf inventory datasets --as-of YYYYMMDD --domain ashare_core
uv run rdf inventory datasets --use company_business_exposure
uv run rdf inventory plan --as-of YYYYMMDD
uv run rdf inventory plan --as-of YYYYMMDD --coverage-status partial --no-features
uv run rdf datasets search 资金流 --as-of YYYYMMDD --use market_validation
uv run rdf datasets search 公告 --as-of YYYYMMDD --use evidence
uv run rdf ingest recipe tushare.daily.to_ashare_daily --partition trade_date=YYYYMMDD --dry-run
uv run rdf datasets meta ashare.daily --partition trade_date=YYYYMMDD
uv run rdf maintain ashare-core --as-of YYYYMMDD --lookback-trading-days 60
uv run rdf maintain status ashare-core --as-of YYYYMMDD --lookback-trading-days 60
uv run rdf datasets meta ashare.intraday_snapshot --partition snapshot_at=ISO_TIME
uv run rdf datasets read ashare.daily --partition trade_date=YYYYMMDD --limit 30
uv run rdf datasets read ashare.price_limits --partition trade_date=YYYYMMDD --columns security_id up_limit down_limit --limit 30
uv run rdf datasets read ashare.limit_list_ths --partition trade_date=YYYYMMDD --columns security_id name price pct_chg board_tag limit_reason open_num limit_order limit_amount --limit 30
uv run rdf maintain ashare-index-weights --snapshot-date YYYYMMDD --refresh
uv run rdf datasets read ashare.index_weights --partition snapshot_date=YYYYMMDD --columns index_id security_id weight_trade_date weight --limit 30
uv run rdf datasets partitions ashare.daily --limit 10
uv run rdf datasets latest ashare.daily --columns security_id trade_date close pct_chg --limit 100
uv run rdf datasets read-window ashare.daily --as-of YYYYMMDD --count 20 --columns security_id trade_date close pct_chg --limit 100
uv run rdf datasets read ashare.stock_basic --partition snapshot_date=YYYYMMDD --columns security_id symbol name fullname exchange list_date act_name act_ent_type --limit 30
uv run rdf ingest pipeline ashare_identity_weekly --partition snapshot_date=YYYYMMDD --refresh
uv run rdf datasets read ashare.company_profile --partition snapshot_date=YYYYMMDD --columns security_id exchange province city office employees main_business --limit 30
uv run rdf datasets read ashare.name_changes --partition snapshot_date=YYYYMMDD --columns security_id name start_date end_date change_reason --limit 30
uv run rdf datasets read ashare.sw_industry_classification --partition snapshot_date=YYYYMMDD --columns source_system index_id industry_name level industry_code parent_code --limit 30
uv run rdf datasets read ashare.industry_members --partition snapshot_date=YYYYMMDD --limit 30
uv run rdf datasets read ashare.ci_industry_members --partition snapshot_date=YYYYMMDD --limit 30
uv run rdf maintain ashare-concept-members --snapshot-date YYYYMMDD --limit 20 --refresh
uv run rdf datasets read ashare.concept_members --partition snapshot_date=YYYYMMDD --partition concept_id=CONCEPT_ID --limit 30
uv run rdf maintain ashare-ths-concepts --snapshot-date YYYYMMDD --limit 20 --refresh
uv run rdf datasets read ashare.ths_index --partition snapshot_date=YYYYMMDD --columns concept_id name index_type source_member_count --limit 30
uv run rdf datasets read ashare.ths_concept_members --partition snapshot_date=YYYYMMDD --partition concept_id=CONCEPT_ID --limit 30
uv run rdf ingest pipeline ashare_market_attention_daily --partition trade_date=YYYYMMDD --refresh
uv run rdf datasets read ashare.ths_hot_rank --partition trade_date=YYYYMMDD --columns rank_type subject_id subject_name rank heat concept_tags_json --limit 30
uv run rdf datasets read ashare.dc_hot_rank --partition trade_date=YYYYMMDD --columns rank_type security_id security_name rank pct_chg price --limit 30
uv run rdf ingest pipeline ashare_short_term_sentiment_daily --partition trade_date=YYYYMMDD --refresh
uv run rdf datasets read ashare.limit_step --partition trade_date=YYYYMMDD --columns security_id security_name limit_up_days --limit 30
uv run rdf datasets read ashare.limit_concept_rank --partition trade_date=YYYYMMDD --columns concept_id concept_name rank limit_up_count consecutive_limit_count up_stat --limit 30
uv run rdf datasets read ashare.kpl_limit_list --partition trade_date=YYYYMMDD --columns security_id security_name board_status theme_tags limit_reason limit_order turnover_rate --limit 30
uv run rdf datasets read ashare.kpl_concept_members --partition trade_date=YYYYMMDD --columns concept_id concept_name security_id security_name hot_num vendor_exposure_desc --limit 30
uv run rdf ingest pipeline ashare_moneyflow_daily --partition trade_date=YYYYMMDD --refresh
uv run rdf datasets read ashare.moneyflow_dc --partition trade_date=YYYYMMDD --columns security_id security_name net_amount net_amount_rate buy_elg_amount buy_lg_amount --limit 30
uv run rdf datasets read ashare.moneyflow_board_dc --partition trade_date=YYYYMMDD --columns board_type subject_id subject_name rank net_amount net_amount_rate --limit 30
uv run rdf datasets read ashare.moneyflow_hsgt --partition trade_date=YYYYMMDD --columns north_money south_money hgt sgt --limit 30
uv run rdf datasets read ashare.northbound_eligible --partition trade_date=YYYYMMDD --columns security_id security_name connect_type connect_type_name --limit 30
uv run rdf datasets read ashare.hsgt_top10 --partition trade_date=YYYYMMDD --columns security_id name market_type rank amount net_amount buy sell --limit 30
uv run rdf datasets read ashare.margin_detail --partition trade_date=YYYYMMDD --columns security_id name rzye rqye rzmre rzche rzrqye --limit 30
uv run rdf ingest pipeline ashare_chips_on_demand --partition trade_date=YYYYMMDD --partition security_id=000001.SZ --refresh
uv run rdf datasets read ashare.chip_distribution_perf --partition trade_date=YYYYMMDD --partition security_id=000001.SZ --columns security_id winner_rate cost_50pct cost_85pct cost_95pct weight_avg --limit 30
uv run rdf datasets read ashare.chip_distribution_detail --partition trade_date=YYYYMMDD --partition security_id=000001.SZ --columns security_id price percent --limit 30
uv run rdf ingest pipeline ashare_ownership_periodic --partition period=YYYYMMDD --refresh
uv run rdf datasets read ashare.shareholder_count --partition period=YYYYMMDD --columns security_id ann_date holder_num --limit 30
uv run rdf datasets read ashare.top10_holders --partition period=YYYYMMDD --columns security_id ann_date holder_name holder_type hold_amount hold_ratio hold_change --limit 30
uv run rdf datasets read ashare.top10_float_holders --partition period=YYYYMMDD --columns security_id ann_date holder_name holder_type hold_amount hold_float_ratio hold_change --limit 30
uv run rdf ingest pipeline ashare_share_pledge_weekly --partition end_date=YYYYMMDD --refresh
uv run rdf datasets read ashare.share_pledge_stats --partition end_date=YYYYMMDD --columns security_id pledge_count unrest_pledge rest_pledge total_share pledge_ratio --limit 30
uv run rdf ingest pipeline ashare_corporate_action_events_daily --partition ann_date=YYYYMMDD --refresh
uv run rdf datasets read ashare.shareholder_trades --partition ann_date=YYYYMMDD --columns security_id holder_name holder_type in_de change_vol change_ratio after_share after_ratio avg_price --limit 30
uv run rdf datasets read ashare.repurchase_events --partition ann_date=YYYYMMDD --columns security_id end_date process_status volume amount high_limit low_limit --limit 30
uv run rdf ingest pipeline ashare_financial_event_daily --partition ann_date=YYYYMMDD --refresh
uv run rdf datasets read ashare.earnings_forecast_events --partition ann_date=YYYYMMDD --columns security_id period forecast_type p_change_min p_change_max net_profit_min net_profit_max change_reason --limit 30
uv run rdf ingest pipeline ashare_block_trades_daily --partition trade_date=YYYYMMDD --refresh
uv run rdf datasets read ashare.block_trades --partition trade_date=YYYYMMDD --columns security_id price volume amount buyer seller --limit 30
uv run rdf maintain ashare-main-business --period YYYYMMDD --stock-snapshot-date YYYYMMDD --limit 20 --refresh
uv run rdf maintain ashare-main-business --period YYYYMMDD --security-id 000001.SZ --segment-types P,D --refresh
uv run rdf datasets read ashare.main_business --partition period=YYYYMMDD --partition security_id=000001.SZ --partition segment_type=P --limit 30
uv run rdf datasets scan ashare.main_business --partition period=YYYYMMDD --columns security_id segment_type item_name sales --limit 50
uv run rdf maintain ashare-financials --as-of YYYYMMDD --stock-snapshot-date YYYYMMDD --dataset-id ashare.income_statement --limit 20 --refresh
uv run rdf maintain ashare-financials --period YYYYMMDD --security-id 000001.SZ --dataset-id ashare.income_statement --refresh
uv run rdf datasets read ashare.income_statement --partition period=YYYYMMDD --partition security_id=000001.SZ --limit 30
uv run rdf datasets scan ashare.income_statement --partition period=YYYYMMDD --columns security_id period total_revenue n_income --limit 50
uv run rdf datasets read ashare.announcements --partition publish_date=YYYYMMDD --limit 30
uv run rdf announcements discover --start-date YYYYMMDD --end-date YYYYMMDD --security-id 000001.SZ --keyword 订单 --limit 20
uv run rdf announcements search --as-of YYYYMMDD --lookback-days 7 --category 持股变动 --keyword 减持 --limit 30
uv run rdf announcements fetch-text --publish-date YYYYMMDD --announcement-id ANNOUNCEMENT_ID --source-url SOURCE_URL --security-id 000001.SZ
uv run rdf maintain industry-report-index --query-date YYYYMMDD --lookback-days 30 --max-pages 1 --refresh
uv run rdf datasets read ashare.announcement_text --partition publish_date=YYYYMMDD --partition announcement_id=ANNOUNCEMENT_ID --columns announcement_id security_id title text_length parse_status --limit 30
uv run rdf datasets scan ashare.announcement_text --partition publish_date=YYYYMMDD --columns announcement_id security_id title text_length parse_status --limit 50
uv run rdf datasets read industry.eastmoney_report_index --partition query_date=YYYYMMDD --columns query_date report_id title published_at source_name industry_name source_url --limit 30
uv run rdf evidence from-announcement-text --partition publish_date=YYYYMMDD --partition announcement_id=ANNOUNCEMENT_ID --query 关键词 --limit 20
uv run rdf datasets read global.sec_ticker_cik --partition snapshot_date=YYYYMMDD --limit 30
uv run rdf datasets read global.sec_companyfacts --partition cik=0000320193 --columns cik entity_name concept unit end_date filed_date form value --limit 30
uv run rdf inventory features --as-of YYYYMMDD
uv run rdf features meta ashare.daily_momentum --as-of YYYYMMDD --window N
uv run rdf features read ashare.daily_momentum --as-of YYYYMMDD --window N --limit 30
uv run rdf features read ashare.market_strength --as-of YYYYMMDD --window N --limit 30
uv run rdf features read ashare.industry_strength --as-of YYYYMMDD --window N --limit 30
uv run rdf features read ashare.concept_strength --as-of YYYYMMDD --window N --limit 30
uv run rdf features read ashare.limit_sentiment --as-of YYYYMMDD --window N --limit 30
uv run rdf evidence sources list
uv run rdf evidence sources fetch SOURCE_ID --param key=value --limit 20
uv run rdf evidence from-dataset global.sec_companyfacts --partition cik=0000320193 --limit 50
uv run rdf evidence from-dataset ashare.shareholder_trades --partition ann_date=YYYYMMDD --limit 50
uv run rdf evidence from-dataset ashare.repurchase_events --partition ann_date=YYYYMMDD --limit 50
uv run rdf evidence from-dataset ashare.earnings_forecast_events --partition ann_date=YYYYMMDD --limit 50
uv run rdf evidence profile --topic TOPIC --limit 20
uv run rdf evidence source-candidates --min-records 3 --limit 20
uv run rdf evidence list --industry INDUSTRY
uv run rdf evidence export evidence-slice.jsonl --company 000001.SZ --period YYYYMMDD
uv run rdf relations ingest relations.json
uv run rdf relations profile --limit 20
uv run rdf relations neighborhood --entity ENTITY --limit 50
uv run rdf relations list --subject ENTITY
uv run rdf relations snapshot --subject ENTITY --output relation-snapshot.json
```

读取 inventory、source map 或 dataset search 时先看 `coverage.status`：`full` 才是目标分区完整覆盖，`partial` 是多键分区的局部子分区，`latest_before` 是目标日前最近快照，`latest` 是未指定 as-of 的本地最新。公司研究结论不能把 `partial/latest_before/latest` 当成目标日全量事实；`rdf inventory plan` 默认会把 `none/partial` 覆盖缺口纳入补数计划。

财务 mart 分区按分区值和 primary key 规范化；若 Tushare 返回多报告期或同一公告日修订行，mart 只保留请求报告期内的修订/最新行，原始多行留在 raw。
