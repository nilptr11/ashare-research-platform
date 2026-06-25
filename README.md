# ashare-research-platform

可复现、可审计、可扩展的 A 股研究数据平台。

## 定位

项目拆成清晰的数据研究链路：

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

当前已落地的主干能力：

- `DatasetCatalog`：注册数据集契约。
- `ConnectorRegistry`：注册 Tushare、AkShare、巨潮、公告、政策、招投标等 source connectors。
- `TushareConnector` / `AkshareConnector` / HTTP JSON connectors：获取原始数据，不做分析判断。
- `RawStore`：保存 source 请求和原始响应。
- `MartPublisher`：把 connector 返回的数据发布为规范化 mart 分区。
- `MartReader`：读取 `data/mart/{dataset}/{partition}/part.parquet`。
- `ashare data`：检查、获取、更新本地 mart。
- `ashare mart`：读取注册 mart 分区和 `_meta.json`。
- `FeatureBuilder` / `FeatureStore`：发布可复现的 `feature_mart`。
- `ashare feature`：构建和读取市场结构特征。
- `EvidenceStore`：入库、校验、去重和检索外部产业证据。
- `ashare evidence`：管理 curated evidence、adapter proposal 和 accepted adapter 运行。
- `EvidenceAdapterRegistry`：把高频数值证据 candidate 晋升为 proposed adapter spec。
- `KnowledgeStore`：保存可追溯的实体、别名、产业链节点和关系。
- `ashare knowledge`：通过 proposal/accept 流程维护慢变量知识库。
- `ContextPackBuilder`：确定性生成 Codex 可读 context pack。
- `ashare context`：生成 market/industry/stock context pack，不生成分析结论。
- `ProtocolRegistry`：注册可复用分析模板和质量门；不强制默认分析框架。
- `RunRecorder`：保存 Codex 分析 run 的问题、上下文、输出和质量门留痕。
- `source_policy`：声明事实源优先级和不可回流规则。
- `reports`：生成 run trace report，报告本身不作为事实源。

## 安装

要求 Python 3.14+。

```bash
uv sync --group dev
```

## 常用命令

每日收盘后维护基础数据。`daily run` 会按完整日常基础库刷新，默认覆盖当日已有分区，保证可重入；无论 16:00、20:00 还是之后手动重跑，都使用同一个入口：

```bash
uv run ashare daily run
uv run ashare daily status
uv run ashare daily report
```

指定日期或只补缺失项：

```bash
uv run ashare daily run --as-of 20260624
uv run ashare daily repair --as-of 20260624
uv run ashare daily status --as-of 20260624 --format json
```

`daily run` 的职责是更新默认市场结构基础库、构建 `5/20/60` feature，并生成 `market_structure` context pack。财务重表、筹码、外部 evidence、knowledge 不进入默认 daily 阻断项；它们按候选池或具体研究问题单独维护。

列出已注册数据集和本地 mart：

```bash
uv run ashare connectors list
uv run ashare connectors fetch policy policy_search --url https://example.com/api -p keyword=AI
uv run ashare data list
uv run ashare data list --format json
```

检查已注册数据集在指定日期的可用性：

```bash
uv run ashare data check --as-of 20260623
uv run ashare data check --as-of 20260623 --dataset daily --format json
```

获取或更新 mart 分区：

```bash
uv run ashare data build daily --trade-date 20260623
uv run ashare data update daily --trade-date 20260623 --refresh
uv run ashare data build stock_basic --snapshot-date 20260623
uv run ashare data build trade_cal --exchange SSE --start-date 20260601 --end-date 20260630
```

`data build/update` 的路径是：

```text
TushareConnector -> data/raw/... -> MartPublisher -> data/mart/...
```

读取 mart 分区元数据：

```bash
uv run ashare mart meta daily --trade-date 20260623
```

读取 mart 分区数据：

```bash
uv run ashare mart read daily --trade-date 20260623 --limit 5
uv run ashare mart read stock_basic --snapshot-date 20260623 --format json
```

构建 feature mart：

```bash
uv run ashare feature list
uv run ashare feature build market_strength --as-of 20260623 --windows 5,20,60
uv run ashare feature build industry_strength --as-of 20260623 --windows 5,20,60
uv run ashare feature build concept_strength --as-of 20260623 --windows 5,20,60
uv run ashare feature build limit_sentiment --as-of 20260623 --windows 5,20
uv run ashare feature build leader_validation --as-of 20260623 --windows 5,20
uv run ashare feature build elasticity_candidates --as-of 20260623 --windows 5,20
```

读取 feature mart：

```bash
uv run ashare feature read market_strength --as-of 20260623 --window 5 --limit 10
uv run ashare feature meta limit_sentiment --as-of 20260623 --window 5
```

Feature 是可复现的分析特征，不是策略，也不是最终事实源。Codex 使用 feature 时必须遵守：

- feature 只用于筛查、排序、聚合展示和发现候选信号。
- 不能只凭 `strength_score`、`leader_score`、`elasticity_score` 等评分下结论。
- 形成题材扩散、资金确认、涨跌停结构、龙虎榜验证等关键判断前，必须回查对应 mart 明细，例如 `dc_index`、`moneyflow_dc`、`limit_list_d`、`limit_list_ths`、`top_list`。
- 必须先看 feature meta 里的 `inputs`、`quality_status`、`quality`、窗口和分区日期；如果状态不是 `ok/ready`，结论只能写成降级或暂无可靠数据。
- strategy 不在 feature 层。策略必须另行定义入场、退出、仓位、风控、交易成本和回测评估。

入库和检索外部产业证据：

```bash
uv run ashare evidence ingest evidence.json
uv run ashare evidence search --industry ai_infrastructure --topic capex --format json
uv run ashare evidence export evidence-capex.jsonl --industry ai_infrastructure --topic capex
uv run ashare evidence adapter-candidates --min-records 3
uv run ashare evidence adapter-specs propose --min-records 3
uv run ashare evidence adapter-specs list
uv run ashare evidence adapter-specs install adapter.json
uv run ashare evidence adapter-specs run adapter:capex
uv run ashare evidence collect --question "AI 算力硬件链是否被基本面验证" --as-of 20260623
```

`evidence collect` 当前只记录开放式采集缺口，不会伪装成已能自动搜索。高频数值证据可以先通过 `adapter-candidates` 识别，再用 `adapter-specs propose` 沉淀为 proposed adapter spec；accepted adapter spec 可通过 `adapter-specs run` 入库为 `maturity=adapter` 的 evidence。

提议、接受和检索知识库记录：

```bash
uv run ashare knowledge propose knowledge.json --reason "company filing checked"
uv run ashare knowledge proposals
uv run ashare knowledge accept <proposal_id>
uv run ashare knowledge search --entity 长飞光纤 --format json
uv run ashare knowledge snapshot --output data/knowledge/snapshot.json
```

Codex 默认只能写入 proposed knowledge；进入 `current.jsonl` 的记录必须先被 `accept`。

生成 context pack：

```bash
uv run ashare context build market-structure --as-of 20260623 --trade-days 120
uv run ashare context build industry ai_infrastructure --as-of 20260623
uv run ashare context build stock 603938.SH --as-of 20260623
```

Context pack 会写入 input hash、coverage、data gaps、quality flags 和 provenance。缺失数据不会被吞掉，会进入 `data_gaps`。

查看可复用 protocol 模板并记录 run。Protocol 不是默认强制框架；Codex 分析时优先服从用户当次指令。只有当你显式传 `--protocol`，或某个框架反复使用并稳定后，才需要引用注册模板。

```bash
uv run ashare protocols list
uv run ashare protocols validate market_structure.v1
uv run ashare protocols output-schema market_structure.v1
uv run ashare runs record --question "按我刚才给的框架分析 AI 算力硬件链" --as-of 20260623 --context-pack data/context_packs/market_structure/as_of=20260623/context.json
uv run ashare runs record --question "按市场结构模板分析 AI 算力硬件链" --protocol market_structure.v1 --as-of 20260623 --context-pack data/context_packs/market_structure/as_of=20260623/context.json
uv run ashare runs list
uv run ashare runs replay runs/<run_id>
```

`runs record` 不调用模型，只保存 Codex 已完成或正在整理的分析上下文、输出和质量门。未指定 `--protocol` 时，run 会记录为 `user_directed.v1`，表示分析约束来自用户当次问题和对话中的框架。

指定数据根目录：

```bash
uv run ashare --data-dir /path/to/data data list
```

## 数据边界

- 已注册 dataset 可以进入默认读取链路。
- 未注册 mart 只允许被发现和提示，不作为默认事实源。
- `data/raw` 保存 connector 请求和原始响应，但不作为 LLM 默认读取入口。
- `data/features` 只保存可复现特征和评分，不保存自然语言结论。
- `data/evidence` 保存外部产业证据，不能覆盖项目内已有行情、财务和公告事实。
- `data/knowledge` 保存结构化慢变量，不表达当日市场强弱。
- `data/context_packs` 是 LLM 默认读取的上下文快照，不直接生成结论。
- `protocols` 只保存可复用分析模板；临时框架以用户当次指令为准，可随 run 记录为 ad hoc protocol。
- `reports/` 和 `runs/` 只保存输出和留痕，不回流为事实源。
- 外部证据不能覆盖项目内已有行情、财务和公告事实。

## 当前入口

- 项目名：`ashare-research-platform`
- Python 包名：`ashare_research`
- CLI：`ashare`
- schema namespace：`ashare.*`
