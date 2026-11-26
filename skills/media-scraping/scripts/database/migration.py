"""Markdown log -> database migration orchestration.

The Markdown parser and v1 validation live in ``scrape_log.py``.  This
module receives neutral ``MigrationDoc`` objects, checks them against the
target database, writes a reviewable SQL file, and performs a transactional
import for SQLite, MySQL, and PostgreSQL.
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import inspect
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateIndex, CreateTable

from . import MigrationError, write_text_atomic
from . import connection, models, repository


@dataclass(frozen=True)
class MigrationDoc:
    path: Path
    run: Dict[str, Any]
    items: List[Dict[str, Any]]

    @property
    def run_id(self) -> str:
        return str(self.run["run_id"])


@dataclass
class MigrationResult:
    sql_path: Optional[Path]
    imported_runs: int
    imported_items: int
    skipped: List[MigrationDoc]
    archived: List[Path]
    dry_run: bool


def _table_exists(engine: Engine, table_name: str) -> bool:
    return inspect(engine).has_table(table_name)


def _read_existing(
    engine: Engine, settings: connection.DatabaseSettings
) -> set:
    # Do not let a dry run create an empty SQLite file just to inspect it.
    if settings.type == "sqlite" and settings.sqlite_path is not None:
        if not settings.sqlite_path.exists():
            return set()
    if not _table_exists(engine, models.scrape_runs.name):
        return set()
    with engine.connect() as conn:
        return repository.Repository(conn).existing_run_ids()


def _check_duplicate_run_ids(docs: Sequence[MigrationDoc]) -> None:
    seen: Dict[str, Path] = {}
    for doc in docs:
        if doc.run_id in seen:
            raise MigrationError(
                "duplicate run_id %s in %s and %s"
                % (doc.run_id, seen[doc.run_id], doc.path)
            )
        seen[doc.run_id] = doc.path


def _sql_dialect_for(dialect_name: str):
    """A dialect for the reviewable SQL file, not for the live import.

    PostgreSQL's generic dialect assumes ``standard_conforming_strings=off``
    when rendering literal strings.  The generated file assumes the modern
    default (on), so backslashes are kept literal.
    """
    if dialect_name == "mysql":
        return mysql.dialect()
    if dialect_name == "postgresql":
        dialect = postgresql.dialect()
        dialect._backslash_escapes = False
        return dialect
    return sqlite.dialect()


def _table_ddl(table, dialect) -> str:
    return str(
        CreateTable(table, if_not_exists=True).compile(dialect=dialect)
    ).strip()


def _index_ddl(index, dialect) -> str:
    # MySQL does not accept CREATE INDEX IF NOT EXISTS.
    if dialect.name == "mysql":
        statement = CreateIndex(index)
    else:
        statement = CreateIndex(index, if_not_exists=True)
    return str(statement.compile(dialect=dialect)).strip()


def _insert_sql(statement, dialect) -> str:
    sql = str(
        statement.inline().compile(
            dialect=dialect, compile_kwargs={"literal_binds": True}
        )
    ).strip()
    # SQLAlchemy doubles percent signs for format/pyformat DBAPI drivers.
    # A SQL file is not sent through a DBAPI, so restore the literal value.
    if dialect.paramstyle in ("format", "pyformat"):
        sql = sql.replace("%%", "%")
    return sql + ";"


def _unique_sql_path(migrations_dir: Path, timestamp: str) -> Path:
    path = migrations_dir / ("%s-from-markdown.sql" % timestamp)
    suffix = 2
    while path.exists():
        path = migrations_dir / (
            "%s-%d-from-markdown.sql" % (timestamp, suffix)
        )
        suffix += 1
    return path


def _index_for(table) -> Any:
    for index in table.indexes:
        if index.name == "idx_scrape_items_run_id":
            return index
    raise MigrationError("index idx_scrape_items_run_id is not defined")


def build_sql(
    docs: Sequence[MigrationDoc], dialect, generated_at: str
) -> str:
    lines = [
        "-- media-scraping md -> database migration",
        "-- dialect: %s" % dialect.name,
        "-- generated_at: %s" % generated_at,
        "-- source logs:",
    ]
    for doc in docs:
        safe_name = doc.path.name.replace("\r", " ").replace("\n", " ")
        lines.append("--   %s (run_id=%s)" % (safe_name, doc.run_id))
    lines.append("--")
    lines.append(
        "-- The migration itself uses parameterized INSERTs; this file is a"
    )
    lines.append("-- reviewable, runnable SQL record for the same target.")
    if dialect.name == "mysql":
        lines.append(
            "-- MySQL note: DDL statements auto-commit; START TRANSACTION"
        )
        lines.append(
            "-- begins the insert transaction.  String escaping assumes the"
        )
        lines.append("-- default sql_mode (backslash escapes enabled).")
    elif dialect.name == "postgresql":
        lines.append(
            "-- PostgreSQL note: strings assume standard_conforming_strings=on"
        )
        lines.append("-- (the default).")
    if dialect.name != "mysql":
        lines.extend(["", "BEGIN;", ""])
    else:
        lines.append("")
    lines.append(_table_ddl(models.scrape_runs, dialect) + ";")
    lines.append("")
    lines.append(_table_ddl(models.scrape_items, dialect) + ";")
    lines.append("")
    lines.append(_index_ddl(_index_for(models.scrape_items), dialect) + ";")
    lines.append("")
    if dialect.name == "mysql":
        lines.append("START TRANSACTION;")
        lines.append("")
    for doc in docs:
        lines.append(
            _insert_sql(models.scrape_runs.insert().values(**doc.run), dialect)
        )
        for item in doc.items:
            lines.append(
                _insert_sql(
                    models.scrape_items.insert().values(**item), dialect
                )
            )
        lines.append("")
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


def migrate(
    docs: Sequence[MigrationDoc],
    engine: Engine,
    settings: connection.DatabaseSettings,
    *,
    migrations_dir: Path,
    archive_dir: Path,
    config_path: Optional[Path] = None,
    config: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
    no_archive: bool = False,
) -> MigrationResult:
    """Import the given docs and return what happened.

    Existing run_ids are skipped.  The SQL file is written before any
    database change; the import, archive moves, and optional config update
    are committed together and rolled back on failure.
    """
    config = config or {}
    _check_duplicate_run_ids(docs)

    existing = _read_existing(engine, settings)
    new_docs = [doc for doc in docs if doc.run_id not in existing]
    skipped = [doc for doc in docs if doc.run_id in existing]

    if not new_docs:
        return MigrationResult(None, 0, 0, skipped, [], dry_run)

    if not no_archive:
        for doc in new_docs:
            target = archive_dir / doc.path.name
            if target.exists():
                raise MigrationError(
                    "archive target already exists: %s" % target
                )

    config_old_text = None
    config_new_text = None
    if not dry_run and config_path is not None:
        try:
            config_old_text = config_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise MigrationError(
                "cannot read config %s: %s" % (config_path, exc)
            )
        updated = connection.build_config_update(config, settings)
        config_new_text = (
            json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
        )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    migrations_dir.mkdir(parents=True, exist_ok=True)
    sql_path = _unique_sql_path(migrations_dir, timestamp)
    sql_text = build_sql(
        new_docs, _sql_dialect_for(engine.dialect.name), timestamp
    )
    write_text_atomic(sql_path, sql_text)

    if dry_run:
        return MigrationResult(sql_path, 0, 0, skipped, [], True)

    if settings.type == "sqlite" and settings.sqlite_path is not None:
        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    connection.create_schema(engine)

    conn = engine.connect()
    trans = None
    moved: List[Any] = []
    config_written = False
    imported_items = 0
    try:
        trans = conn.begin()
        repo = repository.Repository(conn)

        # Guard against another import racing the pre-flight read.
        for doc in new_docs:
            if repo.run_exists(doc.run_id):
                raise MigrationError(
                    "database changed during migration; run_id already "
                    "exists: %s" % doc.run_id
                )

        for doc in new_docs:
            repo.insert_run(doc.run)
            repo.insert_items(doc.items)
            imported_items += len(doc.items)

        for doc in new_docs:
            run_count = repo.count_runs(doc.run_id)
            item_count = repo.count_items(doc.run_id)
            if run_count != 1 or item_count != len(doc.items):
                raise MigrationError(
                    "verification failed for %s: runs=%d, items=%d"
                    % (doc.run_id, run_count, item_count)
                )

        if not no_archive:
            archive_dir.mkdir(parents=True, exist_ok=True)
            for doc in new_docs:
                target = archive_dir / doc.path.name
                if target.exists():
                    raise MigrationError(
                        "archive target already exists: %s" % target
                    )
                shutil.move(str(doc.path), str(target))
                moved.append((doc.path, target))

        if config_path is not None and config_new_text is not None:
            write_text_atomic(config_path, config_new_text)
            config_written = True

        trans.commit()
    except BaseException:
        if trans is not None:
            try:
                trans.rollback()
            except Exception:
                pass
        for source, target in reversed(moved):
            try:
                shutil.move(str(target), str(source))
            except OSError:
                pass
        if config_written and config_old_text is not None:
            try:
                write_text_atomic(config_path, config_old_text)
            except OSError:
                print(
                    "ERROR: failed to restore config %s" % config_path,
                    file=sys.stderr,
                )
        raise
    finally:
        conn.close()

    return MigrationResult(
        sql_path=sql_path,
        imported_runs=len(new_docs),
        imported_items=imported_items,
        skipped=skipped,
        archived=[target for _, target in moved],
        dry_run=False,
    )
