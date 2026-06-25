# Skill-First 数据底座重构目标

本文档是当前重构方向的 source of truth：本项目要成为任意 LLM agent 可用的 A 股研究数据底座和 skill，而不是固定工作流系统。

## 项目定位

项目目标用户是 LLM agent。用户提出市场方向、产业假设或个股问题；agent 使用本项目准备好的基础数据、数据地图、来源注册和推理约束，自主完成市场主线识别、产业链拆解、公司业务暴露度验证、候选池分层和证据缺口整理。

项目不做：

- 不实现 Agent runtime。
- 不封装 OpenAI API、模型调用、消息路由或工具调用调度。
- 不提供 HTTP API server 作为主要使用方式。
- 不把用户问题编译成固定 CLI workflow。
- 不自动生成交易执行指令、仓位建议或下单动作。
- 不把 feature 分数、概念成分、热榜、人气或涨停池当成公司业务暴露度证据。

## 核心判断

数据底座不应该根据每个问题现场生成一份专属上下文作为默认入口。更优方式是：

1. 预先准备基础数据和质量状态。
2. 预先整理本地数据地图，让 agent 知道有什么、在哪里、能支持什么、不能支持什么。
3. 预先整理权威来源注册，让 agent 在本地数据不足时知道从哪里补证据。
4. 用 prompt / skill 约束研究纪律，而不是用 workflow 锁死分析路径。
5. 把 protocol 留给输出校验，把 run 留给复盘留痕。

## 目标使用方式

```text
用户问题或假设
  -> agent 读取 SKILL.md
  -> 读取 references/data-map.md，确认本地数据和边界
  -> 检查数据日期、覆盖范围和质量
  -> 读取相关 mart / feature / evidence / knowledge
  -> 数据不足时，根据 references/source-registry.md fetch 权威来源
  -> 用 prompt 约束事实、推断、假设和缺口
  -> 需要结构化产物时参考 protocol schema
  -> 需要复盘时 runs record 留痕
```

`playbook` 是示例路径，不是默认研究入口。中间快照层已从目标架构中移除；agent 应直接读取 mart、feature、evidence 和 knowledge，并在 run 中记录实际使用的数据引用。

## 目标分层

```text
skill_interface/
  SKILL.md、AGENTS.md

data_catalog/
  数据地图、dataset specs、feature registry、质量状态

source_registry/
  Tushare、AkShare、巨潮、交易所、公司公告、政策、协会、招投标等来源说明

data_kernel/
  connectors、raw_store、marts、features、daily maintenance

semantic_layer/
  knowledge、aliases、taxonomy、entity relation validation

evidence_layer/
  curated evidence、adapter candidates、accepted adapters

protocol_layer/
  输出 schema、质量门、结构化结果约束

run_layer/
  run record、replay、artifact hash、report
```

## 目标目录

```text
SKILL.md
AGENTS.md

references/
  data-map.md
  source-registry.md
  reasoning-policy.md
  data-access-guide.md
  playbooks/

docs/
  architecture/
  operations/
  playbooks/
  refactor/
  vendor/

prompts/
  industry-chain-selection-prompt.md
  industry-evidence-prompt.md

src/ashare_research/
  connectors/
  raw_store/
  datasets/
  marts/
  features/
  evidence/
  knowledge/
  protocols/
  runs/
  reports/
```

短期不必为了目录名字重排代码。优先让入口、数据地图、来源注册和边界表达正确；之后再按模块职责做物理目录重构。

## 数据准备目标

基础数据应尽可能提前准备，而不是在研究时临时拼装：

| 数据类型 | 维护节奏 | 作用 |
| --- | --- | --- |
| 交易日、股票池、基础身份 | 日常 / 快照 | 确定研究对象和交易日 |
| 行情、估值、指数、行业 | 日常 | 市场环境、行业强弱、候选发现 |
| 概念、成分、涨跌停、龙虎榜、资金 | 日常或可用时刷新 | 主题热度、扩散、市场认可线索 |
| 公告、财务、主营构成 | 定期 / 按需补齐 | 公司业务暴露度和基本面验证 |
| evidence | 按主题维护 | 产业价格、订单、产能、capex、政策、招投标 |
| knowledge | 人工或半自动接受 | 公司、产品、客户、产业链关系 |

## 来源准备目标

保留并强化 Tushare，但不要把它混在临时 reference 里。Tushare 应作为 source registry 和 connector 体系的一部分，服务于后续接口扩展。

来源注册需要回答：

1. 这个来源适合补什么事实？
2. 可信层级是什么？
3. 进入项目后应该成为 mart、evidence、knowledge proposal，还是 connector？
4. 是否能高频结构化更新？
5. 与本地已有 mart 冲突时如何处理？

## 交易模式的系统位置

用户提供的交易模式不是自动交易流程，而是研究框架：

1. 在结构性牛市或强产业周期中寻找主线。
2. 先选时代主线，再选高弹性标的。
3. 拆产业链，找供需最紧、重估弹性最大或国产替代最明确的环节。
4. 用公告、财务、evidence 和 accepted knowledge 验证公司业务暴露度。
5. 用市场结构、资金、龙头验证和弹性候选判断是否被市场定价。
6. 输出候选池、证据矩阵、风险和数据缺口。

它应该体现在 prompt 和 protocol 输出约束里，不应该被写成固定 CLI workflow，也不输出交易执行指令。

## 命令面的原则

CLI 只承担四类职责：

- 维护数据：更新、补齐、修复、发布。
- 检查数据：状态、质量、meta、样本。
- 管理证据：ingest、search、proposal、adapter。
- 留痕校验：protocol、run record、replay。

不新增“按某个问题生成研究结果”的命令。LLM agent 的优势在于读取数据后自己推理，不应该被大量问题型命令限制。

## 验收标准

重构完成后，LLM agent 应能做到：

1. 读取 `SKILL.md` 后知道项目不是交易执行系统。
2. 读取 `references/data-map.md` 后知道本地有哪些数据、能支持什么、不能支持什么。
3. 数据不足时能根据 `references/source-registry.md` 找权威来源补证据。
4. 能区分 mart 事实、feature 信号、evidence 外部证据、knowledge 慢变量和 run 留痕。
5. 面对产业链问题，能先拆链，再映射公司，再验证业务暴露度。
6. 能明确写出事实、推断、假设和数据缺口。
7. 能按 protocol schema 输出结构化结果。
8. 能用 run 记录研究过程，但不把 run 当事实源。
