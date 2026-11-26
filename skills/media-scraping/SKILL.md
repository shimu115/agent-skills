---
name: media-scraping
description: 整理、重命名、入库媒体库文件时使用。统一 Movies / TV Shows / Anime / Anime Movies 目录结构，剧集文件采用「英文标题.年份.SxxExx.分辨率.视频编码_音频编码-发布组.扩展名」、电影文件采用「英文标题.年份.分辨率.视频编码_音频编码-发布组.扩展名」的发布组风格命名（电影不含 SxxExx；同一 TMDB collection 的多部电影归入「系列名（系列）」文件夹；弹幕文件按「视频完整主名.danmu.ass / .danmu.xml」命名），以 Jellyfin 已刮削元数据和 TMDB 为标准（目录名中文标题优先 zh-CN），通过硬链接 hard link 入库，禁止复制、移动、删除原始文件。适用于 Jellyfin 刮削、动漫季集编号整理、字幕与海报重命名、Bangumi 插件兼容等场景。
---

# Media Scraping Specification

Version: 1.5

> 规范内容以本文为准。修改规范时，同步更新上方的 `Version:` 与下方变更记录。

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
- 无法唯一匹配视频的弹幕留在 backup 并记录，不得按集号猜测。
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

Fate Zero (2011)/Season 1/Fate.Zero.2011.S01E01.1080p.x265_FLAC-VCB-Studio.mkv
```

所有修改均需记录。

---

# 17. Safety Rules

Agent 不允许：

- 删除任何媒体
- 删除任何字幕
- 删除任何图片
- 覆盖已有元数据
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

修正存量时，可按第 5.1 节将既有散放影片移入/移出系列文件夹：只移动媒体库中的硬链接，原始文件与 backup 不动，并记录日志。
