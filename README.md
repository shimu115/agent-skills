# agent-skills
个人自用的 skills，仅按本人需求编写。
纯 Markdown，无构建、无依赖。每个 skill 一个目录，入口为 `SKILL.md`。
## Skills
| Skill | 用途 | 版本 |
|---|---|---|
| [`media-scraping`](skills/media-scraping/SKILL.md) | 媒体库目录与文件重命名规范，硬链接入库，以 Jellyfin + TMDB 为准 | 1.5 |
## 安装
把 skill 目录复制到 agent 扫描的位置即可，不需要重启。
```sh
# clone 仓库
git clone https://github.com/shimu115/agent-skills.git
cd agent-skills
# DSH（用户级）
mkdir -p ~/.dsh/skills
cp -r skills/media-scraping ~/.dsh/skills/
# Claude Code 等其他 agent（按各自的约定目录）
mkdir -p ~/.claude/skills
cp -r skills/media-scraping ~/.claude/skills/
```
或者用软链，`git pull` 之后立即生效：
```sh
# 只用软连接一次，后续直接 git pull 即可更新
ln -sfn "$PWD/skills/media-scraping" ~/.dsh/skills/media-scraping

```
只想让某个项目用到时，放到 `<项目根>/.dsh/skills/` 或 `<项目根>/.agents/skills/`。
DSH 默认扫描的 skill 目录：
| 作用域 | 路径 |
|---|---|
| 用户级 | `~/.dsh/skills`、`~/.agents/skills` |
| 项目级 | `<项目根>/.dsh/skills`、`<项目根>/.agents/skills` |
## media-scraping
整理、重命名、入库媒体库文件时使用。统一 `Movies` / `TV Shows` / `Anime` / `Anime Movies` 的目录结构，元数据以 Jellyfin 已刮削内容为最高优先级、其次是 TMDB（动漫可用 Bangumi 补充），通过**硬链接**入库，原始文件一律不动。
命名格式：
```text
剧集：英文标题.年份.SxxExx.分辨率.视频编码_音频编码-发布组.扩展名
电影：英文标题.年份.分辨率.视频编码_音频编码-发布组.扩展名
弹幕：<视频完整主名>.danmu.ass / .danmu.xml
```
```text
Anime/
└── 乱马½ (2024)
    └── Season 1
        ├── Ranma½.2024.S01E01.1080p.x264_FLAC-SubsPlease.mkv
        ├── Ranma½.2024.S01E01.1080p.x264_FLAC-SubsPlease.zh-Hans.ass
        └── Ranma½.2024.S01E01.1080p.x264_FLAC-SubsPlease.danmu.ass
```
关键约束：
- 目录名用 TMDB 标题，中文（zh-CN）优先；文件名中的 `${title}` 用 TMDB 英文标题
- 同一 TMDB collection 的多部电影归入 `<系列名>（系列）/`
- 只处理增量，已入库内容冻结（不重命名、不重建链接、不重新刮削）
- 无法唯一确定时输出 `Needs Manual Review` 并停止，不猜测
- 禁止复制、移动、删除原始文件；硬链接失败（含跨文件系统）即报错停止，不自动降级为 copy/move
前置条件：`ffprobe` 可用；下载目录与媒体库位于同一文件系统（硬链接前提）；可访问 Jellyfin 与 TMDB。
## 开发约定
仓库自身的维护约定见 [AGENTS.md](AGENTS.md)。
