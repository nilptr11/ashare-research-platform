# 产业链研究 Playbook

这是示例路径，不是强制工作流。Codex 应根据用户问题和 `codex/data-map.md` 选择最小必要数据。

## 适用问题

- 某条产业主线是否仍被市场定价？
- A 股哪些公司更正宗？
- 哪些公司只是市场关注或待验证？

## 示例路径

1. 检查数据状态：

```bash
uv run ashare daily status --as-of YYYYMMDD --format json
```

2. 必要时读取主线强度：

```bash
uv run ashare feature read industry_strength --as-of YYYYMMDD --window 20 --limit 50 --format json
uv run ashare feature read concept_strength --as-of YYYYMMDD --window 20 --limit 50 --format json
```

3. 必要时找候选池：

```bash
uv run ashare feature read leader_validation --as-of YYYYMMDD --window 20 --limit 100 --format json
uv run ashare feature read elasticity_candidates --as-of YYYYMMDD --window 20 --limit 100 --format json
```

4. 验证公司暴露度：

```bash
uv run ashare evidence search --company COMPANY --format json
uv run ashare knowledge search --entity COMPANY --format json
```

5. 本地数据不足时，根据 `codex/source-registry.md` 补权威来源。

6. 用户要求结构化产物时，按 `industry_chain_selection.v1` 输出结构化结论。

## 输出状态

- `core_research`
- `elastic_watch`
- `laggard_watch`
- `evidence_needed`
- `excluded`

以上状态是研究优先级，不是交易指令。
