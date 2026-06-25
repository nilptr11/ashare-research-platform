# 数据能力地图

本文档告诉 Codex：面对某类研究问题，可以参考哪些数据能力、能支持什么判断、不能支持什么判断。

默认入口仍然是 `SKILL.md` 和 `codex/data-map.md`。本文件是问题到数据的索引，不是固定 workflow，也不要求 Codex 每次先运行 capability CLI。

机器可读能力卡片已经内置在 `src/ashare_research/capabilities/specs/`，优先用 CLI 读取：

```bash
uv run ashare capabilities list --format json
uv run ashare capabilities show CAPABILITY_ID --format json
```

## 市场环境判断

**适合回答**

- 当前市场是顺风、逆风还是震荡？
- 风格和主要指数是否支持成长主线？

**数据入口**

- `market_strength`
- `index_daily`
- `index_dailybasic`
- `limit_sentiment`

**常用命令**

```bash
uv run ashare feature read market_strength --as-of YYYYMMDD --window 20 --format json
uv run ashare feature read limit_sentiment --as-of YYYYMMDD --window 20 --format json
```

**能支持**

- 指数强弱；
- 成交趋势；
- 短线情绪状态；
- 市场是否适合进一步寻找主线。

**不能支持**

- 具体公司基本面；
- 公司业务暴露度；
- 自动交易动作。

## 主线强度识别

**适合回答**

- 哪些行业或概念正在被市场定价？
- 主线是否扩散？

**数据入口**

- `industry_strength`
- `concept_strength`
- `dc_index`
- `sw_daily`
- `ci_daily`

**常用命令**

```bash
uv run ashare feature read industry_strength --as-of YYYYMMDD --window 20 --limit 50 --format json
uv run ashare feature read concept_strength --as-of YYYYMMDD --window 20 --limit 50 --format json
uv run ashare mart read dc_index --trade-date YYYYMMDD --format json
```

**能支持**

- 行业/概念强弱排序；
- 市场关注度初筛；
- 题材扩散线索。

**不能支持**

- 公司正宗程度；
- 订单兑现；
- 财务验证。

## 题材成分和候选池发现

**适合回答**

- 某个主题有哪些 A 股相关公司？
- 哪些公司被市场初步认可？

**数据入口**

- `dc_member`
- `ths_member`
- `index_member_all`
- `ci_index_member`
- `leader_validation`
- `elasticity_candidates`

**常用命令**

```bash
uv run ashare feature read leader_validation --as-of YYYYMMDD --window 20 --limit 100 --format json
uv run ashare feature read elasticity_candidates --as-of YYYYMMDD --window 20 --limit 100 --format json
```

**能支持**

- 候选池初筛；
- 龙头和高弹性候选发现；
- 市场认可度线索。

**不能支持**

- 只凭概念成分判定业务暴露；
- 只凭涨幅判定产业兑现。

## 公司业务暴露度验证

**适合回答**

- 公司是否真的处在产业链关键环节？
- 主线相关业务是否有收入、产品、客户、订单或产能证据？

**数据入口**

- `fina_mainbz`
- `a_stock_notice`
- `earnings_forecast`
- `income`
- `balancesheet`
- `cashflow`
- `fina_indicator`
- evidence
- knowledge

**常用命令**

```bash
uv run ashare context build stock TS_CODE --as-of YYYYMMDD
uv run ashare evidence search --company COMPANY --format json
uv run ashare knowledge search --entity COMPANY --format json
```

**能支持**

- 公司产品、客户、订单、产能、主营构成的可追溯验证；
- 风险事件和公告验证；
- 正宗程度分层。

**不能支持**

- 无来源情况下的业务暴露度判断；
- 用市场热度替代公司披露。

## 产业外部证据补充

**适合回答**

- 产业价格、库存、产能、capex、政策、招投标是否支持主线？

**数据入口**

- evidence records
- accepted adapter specs
- source-specific external research supplied by user or Codex

**常用命令**

```bash
uv run ashare evidence search --industry INDUSTRY --topic TOPIC --format json
uv run ashare evidence adapter-candidates --min-records 3
uv run ashare evidence collect --question "QUESTION" --as-of YYYYMMDD
```

**能支持**

- 项目内 mart 覆盖不了的产业事实；
- 高频外部数值证据的 adapter 候选；
- 产业链验证缺口。

**不能支持**

- 覆盖 mart 已有行情、公告、财务事实；
- 无来源的产业判断。

## 知识和产业链关系

**适合回答**

- 公司、产品、客户、产业链节点之间有什么稳定关系？
- 一个主题的慢变量关系是否已沉淀？

**数据入口**

- knowledge current records
- knowledge proposals

**常用命令**

```bash
uv run ashare knowledge search --entity ENTITY --format json
uv run ashare knowledge propose knowledge.json --reason "source checked"
uv run ashare knowledge proposals --format json
```

**能支持**

- 慢变量关系复用；
- 别名和实体消歧；
- 产业链映射的可追溯补充。

**不能支持**

- 当日市场强弱；
- 未经 accept 的事实确认。

## 输出和留痕

**适合回答**

- 本次分析使用了哪些数据？
- 输出是否符合 schema？
- 后续如何复盘？

**数据入口**

- protocols
- runs

**常用命令**

```bash
uv run ashare protocols validate
uv run ashare protocols output-schema market_structure.v1
uv run ashare runs record --question "QUESTION" --as-of YYYYMMDD --context-pack PATH
uv run ashare runs replay runs/RUN_ID
```

**能支持**

- 输出结构校验；
- artifact hash 留痕；
- 分析过程复盘。

**不能支持**

- 新事实生成；
- 替代 mart、feature、evidence 或 knowledge。
