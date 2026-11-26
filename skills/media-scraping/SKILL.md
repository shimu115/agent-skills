---
name: media-scraping
description: 整理、重命名、入库媒体库文件时使用。统一 Movies / TV Shows / Anime / Anime Movies 目录结构，剧集文件采用「英文标题.年份.SxxExx.分辨率.视频编码_音频编码-发布组.扩展名」、电影文件采用「英文标题.年份.分辨率.视频编码_音频编码-发布组.扩展名」的发布组风格命名（电影不含 SxxExx；同一 TMDB collection 的多部电影归入「系列名（系列）」文件夹；弹幕文件按「视频完整主名.danmu.ass / .danmu.xml」命名），以 Jellyfin 已刮削元数据和 TMDB 为标准（目录名中文标题优先 zh-CN），通过硬链接 hard link 入库，禁止复制、移动、删除原始文件。适用于 Jellyfin 刮削、动漫季集编号整理、字幕与海报重命名、Bangumi 插件兼容等场景。
---

# Media Scraping Specification

Version: 1.10

> 变更记录：1.10（2026-11-26）数据库层改为 SQLAlchemy Core，`migrate` 支持 SQLite / MySQL / PostgreSQL；新增 `scripts/database/`（连接、表结构、仓储、迁移）与 `scripts/database/requirements.txt`，后者是本 skill 唯一的依赖例外，仅 `migrate` 需要；Markdown 日志格式与迁移兼容性不变。1.9（2026-11-26）日志脚本改为随 skill 安装的 `scripts/scrape_log.py`，直接执行，不再从 `references/scrape-log-tool.md` 提取；参考文档只保留用法。1.8（2026-11-26）新增 `references/scrape-log-tool.md`：`init` / `add` / `finish` / `validate` 按模板生成日志，`migrate` 将 v1 md 迁移到 SQLite（生成 SQL、事务导入、行数校验、归档、可选原子更新 `config.json`）；`finished_at` 运行中允许为 `null`，空 `note` 迁移为 `NULL`。1.7（2026-11-26）新增标准 Markdown 日志模板 `references/scrape-log-template.md`（YAML frontmatter + 固定 Records 表），md→SQL 只迁移符合模板的日志；旧格式日志不自动迁移，需先归一化。1.6（2026-11-26）新增固定工作区与首次运行设置（`config.json`）、刮削日志存储（Markdown / 数据库，默认 SQLite）、md 日志迁移为 SQL、入库与不入库两种流程（`tmp/` 中转、`backup/` 硬链接备份）。规范内容以本文为准，修改规范时同步更新此处。

---

# 1. Purpose

本文档用于规范 Agent（Claude Code、Codex、Gemini CLI 等）整理媒体库的行为。

目标：

- 统一整个媒体库目录结构
- 保证 Jellyfin 能够稳定刮削
- 保证与 TMDB 数据一致
- 兼容 Bangumi 插件
- 最大程度降低误识别风险

Agent 必须严格遵循本文档，不允许自行发挥。

---

# 2. Scope

本规范适用于：

- Movies
- TV Shows
- Anime
- Anime Movies
- Specials
- Subtitles
- Danmaku
- Artwork

---

# 3. General Principles

## 3.1 Naming Standard

所有目录及文件命名均以 TMDB 为标准。

目录名使用 TMDB 标题（中文标题优先，见第 21 节「中文标题规则」）。

剧集与电影文件名中的 `${title}` 字段例外：使用 TMDB 英文标题（en-US），字段规则见第 12 节。

不得以：

- 豆瓣
- IMDb
- Bangumi
- AniDB
- 文件名

作为命名依据。

---

## 3.2 Metadata Priority

媒体信息优先级：

1. Jellyfin 已刮削元数据（最高优先级）
2. TMDB
3. Bangumi（仅补充动漫元数据）
4. AniDB（可选）

发生冲突时：

始终使用优先级更高的数据。

---

## 3.3 No Guessing

Agent 不允许：

- 猜测番剧名称
- 猜测年份
- 猜测 Season
- 猜测 Episode

若无法唯一确定：

停止处理。

输出：

```

Needs Manual Review

```

---

# 4. Directory Layout

```
Media/
├── Movies/
├── Anime Movies/
├── TV Shows/
├── Anime/
├── Documentaries/
└── Music/
```

Agent 不允许创建新的媒体分类。

入库模式下，该结构位于 `config.json` 的 `jellyfin_library` 根目录；不入库模式下，该结构位于工作区根目录（第 23 节）。

---

# 5. Movie Rules

目录：

```
Movie Title (Year)
```

视频：

```
${title}.${year}.${resolution}.${videoCodec}_${audioCodec}-${releaseGroup}.${extension}
```

其中 `${title}` 使用 TMDB 英文标题，空格等转 `.`。字段规则见第 12 节。

例如：

```
Movies/
└── Interstellar (2014)
    ├── Interstellar.2014.2160p.x265_FLAC-SubsPlease.mkv
    ├── poster.jpg
    └── fanart.jpg
```

## 5.1 Movie Series / Franchise Grouping

同一 TMDB collection（`belongs_to_collection.id` 相同）的电影（适用于 Movies / Anime Movies 等电影分类），若本次整理包含 ≥2 部，或目标分类目录下已存在对应系列文件夹，则归入同一个系列文件夹。系列文件夹直接放在分类目录下：

```
Movies/
└── 命运之夜——天之杯（系列）
    ├── 命运之夜——天之杯Ⅰ：恶兆之花 (2017)/
    │   └── Fate.stay.night.Heaven's.Feel.I.presage.flower.2017.1080p.x265_FLAC-VCB-Studio.mkv
    ├── 命运之夜——天之杯Ⅱ：迷失之蝶 (2019)/
    │   └── Fate.stay.night.Heaven's.Feel.II.lost.butterfly.2019.1080p.x265_FLAC-VCB-Studio.mkv
    └── 命运之夜——天之杯Ⅲ：春之歌 (2020)/
        └── Fate.stay.night.Heaven's.Feel.III.spring.song.2020.1080p.x265_FLAC-VCB-Studio.mkv
```

规则：

- 系列文件夹名 = TMDB collection 的 zh-CN 名称 + `（系列）`；无 zh-CN 名称时按第 21 节「中文标题规则」回退。名称已含 `（系列）` 时不重复追加；Windows 非法字符用全角符号替代（如 `:`→`：`、`/`→`／`）。
- 若分类目录下已存在同一 collection 的系列文件夹（可由其中的电影 NFO/TMDB ID 确认），沿用现有文件夹名，不新建重复文件夹；名称与 TMDB 当前名称不一致时输出提示，不擅自重命名。
- 系列文件夹只是容器：不得在其中放置视频、字幕、图片或 nfo；所有媒体文件仍在各自的电影文件夹内。
- 系列文件夹内的每部电影仍按第 5 节的 `Movie Title (Year)/` 与第 12.4 节的文件名格式。
- 本次整理只有 1 部同 collection 电影且没有既有系列文件夹时，保持散放，不创建系列文件夹；若系列文件夹已存在，则放入该系列文件夹。
- 已入库的散放影片不自动移入系列文件夹。需要把既有散放影片与新片一起归组时，输出建议，待用户显式要求后按第 22.4 节修正存量。
- 无法从 TMDB collection 唯一确定系列归属时，停止并输出 `Needs Manual Review`；用户显式指定系列名称的，以用户指定为准。
- 系列文件夹只负责文件组织；Jellyfin 的合集展示仍由 TMDB collection 元数据生成（媒体库的合集 / Group movies into collections 设置），系列文件夹本身不创建 Jellyfin Collection。

---

# 6. TV Rules

目录：

```
Series Title (Year)
```

Season：

```
Season 1
Season 2
```

Episode：

```
${title}.${year}.S${season}E${episode}.${resolution}.${videoCodec}_${audioCodec}-${releaseGroup}.${extension}
```

其中 `${title}` 使用 TMDB 英文标题，空格转 `.`。完整字段规则见第 12 节。

例如：

```
Breaking Bad (2008)
└── Season 1
    ├── Breaking.Bad.2008.S01E01.1080p.x265_FLAC-SubsPlease.mkv
```

---

# 7. Anime Rules

动漫按照 TMDB TV 数据整理。

例如：

```
Anime/
└── 乱马½ (2024)
    └── Season 1
        ├── Ranma½.2024.S01E01.1080p.x264_FLAC-SubsPlease.mkv
```

不得使用：

```
Ranma

乱马

Ranma 2024

【喵萌奶茶屋】
```

作为目录名。

---

# 8. Specials

Specials：

```
Season 0
```

剧集：

```
S00E01
```

例如：

```
Season 0
└── Ranma½.2024.S00E01.1080p.x264_FLAC-SubsPlease.mkv
```

---

# 9. Subtitle Rules

普通字幕必须与视频同名：字幕文件 = 视频文件完整主名 + 语言后缀。

弹幕文件使用 `.danmu` 标记，不按语言后缀处理，见第 9.1 节。

例如：

```
Fate.Zero.2011.S01E01.1080p.x265_FLAC-VCB-Studio.mkv

Fate.Zero.2011.S01E01.1080p.x265_FLAC-VCB-Studio.zh.ass

Fate.Zero.2011.S01E01.1080p.x265_FLAC-VCB-Studio.zh-Hans.ass

Fate.Zero.2011.S01E01.1080p.x265_FLAC-VCB-Studio.en.ass
```

Agent 不允许修改字幕内容。

## 9.1 Danmaku Rules

弹幕文件必须与对应视频使用相同的完整主名，并在扩展名前加 `.danmu`：

```
<视频完整主名>.danmu.<extension>
```

例如：

```
视频：Lucky.Star.2007.S01E01.1080p.x265_FLAC.mkv
字幕：Lucky.Star.2007.S01E01.1080p.x265_FLAC.zh-Hans.ass
弹幕：Lucky.Star.2007.S01E01.1080p.x265_FLAC.danmu.ass
      Lucky.Star.2007.S01E01.1080p.x265_FLAC.danmu.xml
```

电影同理（无 SxxExx）：

```
Interstellar.2014.2160p.x265_FLAC-SubsPlease.danmu.ass
Interstellar.2014.2160p.x265_FLAC-SubsPlease.danmu.xml
```

识别规则：

- 源文件名（不含扩展名）中带独立 `dm`、`danmu`、`danmaku`、`弹幕` 标记的 `.ass`/`.ssa`/`.xml` 文件，按弹幕处理。标记可与语言后缀相连，如 `dm-chs`、`dm-cht`、`danmu.chs`；识别时不区分大小写。
- `dm`/`danmu` 标记优先于普通字幕语言判断：`... .dm-chs.ass` 必须输出 `... .danmu.ass`，不得输出 `... .zh-Hans.ass`。
- 例如源文件 `Lucky Star. TV (2007) 01; BD_1080P_h265_flac.dm-chs.ass` / `.dm-chs.xml` 匹配到 `Lucky.Star.2007.S01E01.1080p.x265_FLAC.mkv` 后，输出 `Lucky.Star.2007.S01E01.1080p.x265_FLAC.danmu.ass` / `.danmu.xml`。
- `.xml` 仅当文件名带上述标记，或内容确为弹幕 XML（如 Bilibili `<i><d p="...">` 结构）时按弹幕处理；普通 NFO/元数据 XML 不得改名为 `.danmu.xml`。
- 输出扩展名保持原样并小写：`.ass`→`.danmu.ass`、`.xml`→`.danmu.xml`、`.ssa`→`.danmu.ssa`；不得在 XML/ASS 之间转换，不得合并、修改弹幕内容。
- 弹幕与视频放在同一目录，父目录结构与视频一致（含 Season、电影系列文件夹）。
- 同一视频的 `.danmu.ass` 与 `.danmu.xml` 可同时存在；这是两种格式，不是重复文件。
- 多个源文件映射到同一目标名（如同时有 `dm-chs` 和 `dm-cht`）时，不得覆盖：内容相同（或同一 inode）则保留一个，内容不同则停止并输出 `Needs Manual Review`，不得自行添加语言后缀。
- 其他格式（如 `.json`）如确认是弹幕，也按 `<视频完整主名>.danmu.<ext>` 命名并保留扩展名；无法确认时输出 `Needs Manual Review`。
- 无法唯一匹配视频的弹幕留在原处并记录（不入库模式同时保留在 `backup/<run_id>/`，入库模式保留在 `tmp/<run_id>/`），不得按集号猜测。
- 弹幕文件与视频一样通过硬链接入库（第 21.1 节），不得复制、移动或删除原始文件。

Jellyfin 说明：`.danmu.ass` 可能被 Jellyfin 的外挂字幕解析器当作字幕流（`danmu` 不是标准语言代码，通常会作为流标题），不影响视频匹配；`.danmu.xml` 不是 Jellyfin 原生字幕格式，需由支持弹幕的插件/客户端读取。两者都不要改名成普通字幕。

---

# 10. Artwork Rules

图片命名：

```
poster.jpg

fanart.jpg

banner.jpg

folder.jpg

clearlogo.png
```

若已有图片：

不得覆盖。

---

# 11. Multi-Version Rules

允许：

```
Movie (2024)

Movie (2024) - IMAX

Movie (2024) - Director's Cut
```

不得删除任何版本。

Jellyfin 通过「文件名前缀与父目录名逐字符一致」识别多版本电影。因此**多版本电影**仍使用 `Movie Title (Year) - Version.ext`（此为例外）；**单版本电影**按第 12.4 节的新格式命名。

---

# 12. Video Filename Format

## 12.1 Template

TV Shows / Anime / Specials 的每集视频文件名必须使用：

```
${title}.${year}.S${season}E${episode}.${resolution}.${videoCodec}_${audioCodec}-${releaseGroup}.${extension}
```

字段以 `.` 连接；`${videoCodec}` 与 `${audioCodec}` 之间用 `_`；`${releaseGroup}` 前用 `-`。

示例：

源文件：

```
[VCB-Studio] Fate Zero [01][Ma10p_1080p][x265_flac].mkv
```

重命名为：

```
Fate.Zero.2011.S01E01.1080p.x265_FLAC-VCB-Studio.mkv
```

`${title}` 使用 TMDB 英文标题（en-US）。若 TMDB 没有英文标题且原始标题不是拉丁文字，输出 `Needs Manual Review`，不得音译或猜测。

## 12.2 Field Rules

| 字段 | 来源 | 规则 |
| --- | --- | --- |
| `${title}` | TMDB 英文标题（TV 用 en-US `name`，电影用 en-US `title`） | 空格转 `.`；斜杠、冒号、分号、逗号转 `.`；移除 Windows/Jellyfin 保留字符（尖括号、引号、反斜杠、竖线、问号、星号）；合并连续 `.`；去掉首尾 `.`。保留拉丁字母、数字、连字符、撇号等合法字符 |
| `${year}` | TMDB 年份（TV 用 `first_air_date`，电影用 `release_date`） | 4 位数字；无法确定时输出 `Needs Manual Review` |
| `${season}` | TMDB Season 编号（仅剧集） | 至少补零到 2 位：`S01`、`S10` |
| `${episode}` | TMDB Episode 编号（仅剧集） | 至少补零到 2 位：`E01`、`E100`；季内/全程连续编号以 TMDB 实测为准 |
| `${resolution}` | 源文件名标签 + ffprobe 校验 | 优先采用源文件名中的 `2160p`/`1080p`/`720p`/`576p`/`480p` 标签，并用 ffprobe 宽高校验；无标签时按 ffprobe 判定（取宽、高维度中的较高档位）：宽≥3800 或高≥2000→`2160p`，高≥1300→`1440p`，宽≥1900 或高≥1000→`1080p`，宽≥1200 或高≥700→`720p`，高≥560→`576p`，高≥520→`540p`，高≥460→`480p`，其余→`${height}p`。宽银幕（如 1920×800）判为 `1080p`。源标签与实测明显冲突时输出 `Needs Manual Review` |
| `${videoCodec}` | ffprobe + 源文件名 | 以 ffprobe `codec_name` 判定编码族：`h264`→`x264`、`hevc`→`x265`、`av1`→`AV1`、`vp9`→`VP9`；源文件名显式给出 `x264`/`x265` 时沿用其写法。两者冲突时停止并输出 `Needs Manual Review` |
| `${audioCodec}` | ffprobe 默认音轨 | 规范为大写：`AAC`、`FLAC`、`DTS`、`AC3`、`EAC3`、`TrueHD`、`Opus`、`MP3` 等。多音轨时只取默认音轨（无默认标记则取第一条），不并列多个编码 |
| `${releaseGroup}` | 源文件名 | 优先取开头 `[发布组]`；否则取扩展名前最后一个 `-发布组` 标记。空格转 `.`。无法唯一确定时省略该字段及前面的 `-`，不得臆造 |
| `${extension}` | 源文件扩展名 | 小写，保持容器不变；不得转码或重封装 |

若 ffprobe 无法读取视频流或音频流信息，停止处理并输出 `ERROR`，不得用源文件名标签代替实测值。

## 12.3 Forbidden Content

除上述字段外，文件名不得包含：

- 发布媒介：`BluRay`、`BDRip`、`WEB-DL`、`WEBRip`、`HDTV`
- 动态范围：`HDR`、`SDR`、`HDR10`、`DV`
- 位深：`10bit`、`Ma10p`、`8bit`
- 音频布局：`5.1`、`7.1`、`Atmos`
- 语言/字幕标记：`内封字幕`、`双语`、`国语`、`CHS`、`CHT`
- 校验/体积：CRC、文件大小、`[xxxx MB]`
- 空格、保留字符（尖括号、冒号、引号、斜杠、反斜杠、竖线、问号、星号）、连续点、首尾点
- 除 `releaseGroup` 以外的来源/发布组标记

## 12.4 Movies

电影不使用 SxxExx 字段，文件名格式为：

```
${title}.${year}.${resolution}.${videoCodec}_${audioCodec}-${releaseGroup}.${extension}
```

示例：

源文件：

```
[SubsPlease] Interstellar (2014) [2160p][x265_flac].mkv
```

重命名为：

```
Interstellar.2014.2160p.x265_FLAC-SubsPlease.mkv
```

电影的 `${title}` 取 TMDB 英文标题（en-US `title`），`${year}` 取 `release_date` 年份；其余字段规则同 §12.2。

**多版本电影例外**：Jellyfin 要求多版本文件的文件名前缀与父目录名逐字符一致，因此同一电影存在 IMAX/导演剪辑版等多个版本时，仍使用第 11 节的 `Movie Title (Year) - Version.ext` 命名，否则 Jellyfin 会把它们识别为不同电影。单版本电影不受影响。

电影位于系列文件夹内时（第 5.1 节），父目录仍是各自的 `Movie Title (Year)/`，文件名格式不变。

## 12.5 Jellyfin Compatibility

Jellyfin 以 `SxxExx` 识别剧集；`SxxExx` 之后的 `${resolution}.${videoCodec}_${audioCodec}-${releaseGroup}` 会作为附加标签/版本信息处理，不影响剧集匹配。Jellyfin 以「标题 + 年份」识别电影，`${year}` 之后的字段同样不影响电影匹配。外部字幕必须复用完整的视频文件主名，语言后缀追加在最后。

弹幕文件 `.danmu.ass` / `.danmu.xml` 不影响视频匹配：`.danmu.ass` 可能作为外挂字幕流出现（`danmu` 不是标准语言代码，通常作为流标题）；`.danmu.xml` 不是 Jellyfin 原生字幕格式，需由弹幕插件/客户端读取。详见第 9.1 节。

多版本电影是唯一例外：Jellyfin 要求文件名前缀与父目录名逐字符一致，须按第 11 节处理。

本格式仅适用于新入库或显式要求修正存量的文件；已入库文件按第 22 节冻结。

---

# 13. Rename Workflow

每个媒体必须按以下步骤处理：

Step 0

读取工作区 `config.json`；首次运行按第 23.2 节完成设置。日志存储方式与入库模式以配置为准。

Step 1

识别媒体类型。

Step 2

查询 Jellyfin。

若 Jellyfin 已识别：

直接采用 Jellyfin 信息。

Step 3

若 Jellyfin 未识别：

查询 TMDB。

同时获取：

- TMDB 英文标题（en-US，用于文件名的 `${title}`）
- 年份
- Season / Episode 编号（电影不需要）

Step 4

若 TMDB 未识别：

对于动漫：

查询 Bangumi。

Step 5

使用 ffprobe 读取：

- 分辨率
- 视频编码
- 默认音轨编码

从源文件名识别发布组。

按第 12 节模板生成目标文件名。

Step 6

若仍无法唯一确定：

加入：

```
Needs Manual Review
```

不得继续。

---

# 14. Rename Rules

允许：

- 创建目录
- 创建 Season
- 重命名
- 移动文件
- 移动字幕
- 移动弹幕
- 移动图片

禁止：

- 删除视频
- 删除字幕
- 删除弹幕
- 删除图片
- 转码
- 修改编码
- 修改字幕
- 修改弹幕 / 转换弹幕格式
- 删除 NFO

---

# 15. Validation Rules

整理完成后检查：

✓ 目录符合规范

✓ Season 正确

✓ Episode 正确

✓ 剧集文件名符合第 12.1 节模板（英文标题、年份、SxxExx、分辨率、编码、发布组顺序正确）

✓ 电影文件名符合第 12.4 节模板（英文标题、年份、分辨率、编码、发布组顺序正确，无 SxxExx）

✓ 电影系列文件夹层级正确（`<系列名>（系列）/` 下为各电影文件夹，系列文件夹内无媒体文件）

✓ Jellyfin 能从剧集文件名解析出 SxxExx

✓ 字幕同名

✓ 弹幕文件按第 9.1 节命名（视频完整主名 + `.danmu.ass` / `.danmu.xml`）

✓ 图片命名正确

✓ 文件未丢失

✓ 文件数量一致

✓ 本次运行日志已按模板写入 `doc/<run_id>.md` 或数据库

✓ 不入库模式下 `backup/<run_id>/` 的备份硬链接已创建

✓ 入库模式下 tmp 中的硬链接已移入媒体库，或剩余文件已记录

若失败：

停止处理。

---

# 16. Logging

Agent 必须输出：

```
Rename:

Old:

[VCB-Studio] Fate Zero [01][Ma10p_1080p][x265_flac].mkv

↓

New:

Anime/Fate Zero (2011)/Season 1/Fate.Zero.2011.S01E01.1080p.x265_FLAC-VCB-Studio.mkv
```

所有修改均需记录，并写入持久化日志：Markdown 文档或数据库。

日志存储方式由 `config.json` 的 `log_storage` 决定，首次运行时询问（16.1），之后不再重复询问。

## 16.1 Log Storage Selection

首次运行（`config.json` 不存在或缺少 `log_storage`）时，Agent 必须询问日志存储方式：

```
首次运行请选择日志存储方式：

1. Markdown 文档：日志写入 doc/ 目录，每次运行一个 .md 文件
2. 数据库：默认 SQLite，也可以使用其他数据库

请选择 1 或 2。
```

- 选择 Markdown：`log_storage` 写为 `markdown`。
- 选择数据库：继续询问数据库类型。
  - 用户明确指出数据库类型时，使用该类型。
  - 用户未指定（回答“数据库”“随便”等）：默认 SQLite。
  - SQLite 为独立数据库文件，固定存放在 `data/scraping-logs.db`（`data/` 不存在时创建），配置写为 `{"type": "sqlite", "path": "data/scraping-logs.db"}`。
  - MySQL / PostgreSQL：询问 host、port、database、user；数据库本身必须已存在，脚本只建表、不建数据库。密码不得写入 `config.json`，只从 `password_env` 指定的环境变量读取（省略时使用 `MEDIA_SCRAPING_DB_PASSWORD`）；未设置时提示用户先设置该环境变量，不得把密码写入日志或 SQL。
  - 数据库驱动由 `scripts/database/requirements.txt` 提供，仅 `migrate` 需要安装；Markdown 日志与 `init` / `add` / `finish` / `validate` 不依赖它。
- 询问完成后写入 `config.json`（第 23.2 节），本次及后续运行均按此配置记录日志。用户未回答时停止，不得开始刮削。
- 用户显式要求修改存储方式时，按 16.4 迁移；未明确要求时不得切换。

兼容旧工作区：`config.json` 不存在或缺少 `log_storage`，但 `doc/` 下存在 `archive/` 之外的 `.md` 文件时，视为 Markdown 日志模式，补写 `config.json`（`log_storage: "markdown"`），不再询问日志存储方式；仅补问工作区与入库设置。若 `data/scraping-logs.db` 已存在，则视为 SQLite 日志模式，按同样方式补写配置。两者同时存在时停止，要求用户确认使用哪一种，不得自行选择。

日志写入失败（磁盘满、权限不足、数据库连接失败等）时停止处理并输出：

```
ERROR:
Failed to write scraping log.
```

不得在无日志的情况下继续刮削。

## 16.2 Markdown Log Format

Markdown 日志每次运行一个文件，必须严格使用 `references/scrape-log-template.md` 的结构：

```
doc/<run_id>.md
```

`doc/` 不存在时创建。`<run_id>` 为本次运行开始时间，格式 `YYYYMMDD-HHmmss`，例如 `20261126-153000`。

日志优先由本 skill 的 `scripts/scrape_log.py` 生成（用法见 `references/scrape-log-tool.md`）：

- 脚本随 skill 安装；按 skill 加载时给出的 base directory 或安装位置直接执行，不要复制到工作区。
- 运行开始执行 `init`，每个文件操作执行 `add`，结束执行 `finish`；迁移前用 `validate` 校验。
- 脚本需要 Python 3.8+；`init` / `add` / `finish` / `validate` 仅用标准库，`migrate` 需要 SQLAlchemy 与目标数据库驱动（安装方式见 `references/scrape-log-tool.md`）。脚本缺失或 Python 不可用时按模板手写，并在结束前用 `validate` 校验（可在其他机器执行）。
- `init` 不覆盖已有日志；`add` / `finish` 原子写入；`finish` 同步 frontmatter 与 `## Summary`。

机器迁移只读取两部分：YAML frontmatter 与 `## Records` 表格。其余章节可自由书写，迁移时忽略。frontmatter 键名、Records 表头、列顺序和取值集合不得修改：

```markdown
---
log_schema: 'media-scraping-log/v1'
run_id: '20261126-153000'
started_at: '2026-11-26 15:30:00'
finished_at: '2026-11-26 15:32:10'
workspace: 'F:\MediaWork'
mode: 'in_place'
library: null
summary_added: 1
summary_skipped: 0
summary_needs_review: 1
summary_errors: 0
---

# Scrape Log: 20261126-153000

## Records

| seq | action | media_type | status | source_path | target_path | note |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | hardlink | tv | done | `D:\Downloads\Fate Zero\[VCB-Studio] Fate Zero [01][Ma10p_1080p][x265_flac].mkv` | `Anime/Fate Zero (2011)/Season 1/Fate.Zero.2011.S01E01.1080p.x265_FLAC-VCB-Studio.mkv` | |
| 2 | backup | tv | done | `D:\Downloads\Fate Zero\[VCB-Studio] Fate Zero [01][Ma10p_1080p][x265_flac].mkv` | `backup/20261126-153000/Fate Zero/[VCB-Studio] Fate Zero [01][Ma10p_1080p][x265_flac].mkv` | |
| 3 | review | tv | needs_review | `D:\Downloads\Fate Zero\[VCB-Studio] Fate Zero [SP].mkv` | `-` | 无对应 TMDB 剧集 |
```

规则：

- frontmatter 为纯 `key: value`，不嵌套。字符串值统一用单引号包裹，值内的 `'` 写成 `''`；`library` 为 `null` 时不加引号，`summary_*` 为非负整数。
- 必填键：`log_schema`、`run_id`、`started_at`、`finished_at`、`workspace`、`mode`、`library`、`summary_added`、`summary_skipped`、`summary_needs_review`、`summary_errors`。
- `finished_at` 在运行中写 `null`，`finish` 后写 `YYYY-MM-DD HH:MM:SS`；md→数据库迁移只接受非 `null`。
- 文件名 `<run_id>.md` 必须与 frontmatter 的 `run_id` 一致，且符合 `YYYYMMDD-HHmmss`；不一致时停止并输出 `Needs Manual Review`。
- 模板结构发生不兼容变化时，必须把 `log_schema` 升为 `media-scraping-log/v2`，不得在 v1 下改字段或列。
- `mode` 取值：`in_place`、`ingest`。`library` 在入库模式填媒体库绝对路径，否则为 `null`。
- `workspace`、`mode`、`library` 必须与本次运行使用的 `config.json` 一致。
- `summary_*` 与 `## Summary` 均按文件条目计数，不按操作条数计数；迁移以 frontmatter 为准，两者必须一致。
- `seq` 为正整数，从 1 开始连续递增，不得重复。
- `action` 取值：`rename`（原地重命名）、`hardlink`（创建硬链接）、`move`（tmp 中的硬链接移入媒体库）、`backup`（创建备份硬链接）、`skip`（未修改）、`review`（需人工确认）、`error`。
- `media_type` 取值：`movie`、`tv`、`anime`、`anime_movie`、`special`、`subtitle`、`danmaku`、`artwork`、`metadata`、`music`、`other`；无法确定时用 `other`。
- `status` 取值：`done`、`skipped`、`needs_review`、`error`。
- `source_path` / `target_path` 必须用反引号包裹；没有对应路径时写 `-`。路径优先记录相对工作区根目录或媒体库根目录的路径；不在两者之内时记录绝对路径。
- `note` 为单行纯文本，空值留空；单元格内的 `|` 写成 `\|`，换行写成空格。
- 文件中只能出现一个 `## Records` 标题；解析时只认行首的 `## Records`（前后可有空行），忽略正文或引用块中的同名文本。`## Records` 标题之后必须紧跟表头，不得插入其他内容；表格之后可以追加 `## Summary`、`## Notes` 等人类可读章节，迁移在下一个行首 `## ` 标题处停止解析。
- 需要人工确认或出错的条目同样写入 Records，不得只输出到终端。
- 终端输出仍可使用本文开头的 `Rename: Old → New` 块；持久化日志必须使用上述固定结构。
- 路径或备注无法满足表格语法（含反引号、换行等）时，停止并输出 `Needs Manual Review`，不得写出格式错误的日志。

## 16.3 Database Log Format

数据库模式下，每次运行写入一条 `scrape_runs`，每个文件操作写入一条 `scrape_items`。表结构由 `scripts/database/models.py` 用 SQLAlchemy Core 定义，SQLite / MySQL / PostgreSQL 共用同一份列、约束与索引。

SQLite 表结构：

```sql
CREATE TABLE IF NOT EXISTS scrape_runs (
    run_id                 TEXT PRIMARY KEY,
    started_at             TEXT NOT NULL,
    finished_at            TEXT,
    workspace              TEXT NOT NULL,
    mode                   TEXT NOT NULL,   -- in_place | ingest
    library_path           TEXT,
    summary_added          INTEGER NOT NULL DEFAULT 0,
    summary_skipped        INTEGER NOT NULL DEFAULT 0,
    summary_needs_review   INTEGER NOT NULL DEFAULT 0,
    summary_errors         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scrape_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    action       TEXT NOT NULL,
    media_type   TEXT,
    source_path  TEXT,
    target_path  TEXT,
    status       TEXT NOT NULL,
    note         TEXT,
    created_at   TEXT NOT NULL,
    UNIQUE (run_id, seq),
    FOREIGN KEY (run_id) REFERENCES scrape_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_scrape_items_run_id ON scrape_items(run_id);
```

- 非 SQLite 数据库按目标方言生成等价 DDL；字段含义不变。类型映射：SQLite 沿用上表的 `TEXT`；MySQL / PostgreSQL 的 `run_id`、`started_at`、`finished_at`、`mode`、`action`、`media_type`、`status` 使用 `VARCHAR`（短键 64、时间 19），路径、备注与工作区使用 `TEXT`。
- MySQL 使用 InnoDB / `utf8mb4`；MySQL 不支持 `CREATE INDEX IF NOT EXISTS`，迁移 SQL 中的索引按普通 `CREATE INDEX` 生成。
- 建表使用 `CREATE TABLE IF NOT EXISTS` 语义，只创建缺失的表及其索引，不重建或修改已有表。
- `seq` 为本次运行内的记录序号，从 1 开始递增。
- 写入使用事务；失败时回滚记录并输出 `ERROR`，不得只写入部分记录。建表在导入事务之前执行，失败时表可能保留（MySQL DDL 自动提交，SQLite / PostgreSQL 也不保证回滚 DDL），但不会留下部分记录。
- 正常运行时不得删除或重建已有表。
- 迁移或手工执行用的 SQL 文件存放在 `data/migrations/`。

## 16.4 Switching Log Storage

仅当用户显式要求修改日志存储方式时执行，例如“日志改成数据库”“日志改回 md”。

切换前输出迁移计划，等待用户确认。迁移失败时保持原存储方式不变，不得删除原始日志。

### Markdown → 数据库

优先使用本 skill 的 `scripts/scrape_log.py migrate` 子命令（用法见 `references/scrape-log-tool.md`）；它按本节规则支持 SQLite / MySQL / PostgreSQL：

- 默认读取 `doc/*.md`；未配置数据库时写入 SQLite `data/scraping-logs.db`，SQL 保存到 `data/migrations/`，成功后归档到 `doc/archive/`。MySQL / PostgreSQL 必须通过 `--config` 提供连接信息，数据库需已存在。
- SQL 按目标方言生成（SQLite 保持 `TEXT`；MySQL / PostgreSQL 使用 `VARCHAR` / `TEXT`）；实际导入使用参数化插入。
- 生成 SQL 前查询已有 `run_id` 并跳过重复项；提交前校验 `scrape_runs` / `scrape_items` 行数。
- `--config` 提供时，在提交事务前原子更新 `config.json`；归档、config 写入或提交失败时回滚数据库记录、移回 md，并恢复原 config。
- `--db` 只用于覆盖 SQLite 路径；MySQL / PostgreSQL 必须使用 `--config`。
- `migrate` 需要 `scripts/database/requirements.txt` 中的 SQLAlchemy 与驱动，未安装时脚本报错并给出安装命令。`--dry-run` 对 SQLite 不创建数据库文件，对 MySQL / PostgreSQL 会只读连接查询已有 `run_id`。

仅迁移符合 `references/scrape-log-template.md` 的日志：解析后的 `log_schema` 必须为 `media-scraping-log/v1`，且 Records 表头与模板完全一致。旧格式日志不自动迁移，避免按标题猜测产生错误数据。

1. 读取 `doc/` 下所有 `.md`（不含 `doc/archive/`），逐个校验：
   - 缺少 frontmatter、`log_schema` 不为 `media-scraping-log/v1`、或 Records 表头不一致：判定为旧格式，跳过并在迁移报告中列出，不得删除。
   - frontmatter 缺必填键、取值非法、`finished_at` 为 `null`（运行未完成）、文件名与 `run_id` 不一致、`seq` 不连续、列数不为 7、路径未用反引号包裹：该文件迁移失败，整次迁移停止并输出 `ERROR`，不得部分导入。
   - 迁移前检查 `doc/archive/` 归档目标，已存在时停止，不覆盖。
2. 解析结果：frontmatter → `scrape_runs`（`library` 写入 `library_path`）；Records 每行 → `scrape_items`。`seq`、`action`、`media_type`、`status`、`source_path`、`target_path`、`note` 原样写入，`created_at` 取该文件的 `started_at`；表格中的 `-` 转为 `NULL`，空 `note` 转为 `NULL`。
3. 若目标数据库为 SQLite，创建 `data/scraping-logs.db` 并建表；MySQL / PostgreSQL 连接已存在的数据库后建表，不创建数据库。
4. 生成完整 SQL（DDL + 全部 md 记录的 `INSERT`，字符串按目标方言转义；已存在的 `run_id` 跳过，可用目标方言的跳过语法或在生成前排除）保存到 `data/migrations/<timestamp>-from-markdown.sql`，其中 `<timestamp>` 为迁移执行时间，格式 `YYYYMMDD-HHmmss`。
5. 在事务中执行 SQL，或使用等价的参数化插入；`run_id` 已存在时跳过该次运行并报告，不得重复插入。
6. 校验 `scrape_runs` / `scrape_items` 行数与解析结果一致。
7. 成功后把已迁移的 md 文件移动到 `doc/archive/`，更新 `config.json` 的 `log_storage` 与 `database`。
8. 任一步失败：回滚数据库记录，保留全部 md 文件，不修改 `config.json`，输出 `ERROR`。建表在导入事务之前执行，失败时表可能保留，但不会留下部分记录。

旧格式日志（无 frontmatter 或 `log_schema` 不为 `media-scraping-log/v1`）不参与自动迁移。历史日志若位于 `data/docs/` 等非 `doc/` 目录，同样不在读取范围内；如需入库，先人工或单独脚本归一化为模板结构并放入 `doc/`，再执行上述流程。归一化结果需经用户确认，不得按标题、表头或文件名猜测迁移内容。

### 数据库 → Markdown

1. 读取数据库全部运行与记录，按 `run_id` 生成 `doc/<run_id>.md`（16.2 节模板，含 frontmatter 与 Records）。目标文件已存在时停止，不覆盖。
2. 校验记录数量一致。
3. 成功后更新 `config.json` 的 `log_storage` 为 `markdown`；SQLite 数据库文件移动到 `data/archive/`，`config.json` 的 `database` 置为 `null`。非 SQLite 数据库保留原数据，仅断开配置。
4. 失败时保留数据库与 `config.json` 不变，输出 `ERROR`。

---

# 17. Safety Rules

Agent 不允许：

- 删除任何媒体
- 删除任何字幕
- 删除任何图片
- 删除日志文件或日志数据库
- 覆盖已有元数据
- 覆盖已有 `config.json`
- 未经用户要求切换日志存储方式
- 修改视频内容
- 转码视频

若出现冲突：

停止处理。

---

# 18. Manual Review

以下情况必须人工确认：

- 多部作品同名
- TMDB 无记录
- Season 不一致
- Episode 不一致
- OVA 无法匹配
- 剧场版无法匹配
- 弹幕无法匹配唯一视频
- 多个弹幕映射到同一目标名且内容不同
- 备份或入库目标已存在且 inode 不同
- 日志迁移的归档目标已存在

Agent 不允许自行决定。

---

# 19. Compatibility

本规范兼容：

- Jellyfin
- TMDB
- Bangumi Plugin
- Sonarr
- Radarr
- TinyMediaManager
- Plex
- Emby

---

# 20. Summary

最终媒体库应符合：

Movies/

```
Interstellar (2014)/
    Interstellar.2014.2160p.x265_FLAC-SubsPlease.mkv
```

Anime/

```
乱马½ (2024)/
    Season 1/
        Ranma½.2024.S01E01.1080p.x264_FLAC-SubsPlease.mkv
        Ranma½.2024.S01E01.1080p.x264_FLAC-SubsPlease.zh-Hans.ass
        Ranma½.2024.S01E01.1080p.x264_FLAC-SubsPlease.danmu.ass
        Ranma½.2024.S01E01.1080p.x264_FLAC-SubsPlease.danmu.xml
```

TV Shows/

```
Breaking Bad (2008)/
    Season 1/
        Breaking.Bad.2008.S01E01.1080p.x265_FLAC-SubsPlease.mkv
```

所有媒体均应：

- 目录使用 TMDB 官方标题（中文标题优先）
- 同一 TMDB collection 的多部电影归入 `<系列名>（系列）/` 系列文件夹
- 弹幕文件使用 `<视频完整主名>.danmu.<ext>`（如 `.danmu.ass` / `.danmu.xml`），不与普通字幕语言后缀混用
- 剧集与电影文件名中的 title 使用 TMDB 英文标题
- 使用 TMDB 年份
- 使用 TMDB Season 编号
- 使用 TMDB Episode 编号
- 与 Jellyfin 完全兼容
- 与 Bangumi 插件兼容

# 21. File Organization Rules

## 21.1 Hard Link Requirement

当媒体文件需要整理到新的媒体库目录时，**必须优先使用硬链接（Hard Link）**。

允许：

- 创建目录
- 创建硬链接
- 重命名硬链接
- 移动硬链接（仅媒体库中的链接）
- 创建字幕硬链接
- 创建弹幕硬链接
- 创建图片硬链接
- 创建备份硬链接（第 23.4 节）
- 将 `tmp/` 中的硬链接移动到媒体库（同一文件系统，第 23.3 节）

禁止：

- 剪切（Cut）
- 粘贴（Paste）
- 移动原始文件（Move）
- 复制文件（Copy）
- 删除原始文件

---

### 正确示例

原始下载目录：

```text
Downloads/
└── [SubsPlease] Ranma ½ - 01 (1080p).mkv
```

整理后的媒体库：

```text
Anime/
└── 乱马½ (2024)
    └── Season 1
        └── Ranma½.2024.S01E01.1080p.x264_FLAC-SubsPlease.mkv
```

Agent 应执行：

```text
Downloads/
└── [SubsPlease] Ranma ½ - 01 (1080p).mkv
        │
        └──────────────► Hard Link
                           │
                           ▼
Anime/
└── 乱马½ (2024)
    └── Season 1
        └── Ranma½.2024.S01E01.1080p.x264_FLAC-SubsPlease.mkv
```

原始下载目录保持不变。

媒体库中的文件为硬链接。

---

### 禁止示例

禁止：

```text
Downloads/

↓

Move

↓

Anime/
```

原因：

- 下载器可能丢失文件
- PT 做种失败
- 无法继续校验

禁止：

```text
Downloads/

↓

Copy

↓

Anime/
```

原因：

- 占用双倍磁盘空间
- 后续维护困难

---

## 21.2 Hard Link Validation

整理完成后，Agent 应验证：

- 原始文件仍然存在。
- 新文件已创建。
- 两个文件 inode 相同（若操作系统支持）。
- 文件大小一致。
- 文件校验值一致（可选）。

若无法创建硬链接：

停止处理，并输出：

```text
ERROR:
Hard Link creation failed.
```

不得自动改用复制（Copy）或移动（Move）。

---

## 21.3 Cross Filesystem

若原始目录与目标目录位于不同文件系统（Filesystem）或不同挂载点（Mount Point），导致无法创建硬链接：

Agent 不得自动复制或移动文件。

应停止处理，并输出：

```text
ERROR:
Source and destination are on different filesystems.
Hard links are not supported.
```

等待人工处理或调整目录结构。

入库模式下，`tmp/` 与媒体库必须位于同一文件系统；否则同样停止并输出上述 `ERROR`，不得把移动硬链接降级为复制。

### 中文标题规则

Agent 获取 TMDB 信息后，应按以下优先级确定目录名称：

1. TMDB 简体中文标题（zh-CN）
2. TMDB 原始标题（Original Title）
3. TMDB 英文标题（English Title）

不得直接使用当前网页显示语言作为最终目录名称。

网页显示语言受访问地区、浏览器语言或账户语言影响，不具有统一性。

---

# 22. Incremental Processing

Agent 默认只处理增量。

本次任务指定的新文件或下载目录是唯一输入。

不得自行将处理范围扩大到媒体库中已入库的内容。

已入库内容视为冻结：

- 不重命名
- 不重建硬链接
- 不移动
- 不重新刮削
- 不触碰已有 NFO、字幕、弹幕、图片

例如：

刀剑神域 (2012) 中 Season 1、Season 2 已入库。

新到 Season 3：

```text
Anime/
└── 刀剑神域 (2012)
    ├── Season 1/          ← 保持不变
    ├── Season 2/          ← 保持不变
    └── Season 3/          ← 仅新增
        └── Sword.Art.Online.2012.S03E01.1080p.x265_FLAC.mkv
```

Agent 只创建 Season 3 并入库其剧集。

Season 1、Season 2 及其全部文件保持不变。

---

## 22.1 判断方式

按序执行：

1. 目标文件已存在，且与来源为同一 inode（即已是硬链接）→ 跳过。

2. 目标 Season 目录已存在 → 仅补充缺失集数，不触碰已有集。

3. 新文件与已有集同名但非同一 inode（不同版本 / 不同来源）→ 不得覆盖，停止并输出：

```
Needs Manual Review
```

---

## 22.2 验证补充

整理完成后，除第 15 节外，还应确认：

- 已有文件的 inode 未变化

- 已有文件的修改时间未变化

---

## 22.3 日志补充

除第 16 节外，Agent 还应输出：

- 新增条目及数量

- 跳过条目及数量（注明"未修改"）

---

## 22.4 例外

仅当显式要求"修正存量"时，才可对已入库内容重做。

该操作不属于默认行为。

修正存量时，可按第 5.1 节将既有散放影片移入/移出系列文件夹：只移动媒体库中的硬链接，原始文件与 `backup/` 不动，并记录日志。

---

# 23. Workspace & Ingestion

## 23.1 Fixed Workspace

本 skill 使用一个固定的刮削工作区。以下内容全部位于工作区根目录：

```
<workspace>/
├── config.json
├── doc/                  # Markdown 日志（固定模板，见 references/）
├── data/                 # 数据库与迁移 SQL
├── tmp/                  # 入库模式临时目录
├── backup/               # 不入库模式的源文件备份硬链接
├── Movies/
├── Anime Movies/
├── TV Shows/
├── Anime/
├── Documentaries/
└── Music/
```

- 工作区路径记录在 `config.json` 的 `workspace` 字段，使用绝对路径。
- 首次运行时由用户确认工作区路径，默认为 Agent 当前工作目录；确认后不得随意更换。
- 当前目录没有 `config.json` 时，先询问工作区路径：用户指定已有工作区则读取其配置；用户确认以当前目录新建工作区时，才创建 `config.json` 并进入首次设置。不得在未确认的情况下新建工作区。
- `doc/`、`data/`、`tmp/`、`backup/` 只存放日志、数据库和硬链接，不得混入其他文件。
- 上述目录按需创建；目录不存在不代表配置错误。
- 分类目录（`Movies/` 等）只在“不入库”模式或已有工作区中使用；入库模式的工作区可以没有分类目录。

## 23.2 First-Run Setup

首次运行指 `config.json` 不存在，或缺少 `log_storage` / `ingest` 等必要字段。

首次运行以 `config.json` 是否存在为准；`doc/`、`data/` 只用于旧工作区的模式推断（16.1），数据库模式下 `doc/` 可以不存在。

按以下顺序询问，只补问缺失项；全部确认后写入 `config.json`，之后不再重复询问：

1. 工作区路径（默认当前目录）。若指定路径已存在 `config.json`，直接读取，不重复首次设置；目录不存在时先询问是否创建，不得擅自创建。
2. 日志存储方式（16.1 节）。
3. 是否需要入库：

```
本次刮削是否需要入库到 Jellyfin 媒体库？

1. 需要：请提供媒体库根目录（例如 ~/media）
2. 不需要：在工作区分类，并把源文件硬链接备份到 backup/
```

- 选择入库：必须提供 `jellyfin_library`；路径不存在时先询问是否创建，不得擅自创建。
- 选择不入库：`jellyfin_library` 记为 `null`。

`config.json` 示例（不入库 + Markdown 日志）：

```json
{
  "schema_version": 1,
  "workspace": "F:\\MediaWork",
  "log_storage": "markdown",
  "database": null,
  "ingest": false,
  "jellyfin_library": null
}
```

入库 + SQLite 日志：

```json
{
  "schema_version": 1,
  "workspace": "F:\\MediaWork",
  "log_storage": "database",
  "database": {
    "type": "sqlite",
    "path": "data/scraping-logs.db"
  },
  "ingest": true,
  "jellyfin_library": "~/media"
}
```

非 SQLite 数据库：

```json
{
  "schema_version": 1,
  "workspace": "F:\\MediaWork",
  "log_storage": "database",
  "database": {
    "type": "mysql",
    "host": "127.0.0.1",
    "port": 3306,
    "database": "media_scraping",
    "user": "scraper",
    "password_env": "MEDIA_SCRAPING_DB_PASSWORD"
  },
  "ingest": true,
  "jellyfin_library": "~/media"
}
```

PostgreSQL 把 `type` 改为 `postgresql`，端口默认 5432，其余字段相同：

```json
{
  "schema_version": 1,
  "workspace": "F:\\MediaWork",
  "log_storage": "database",
  "database": {
    "type": "postgresql",
    "host": "127.0.0.1",
    "port": 5432,
    "database": "media_scraping",
    "user": "scraper",
    "password_env": "MEDIA_SCRAPING_DB_PASSWORD"
  },
  "ingest": true,
  "jellyfin_library": "~/media"
}
```

规则：

- `database` 的 `type` 支持 `sqlite` / `mysql` / `postgresql`；数据库名可写作 `database` 或 `name`（同时存在时以 `database` 为准）。
- 密码只从 `password_env` 指定的环境变量读取，默认 `MEDIA_SCRAPING_DB_PASSWORD`；不得把密码写入 `config.json`、日志或 SQL。MySQL / PostgreSQL 数据库本身必须已存在。
- `jellyfin_library` 是媒体库根目录，其下直接使用第 4 节的分类结构。
- `~` 在读取时展开为当前用户主目录。
- `config.json` 已存在时不得覆盖；修改时保留未涉及字段。
- `config.json` 无法解析时停止，要求用户修复或确认重建，不得静默覆盖。
- `config.json` 写入失败时停止，不得在无配置的情况下开始刮削。
- 用户只要求“本次入库”或“本次不入库”时，只对本次生效，不修改 `config.json`。
- 用户明确要求修改默认设置时，更新对应字段并记录日志。

## 23.3 Ingest Mode

触发条件：`config.json` 中 `ingest: true`，或用户本次显式要求入库。

前置条件：

- `jellyfin_library` 已记录且可写。未记录时先询问媒体库路径；用户确认长期使用时写入 `config.json`，否则仅本次使用。
- 源目录、`tmp/`、媒体库位于同一文件系统。

流程：

1. 创建 `tmp/<run_id>/`。目录已存在且非空时停止，不得复用或清空。
2. 在 `tmp/<run_id>/` 下按第 4–12 节刮削：创建分类、季、电影目录，重命名并创建硬链接。所有文件均为硬链接，源文件不动。
3. 按第 15、22 节校验。
4. 合并到媒体库：
   - 媒体库根目录缺少的分类目录，按第 4 节创建。
   - 逐个把 `tmp/<run_id>/` 中的硬链接移动到媒体库对应路径。同一文件系统内移动不改变 inode。
   - 目标已存在且与来源为同一 inode：跳过。
   - 目标已存在但 inode 不同：不得覆盖，保留在 tmp，记为 `Needs Manual Review`。
5. 清理：只删除 `tmp/<run_id>/` 下的空目录；仍有文件时保留并记录，不得删除。
6. 日志记录源路径 → tmp 路径（`hardlink`）与 tmp 路径 → 媒体库路径（`move`）。
7. 成功后，工作区中旧的分类目录不得删除或移动。

禁止：

- 复制
- 跨文件系统移动
- 覆盖已有文件
- 删除 tmp 中未入库的文件

`tmp/` 与媒体库不在同一文件系统时停止并输出：

```
ERROR:
tmp and media library are on different filesystems.
Hard links are required.
```

不得改为复制。

## 23.4 Non-Ingest Mode

触发条件：`config.json` 中 `ingest: false`，或用户本次显式要求不入库。

流程：

1. 备份源文件：把本次任务输入范围内的源文件（视频、字幕、弹幕、图片、NFO）按相对输入目录的路径，硬链接到 `backup/<run_id>/`。
   - 目标已存在且为同一 inode：跳过。
   - 目标已存在但 inode 不同：不得覆盖，记为 `Needs Manual Review`。
   - 多个输入目录时，各自以其目录名在 `backup/<run_id>/` 下建子目录；子目录重名时停止并输出 `Needs Manual Review`。
2. 在工作区根目录下按第 4–12 节分类、重命名并创建硬链接。
3. 校验备份硬链接（第 21.2 节）。
4. 日志记录备份硬链接（`backup`）与分类硬链接（`hardlink`）。
5. 源文件保持原样，不得移动、复制或删除。

源文件、工作区分类目录、`backup/` 不在同一文件系统时停止并输出第 21.3 节的 `ERROR`，不得降级为复制。

## 23.5 Mode Change

- 入库 / 不入库是默认设置，保存在 `config.json` 的 `ingest`。
- 修改默认设置只影响后续运行；已经整理或入库的文件按第 22 节冻结，不自动搬运。
- 需要修正存量时，按第 22.4 节处理。用户明确要求时，才可把工作区中已整理的硬链接移入媒体库，或反向移出；原始文件与 `backup/` 不动。
