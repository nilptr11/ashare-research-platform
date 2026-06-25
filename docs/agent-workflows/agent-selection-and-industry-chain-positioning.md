# Agent 选股与产业链拆解定位

本文档定义本项目在“交易模式”语境下的实际边界：项目只做 Agent 主导的研究、拆解、筛查和留痕，不做自动化交易。

## 项目目标

本项目的目标是让 Agent 基于可审计数据完成四类工作：

1. 发现市场正在定价的产业主线。
2. 拆解产业链环节，识别最可能被重估的环节。
3. 把产业链环节映射到 A 股公司，并区分正宗受益、间接受益、弱相关和待验证。
4. 输出候选池、证据矩阵、风险标记、数据缺口和后续跟踪清单。

系统输出应是研究结论，不是交易指令。推荐输出状态包括：

| 状态 | 含义 |
| --- | --- |
| `core_research` | 产业链位置、市场认可和证据强度都较高，值得优先深入研究 |
| `elastic_watch` | 弹性和市场表现突出，但基本面或业务暴露度仍需继续验证 |
| `laggard_watch` | 同主线内尚未充分表现，但需要证明不是弱相关或弱票 |
| `evidence_needed` | 概念或价格信号存在，但缺公司披露、财务、订单或产业证据 |
| `excluded` | 业务暴露度弱、证据冲突、风险过高或只是蹭概念 |

## 非目标

项目不做以下事情：

- 不自动下单，不对接券商执行系统。
- 不输出买入、卖出、加仓、减仓、满仓、单吊等交易指令。
- 不把 feature 分数解释成策略信号。
- 不用外部搜索覆盖项目内已有行情、公告、财务和资金事实。
- 不把概念成分、热榜、人气榜、涨停池直接等同于公司业务暴露度。

## 推荐工作流

```text
daily status 确认数据 ready
  -> industry-chain context 确认主题上下文和缺口
  -> 行业/概念 feature 发现主线
  -> 产业链拆解
  -> A 股公司映射
  -> 公告、财务、evidence、knowledge 验证业务暴露度
  -> 候选池分层
  -> 输出证据缺口和后续跟踪清单
  -> runs 记录本次分析留痕
```

## 数据分工

| 研究问题 | 优先数据 | 使用边界 |
| --- | --- | --- |
| 市场有没有主线 | `market_strength`、`limit_sentiment`、指数/行业 mart | 只能判断市场结构，不判断公司基本面 |
| 哪些行业/概念正在变强 | `industry_strength`、`concept_strength`、`sw_daily`、`ci_daily`、`dc_index` | 概念强度是主线线索，不是公司受益证明 |
| 谁被市场认可 | `leader_validation`、`elasticity_candidates`、`moneyflow_dc`、`top_list`、`limit_list_ths` | 用于候选筛查和市场验证，不直接输出交易动作 |
| 公司卡在哪个产业链环节 | `fina_mainbz`、公告、年报、公司披露、knowledge | 必须有可追溯来源；缺失时标为 `evidence_needed` |
| 产业是否兑现 | evidence、政策、招投标、价格、产能、capex、协会数据 | 外部证据必须记录 source、URL、发布时间、查询时间和置信度 |
| 风险是否可接受 | 财务 mart、审计意见、公告、解禁/减持/问询等事件 | 只能标记风险和排除理由，不输出交易止损点 |

## 产业链拆解要求

每条主线至少拆到以下层级：

1. 上游资源、材料、设备或核心零部件。
2. 中游制造、集成、模组、系统或平台。
3. 下游应用、客户、渠道、运营或服务。
4. 当前景气最强或供需最紧的环节。
5. A 股可映射公司及其业务暴露度。
6. 证据状态：已验证、待验证、证据冲突或暂无可靠数据。

对每家公司，不能只因为进入某个概念板块就认定为正宗标的。必须至少给出一种可追溯支持：

- 公司公告、年报、半年报、招股书或定期报告。
- 公司投资者关系、互动平台、交易所问询回复。
- 项目内 accepted knowledge。
- 已入库 evidence，且 source_type 符合来源规则。

## 协议入口

重复使用该工作流时，使用注册协议：

```bash
uv run ashare context build industry-chain ai_infrastructure --as-of 20260623 --windows 5,20,60
uv run ashare protocols show industry_chain_selection.v1
uv run ashare protocols output-schema industry_chain_selection.v1
uv run ashare runs record --question "按主线选股与产业链拆解协议分析 AI 算力硬件链" --protocol industry_chain_selection.v1 --as-of 20260623 --context-pack data/context_packs/industry_chain/as_of=20260623/key=ai_infrastructure/context.json --validated-output output.json
```

该协议输出候选池、证据矩阵和后续跟踪计划。若缺产业链证据或公司业务暴露度证据，结论必须降级，并在 `data_gaps` 中写明影响和建议补数路径。
研究产物通过 `runs record` 留痕，不回流为 mart、feature、evidence 或 knowledge 事实源。

Agent 生成分析时优先使用 prompt：

```text
prompts/industry-chain-selection-prompt.md
```
