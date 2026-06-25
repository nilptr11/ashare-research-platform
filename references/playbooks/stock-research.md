# 个股研究 Playbook

这是示例路径，不是强制工作流。

## 示例路径

```bash
uv run ashare daily status --as-of YYYYMMDD --format json
uv run ashare mart read daily --trade-date YYYYMMDD --format json
uv run ashare evidence search --company COMPANY --format json
uv run ashare knowledge search --entity COMPANY --format json
```

先直接检查 mart、evidence 和 knowledge，不生成中间快照。

## 输出重点

- 公司基础信息和行情结构；
- 公告、财务、主营构成和风险；
- 产业链关系和业务暴露度证据；
- 数据缺口和后续跟踪。

不得只凭题材、热榜或涨幅判断公司正宗程度。
