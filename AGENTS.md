# AGENTS

本仓库是个人 skill 备份，只有 Markdown，没有构建、依赖和 CI。不要引入它们。

## 新增 skill

- 新建 `skills/<kebab-case-name>/SKILL.md`，frontmatter 必须有 `name` 与 `description`
- `name` 与目录名一致
- 在 README 的 Skills 表补一行（名称链接、用途、版本）
- 不要修改其他已有 skill

## 修改 skill

- 正文有任何行为变化时，更新 SKILL.md 顶部的 `Version:` 与变更记录
- 保持单文件自包含；需要 `references/` 才拆成目录包
- `SKILL.md` 文件名全大写

## 不要做

- 不要写安装脚本去改 `~/.dsh/skills`，安装方式在 README 里，由人手动执行
- 不要改 `description` 来“优化”触发词，除非明确要求
