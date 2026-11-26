---
log_schema: 'media-scraping-log/v1'
run_id: '<YYYYMMDD-HHmmss>'
started_at: '<YYYY-MM-DD HH:MM:SS>'
finished_at: '<YYYY-MM-DD HH:MM:SS>'
workspace: '<工作区绝对路径>'
mode: '<in_place|ingest>'
library: null
summary_added: 0
summary_skipped: 0
summary_needs_review: 0
summary_errors: 0
---

# Scrape Log: <run_id>

> 本文件是 media-scraping 的标准 Markdown 日志模板。
>
> - 机器迁移只读取 YAML frontmatter 和 `## Records` 表格。
> - 其他章节（`## Summary`、`## Notes` 等）仅供人阅读，迁移时忽略。
> - 不得修改 frontmatter 键名、Records 表头、列顺序和取值集合。
> - 每个文件操作一行，`seq` 从 1 开始连续递增。
> - 可用本 skill 的 `scripts/scrape_log.py` 的 `init` / `add` / `finish` 生成，避免手写格式错误；用法见 `references/scrape-log-tool.md`。
> - 运行中 `finished_at` 写 `null`，结束时写入完成时间；迁移要求非 `null`。

## Records

| seq | action | media_type | status | source_path | target_path | note |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | hardlink | tv | done | `D:\Downloads\Show\S01E01.mkv` | `TV Shows/Show (2020)/Season 1/Show.2020.S01E01.1080p.x264_FLAC-Group.mkv` | |
| 2 | backup | tv | done | `D:\Downloads\Show\S01E01.mkv` | `backup/<run_id>/Show/S01E01.mkv` | |
| 3 | skip | tv | skipped | `D:\Downloads\Show\S01E02.mkv` | `TV Shows/Show (2020)/Season 1/Show.2020.S01E02.1080p.x264_FLAC-Group.mkv` | 已是同一 inode |

## Summary

- Added: 1
- Skipped: 1
- Needs Manual Review: 0
- Errors: 0

## Notes

<可选：TMDB ID、作品名、季集说明、异常说明等。迁移时忽略；也可以在此后追加 `## 基本信息`、`## 验证结果` 等人类可读章节。>
