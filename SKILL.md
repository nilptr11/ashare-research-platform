---
name: ashare-research-data-foundation
description: Use when an LLM agent researches A-share market themes, stock candidates, industry-chain decomposition, company exposure, evidence gaps, or market structure with this repository. This skill explains how to use the repo as a prepared data foundation and source map, not as an automated trading system or fixed agent workflow.
---

# A 股研究数据底座

本项目是给 LLM agent 直接使用的 A 股研究数据底座。不做自动化交易，也不把用户问题固定成预设 workflow。

用户提出方向或假设；LLM agent 读取本地已准备数据、识别缺口、必要时去权威来源补证据，并输出可追溯研究结论。交易决策和交易执行不属于本项目。

## 默认使用方式

1. 把用户问题当作研究假设，不要直接当结论。
2. 先读 `references/data-map.md`，确认本地有哪些已准备数据、适合支持哪些判断。
3. 检查数据日期、覆盖范围和质量；不要为了回答问题现场生成专属 workflow。
4. 本地数据足够时，直接读取 mart、feature、evidence、knowledge 的相关分区或样本。
5. 本地数据不足时，读 `references/source-registry.md`，只从权威或可解释来源补证据，并记录来源、日期和适用边界。
6. 用 `references/reasoning-policy.md` 约束结论：区分事实、推断、假设和缺口。
7. 当用户需要产业链拆解或候选池时，使用交易模式作为研究框架，不作为买卖或仓位指令。
8. 需要结构化输出时，再参考 protocol schema；需要复盘时，再用 run 留痕。

## 按需读取

- `references/data-map.md`：本地数据地图、数据层级、适用问题和盲区。默认先读。
- `references/dataset-index.md`：常用 dataset/feature 的快速定位索引。
- `references/source-registry.md`：本地数据不足时的权威来源和 fetch 原则。
- `references/reasoning-policy.md`：事实源优先级、降级规则、禁止事项。
- `prompts/industry-chain-selection-prompt.md`：用户要求主线选股、产业链拆解、候选池分层时读取。
- `src/ashare_research/protocols/specs/`：需要可校验结构化产物时读取。

## 数据层级

- `data/mart`：行情、公告、财务、指数、资金等结构化事实源。
- `data/features`：可复现的筛查、排序、聚合信号；不能单独当事实结论。
- `data/evidence`：项目内 mart 覆盖不了的产业外部证据。
- `data/knowledge`：公司、产品、客户、产业链节点等 accepted 慢变量关系。
- `runs` / `reports`：研究留痕，不回流为事实源。

## 研究纪律

- 不输出买入、卖出、加仓、减仓、仓位、止盈止损、下单等交易执行指令。
- 不用概念成分、热榜、人气或涨停池直接证明公司业务暴露度。
- 公司产品、客户、订单、产能、收入构成必须有公告、财报、IR、交易所问询、合格 evidence 或 accepted knowledge 支撑。
- Feature 只用于发现候选、强弱排序和交叉验证入口。
- 缺数据时写明缺口和影响，不用模型记忆补成确定性事实。

## 最小工具面

CLI 是维护、抽样和校验工具，不是 LLM agent 的思考流程。优先使用少量命令确认数据是否存在和是否新鲜：

```bash
uv run ashare daily status --as-of YYYYMMDD --format json
uv run ashare data list --format json
uv run ashare mart meta DATASET --trade-date YYYYMMDD
uv run ashare feature meta FEATURE --as-of YYYYMMDD --window 20
uv run ashare evidence search --industry INDUSTRY --format json
uv run ashare knowledge search --entity ENTITY --format json
```

只有在维护数据、补数据、验证输出或记录研究过程时，才下钻到更具体的命令。
