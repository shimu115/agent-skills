# Scrape Log Tool

`media-scraping` 的标准日志生成与 Markdown → 数据库迁移工具。脚本是 [`../scripts/scrape_log.py`](../scripts/scrape_log.py)，随 skill 安装，要求 Python 3.8+。`init` / `add` / `finish` / `validate` 只用 Python 标准库；`migrate` 使用 [`../scripts/database/`](../scripts/database/) 的 SQLAlchemy Core 层，需要额外安装依赖。

## 用途

- `init` / `add` / `finish`：按 [`scrape-log-template.md`](scrape-log-template.md) 生成日志，避免手写表头、转义和 `seq` 出错。
- `validate`：校验单个文件或整个 `doc/`，迁移前可先跑一遍。
- `migrate`：把 v1 Markdown 日志迁移到 SQLite / MySQL / PostgreSQL，生成 `data/migrations/<timestamp>-from-markdown.sql`，成功后归档 md。

脚本只读写日志、目标数据库、`data/migrations/`、`doc/archive/`，以及 `--config` 指定的 `config.json`；不接触原始媒体文件，不联网。

## 依赖

`init` / `add` / `finish` / `validate` 只用标准库。

`migrate` 需要 SQLAlchemy 2.x 和目标数据库驱动：

```sh
SKILL_DIR="$HOME/.claude/skills/media-scraping"   # 按实际安装位置调整
python -m pip install -r "$SKILL_DIR/scripts/database/requirements.txt"
```

`requirements.txt` 包含 SQLAlchemy、PyMySQL[rsa]（MySQL，含 MySQL 8 认证依赖）和 psycopg（PostgreSQL）；SQLite 使用 Python 标准库 `sqlite3`，无需额外驱动。未安装时 `migrate` 会报错并给出安装命令。

数据库层（仅 `migrate` 使用）：

- `scripts/database/connection.py`：读取 `config.json`、解析连接信息、创建 engine。
- `scripts/database/models.py`：SQLAlchemy Core 的 `scrape_runs` / `scrape_items` 表定义。
- `scripts/database/repository.py`：统一数据访问接口；阶段一提供迁移所需的查询与写入。
- `scripts/database/migration.py`：Markdown 迁移编排、SQL 生成、事务导入与回滚。

## 脚本位置

脚本随 skill 一起安装，位于本 skill 目录的 `scripts/scrape_log.py`，无需复制到工作区，也不需要从文档生成。

定位方式：

- skill 加载时若给出 base directory，直接使用 `<base>/scripts/scrape_log.py`。
- 否则按安装位置查找：`~/.claude/skills/media-scraping/scripts/scrape_log.py`、`~/.dsh/skills/media-scraping/scripts/scrape_log.py`、`~/.agents/skills/media-scraping/scripts/scrape_log.py`，或项目级 `<项目根>/.claude/skills/...`、`.dsh/skills/...`、`.agents/skills/...`。
- 安装时只复制了 `SKILL.md`、没有 `scripts/` 时，重新复制整个 `media-scraping` 目录或改用软链。

不要把脚本复制进工作区的 `doc/`、`data/`、`tmp/`、`backup/`：这些目录按 23.1 只存放日志、数据库和硬链接。

## 生成日志

在工作区根目录执行（Windows 下路径改成 `F:\...`，含空格的参数加引号）。`SKILL_DIR` 指向 skill 安装目录，按实际位置调整；Windows PowerShell 用 `$SKILL_DIR = "$env:USERPROFILE\.claude\skills\media-scraping"`、`$TOOL = "$SKILL_DIR\scripts\scrape_log.py"`，后续命令把 `"$TOOL"` 写成 `$TOOL`：

```sh
SKILL_DIR="$HOME/.claude/skills/media-scraping"   # 按实际安装位置调整
TOOL="$SKILL_DIR/scripts/scrape_log.py"
python "$TOOL" init --workspace /path/to/workspace --mode in_place
# log_path=/path/to/workspace/doc/20261126-153000.md
# run_id=20261126-153000

python "$TOOL" add \
  --log /path/to/workspace/doc/20261126-153000.md \
  --action hardlink --media-type tv --status done \
  --source '/downloads/Show/S01E01.mkv' \
  --target 'TV Shows/Show (2020)/Season 1/Show.2020.S01E01.1080p.x264_FLAC-Group.mkv'

python "$TOOL" add \
  --log /path/to/workspace/doc/20261126-153000.md \
  --action backup --media-type tv --status done \
  --source '/downloads/Show/S01E01.mkv' \
  --target 'backup/20261126-153000/Show/S01E01.mkv'

python "$TOOL" add \
  --log /path/to/workspace/doc/20261126-153000.md \
  --action review --media-type tv --status needs_review \
  --source '/downloads/Show/S01E02.mkv' --target - \
  --note '无对应 TMDB 剧集'

python "$TOOL" finish \
  --log /path/to/workspace/doc/20261126-153000.md \
  --added 1 --skipped 0 --needs-review 1 --errors 0

python "$TOOL" validate \
  --log /path/to/workspace/doc/20261126-153000.md --require-finished
```

规则：

- `--source` / `--target` 传 `-` 表示无路径。
- `--note` 中的换行会变成空格；`|` 自动转义成 `\|`；空 note 在迁移时写为 `NULL`。
- 路径含反引号或换行时脚本拒绝写入，由 agent 按 16.2 记为 `Needs Manual Review`。
- `init` 不覆盖已有日志；运行中 `finished_at` 为 `null`，`finish` 写入完成时间并同步 frontmatter 与 `## Summary`。
- `finish` 的四个计数按 16.2 的口径传入（按文件条目，不按 Records 行数）；脚本只校验非负，不自行推断。
- `add` / `finish` 使用临时文件 + `os.replace` 原子写入；写入失败不会留下半行记录。

`init` 参数：

| 参数 | 说明 |
| --- | --- |
| `--workspace` | 工作区绝对路径；提供 `--config` 时可省略 |
| `--mode` | `in_place` 或 `ingest`；提供 `--config` 时可省略 |
| `--library` | 入库模式的媒体库绝对路径；`in_place` 不得设置 |
| `--run-id` | 默认当前时间 `YYYYMMDD-HHmmss`；提供时 `started_at` 默认由它推导 |
| `--started-at` | 默认当前时间 |
| `--doc-dir` | 默认 `<workspace>/doc` |
| `--config` | 读取 `config.json` 的 `workspace`、`ingest`、`jellyfin_library`；`log_storage` 必须缺失或为 `markdown` |

`add` 的 `--action` / `--media-type` / `--status` 取值由脚本按 16.2 校验，非法值直接拒绝。

## 迁移

在工作区根目录执行（`TOOL` 同上）：

```sh
# SQLite：先看会生成什么，不改数据库和日志
python "$TOOL" migrate --dry-run

# SQLite：正式迁移；--config 让脚本成功后原子更新 config.json
python "$TOOL" migrate --config config.json

# MySQL / PostgreSQL：必须提供 --config
python "$TOOL" migrate --config config.json --dry-run
python "$TOOL" migrate --config config.json
```

默认读取 `doc/*.md`，写入 `config.json` 指定的数据库；未配置数据库时使用 SQLite `data/scraping-logs.db`。SQL 保存到 `data/migrations/<timestamp>-from-markdown.sql`，迁移成功的 md 移到 `doc/archive/`。

### 数据库配置

`config.json` 的 `database` 支持 SQLite：

```json
{
  "type": "sqlite",
  "path": "data/scraping-logs.db"
}
```

MySQL：

```json
{
  "type": "mysql",
  "host": "127.0.0.1",
  "port": 3306,
  "database": "media_scraping",
  "user": "scraper",
  "password_env": "MEDIA_SCRAPING_DB_PASSWORD"
}
```

PostgreSQL：

```json
{
  "type": "postgresql",
  "host": "127.0.0.1",
  "port": 5432,
  "database": "media_scraping",
  "user": "scraper",
  "password_env": "MEDIA_SCRAPING_DB_PASSWORD"
}
```

- 数据库名也可写作 `name`；两者同时存在时以 `database` 为准。
- `port` 省略时 MySQL 用 3306、PostgreSQL 用 5432。
- 密码只从 `password_env` 指定的环境变量读取；省略时使用 `MEDIA_SCRAPING_DB_PASSWORD`。不得把密码写进 `config.json`，脚本也不会把密码写入日志或 SQL。
- MySQL / PostgreSQL 的数据库本身必须已存在；脚本只建表，不建数据库。
- SQLite 的 `database.path` 相对 `config.json` 的 `workspace`（未设置时为当前目录）；`--db` 相对当前目录，且与已配置的 `database.path` 不一致时脚本报错。
- `--db` 只覆盖 SQLite 路径；MySQL / PostgreSQL 必须用 `--config`。

### 迁移规则

- 只迁移 `log_schema: 'media-scraping-log/v1'`、通过校验、`finished_at` 非 `null`、文件名与 `run_id` 一致、且 `run_id` 未在数据库中的日志。
- 没有 frontmatter 或不是 v1 的文件按 legacy 跳过，不报错、不删除。
- v1 但结构错误 / 未完成 / 文件名不符：整个迁移中止，不生成 SQL、不改数据库、不移动日志。
- 已存在的 `run_id` 跳过，不重复导入，也不归档；脚本不比较 md 与数据库内容，需要清理或怀疑内容不一致时先人工核对。
- 没有可迁移的新日志时只报告 `Nothing to migrate`，不生成 SQL、不改数据库和 `config.json`。
- 运行中断留下的 `finished_at: null` 日志会让 `migrate` 整体中止；先补 `finish`，或确认后把该文件移出 `doc/`（不要删除）。
- 导入前生成完整 SQL（DDL + 全部新记录），实际导入使用 SQLAlchemy 参数化 `INSERT`；提交前校验每个 `run_id` 的 `scrape_runs` 为 1 行、`scrape_items` 行数与解析结果一致。
- 同一秒内重复运行（例如先 `--dry-run` 再正式执行）时，SQL 文件名追加 `-2`、`-3` 等后缀，避免覆盖已有文件。
- 生成的 SQL 文件用于审阅和手工执行，不是幂等脚本；重复执行可能因已有索引或重复 `run_id` 失败。需要重跑时用 `migrate`，脚本会跳过已有 `run_id`。
- 归档和 config 更新在同一个事务窗口内：归档失败、config 写入失败或提交失败都会回滚数据库记录，并把已移动的 md 移回原处。已生成的 SQL 文件保留，便于排查。
- 建表在导入事务之前；失败时表可能保留（MySQL DDL 会自动提交，SQLite/PostgreSQL 也不保证回滚 DDL），但不会留下部分记录。
- `--config` 更新 `log_storage` 为 `"database"`；SQLite 同时写入 `database` 为 `{"type": "sqlite", "path": "data/scraping-logs.db"}`（路径优先相对 config 的 `workspace`，无法相对时写绝对路径）；MySQL/PostgreSQL 保留原连接块（含 `password_env`，不含密码）。不传 `--config` 时脚本打印 `Next:` 行，由 agent 按 16.4 更新配置。
- SQL 文件按目标方言生成：SQLite 保持 TEXT 类型；MySQL/PostgreSQL 使用 VARCHAR(64)/VARCHAR(19) 与 TEXT。MySQL 的 DDL 会先执行，再 `START TRANSACTION` 导入记录；PostgreSQL 使用标准字符串（`standard_conforming_strings=on`）。
- `--dry-run` 对 SQLite 不创建数据库文件；对 MySQL/PostgreSQL 会连接数据库读取已有 `run_id`（只读），因此需要驱动、可访问的数据库和已设置的环境变量密码。
- 脚本不实现数据库 → Markdown；该方向仍按 16.4 手工执行。

迁移参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--doc-dir` | `doc` | 日志目录 |
| `--db` | `data/scraping-logs.db` | SQLite 数据库路径；仅 SQLite；未提供时使用 `--config` 中的 `database.path`，两者不一致时报错 |
| `--migrations-dir` | `<doc-dir>/../data/migrations` | SQL 输出目录 |
| `--config` | 无 | 读取数据库配置；MySQL/PostgreSQL 必填；迁移成功时在事务提交前原子更新 `config.json` |
| `--dry-run` | 关闭 | 只生成 SQL |
| `--no-archive` | 关闭 | 不移动 md（测试用） |

`data/docs/` 等非 `doc/` 目录中的历史日志不在读取范围内；先按 16.4 归一化为 v1 模板并放入 `doc/`，再执行迁移。

## 退出码

- `0`：成功；`validate` 没有无效 v1 日志（legacy 跳过不算失败）
- `1`：参数、校验或迁移错误
