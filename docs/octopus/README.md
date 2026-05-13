# @Octopus_docs 目录说明

> ⚠️ **内容已迁移！** 以下文件的功能已合并到 `docs/` 目录的单一主文档中。

## 迁移状态

| 文件 | 状态 | 迁移目标 |
|------|------|---------|
| `Octopus_Operation_Handbook.md` | ✅ 已合并 | `docs/octopus_user_guide.md`（§9.9）|
| `UI_User_Guide.md` | ✅ 已合并 | `docs/octopus_user_guide.md` |
| `Octopus_Knowledge_Base.md` | ✅ 已合并 | `docs/octopus_knowledge_reference.md` |
| `Output_Parsing_Manual.md` | ✅ 已合并 | `docs/octopus_knowledge_reference.md` |

## 当前文档体系

```
docs/
├── octopus_user_guide.md              ← 主指南（Octopus 使用流程 + 并行化）
├── octopus_knowledge_reference.md     ← 知识参考（语法速查 + 解析代码）
├── openclaw_operating_model.md       ← 编排手册（角色 + 触发 + 排错）
├── development_lessons_20260418.md    ← 开发经验记录
└── harness_reports/                  ← 测试报告（自动生成）

@Octopus_docs/                         ← 纯参考静态资源
├── VisIt_Integration_Guide.md          ← 保留：VisIt 集成专项
├── generated_inputs/                   ← 保留：输入模板参考
├── scripts/                           ← 保留：实用脚本
└── output/                            ← 保留：输出示例
```

## 保留文件说明

| 文件 | 用途 |
|------|------|
| `VisIt_Integration_Guide.md` | VisIt 3D 可视化专项指南，未与主体系合并 |
| `generated_inputs/` | Octopus 公式模式输入模板参考 |
| `scripts/` | 辅助脚本参考 |
| `output/` | 输出文件示例 |

## 新增主文档

### `docs/octopus_user_guide.md`
**Octopus 完整使用指南**（主入口）
- DFT 物理基础、模式选择、网格收敛
- PP Mode / Formula Mode / All-Electron Mode 操作步骤
- TD-DFT 含时演化配置
- **HPC 并行化与 PBS 调度（新增 §9.9）**
- MLIP 增效实施计划

### `docs/octopus_knowledge_reference.md`
**Octopus 知识参考手册**（查阅用）
- 输入文件语法速查（含 Species 格式）
- XC 泛函完整对照表（libxc 字符串）
- 计算模式参考
- 输出解析 Python/TypeScript 代码模板
- 实用程序命令速查

### `docs/openclaw_operating_model.md`
**OpenClaw 操作系统手册**（编排主入口）
- 角色边界与职责
- 触发源与执行总线
- 服务故障排查
- 完成状态记录
