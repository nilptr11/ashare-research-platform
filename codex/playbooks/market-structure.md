# 市场结构 Playbook

这是示例路径，不是强制工作流。

## 示例路径

```bash
uv run ashare daily status --as-of YYYYMMDD --format json
uv run ashare feature meta market_strength --as-of YYYYMMDD --window 20
uv run ashare feature read market_strength --as-of YYYYMMDD --window 20 --format json
uv run ashare feature read limit_sentiment --as-of YYYYMMDD --window 20 --format json
```

已有 market context 快照时可以读取；没有快照时不要为了套路径强行生成。

## 输出重点

- 指数和市场强弱；
- 行业/概念是否有持续性；
- 涨跌停和短线情绪；
- 数据缺口和降级影响。

不得输出交易执行指令。
