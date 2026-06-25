# Project Docs

本目录只放会指导项目使用、维护或 Agent 研究流程的文档。运行时事实源仍以 `data/mart`、`data/features`、`data/evidence`、`data/knowledge`、`data/context_packs` 为准。

## 目录边界

| 目录 | 作用 |
| --- | --- |
| `architecture/` | 系统能力、数据读取顺序、产物边界和质量门说明 |
| `operations/` | 基础数据维护、验收、补数和读取口径 |
| `agent-workflows/` | Agent 研究工作流、输出状态和非交易边界 |
| `vendor/` | 外部供应商或接口资料，例如 Tushare 接口清单 |

## 不放在这里的内容

- 可执行配置放 `config/`。
- Agent prompt 放 `prompts/`。
- 可校验 protocol 和 output schema 放 `src/ashare_research/protocols/`。
- 运行数据和研究留痕放 `data/` 或 `runs/`。
- 过期设计稿、未使用 source map、一次性调研材料不保留。
