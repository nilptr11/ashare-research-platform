# Codex 使用说明

本目录是 Codex 使用本项目的按需参考层。默认入口是根目录 `SKILL.md`，本目录负责说明数据地图、来源注册、推理边界和可选研究辅助材料。

项目本身不运行 Agent，不调用模型 API，也不提供 HTTP 服务。Codex 直接读取本地数据和文档，必要时调用少量 CLI 做检查、抽样、补数、校验或留痕。

## 默认模式

```text
用户问题或假设
  -> 读取 SKILL.md
  -> 读取 data-map，确认本地数据、日期、覆盖和盲区
  -> 直接使用 mart / feature / evidence / knowledge 的相关事实
  -> 数据不足时，根据 source-registry 去权威来源补证据
  -> 按 reasoning-policy 区分事实、推断、假设和缺口
  -> 用户需要结构化产物时，参考 protocol schema
  -> 需要复盘时，runs record 留痕
```

不要把 `capabilities`、`context compose` 或某个 playbook 当成默认工作流。它们只是辅助索引、快照和示例路径。

## 文件说明

| 文件 | 作用 |
| --- | --- |
| `data-map.md` | 本地数据地图：已有数据、数据层级、适用问题、结论边界 |
| `source-registry.md` | 数据不足时的权威来源、fetch 原则和入库方式 |
| `reasoning-policy.md` | Codex 推理边界、来源优先级、降级和禁止事项 |
| `capability-map.md` | 问题到数据能力的映射参考，不是固定流程 |
| `data-access-guide.md` | 维护、抽样、读取和校验命令参考 |
| `playbooks/` | 示例研究路径，仅供参考，不强制执行 |

## 关键边界

- 数据底座优先于现场生成问题型 workflow。
- 本地 mart 是结构化事实源；feature 只做筛查和排序；evidence / knowledge 补足产业和语义事实。
- 本地数据不足时，先找权威来源，再把来源、日期、口径和不确定性写清楚。
- 不输出交易执行指令，不把研究候选池写成买卖建议。
