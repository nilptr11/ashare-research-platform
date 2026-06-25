# Project Docs

本目录只放会指导项目使用、维护或 Agent 研究的文档。Codex 默认入口在根目录 `SKILL.md`，运行时事实源以 `data/mart`、`data/features`、`data/evidence`、`data/knowledge` 为准；`data/context_packs` 只是可选快照。

## 目录边界

| 目录 | 作用 |
| --- | --- |
| `architecture/` | 系统能力、数据读取顺序、产物边界和质量门说明 |
| `operations/` | 基础数据维护、验收、补数和读取口径 |
| `playbooks/` | 示例研究路径，仅供参考，不是强制工作流 |
| `vendor/` | 外部供应商或接口资料，例如 Tushare 接口清单 |
| `refactor/` | 目标架构、重构路线和迁移策略 |

## 不放在这里的内容

- 可执行配置放 `config/`。
- Agent prompt 放 `prompts/`。
- 可校验 protocol 和 output schema 放 `src/ashare_research/protocols/`。
- 运行数据和研究留痕放 `data/` 或 `runs/`。
- 过期设计稿、未使用 source map、一次性调研材料不保留。
