# AGENTS

本仓库是个人 skill 备份，以 Markdown 为主；skill 自带脚本放在 `skills/<kebab-case-name>/scripts/`，只用标准库，不引入构建、依赖和 CI。

## 新增 skill

- 新建 `skills/<kebab-case-name>/SKILL.md`，frontmatter 必须有 `name` 与 `description`
- `name` 与目录名一致
- 在 README 的 Skills 表补一行（名称链接、用途、版本）
- 需要脚本时放在 `scripts/`，只用标准库；在 `SKILL.md` 或 `references/` 写明路径与用法
- 不要修改其他已有 skill

## 修改 skill

- 正文或 `scripts/` 有行为变化时，更新 SKILL.md 顶部的 `Version:` 与变更记录
- 核心规范保持在 `SKILL.md`；用法说明放 `references/`，可执行脚本放 `scripts/`
- `SKILL.md` 文件名全大写

## 不要做

- 不要写安装脚本去改 `~/.dsh/skills`，安装方式在 README 里，由人手动执行
- 不要改 `description` 来“优化”触发词，除非明确要求
- 禁止修改本文件
