"""SQLAlchemy Core table definitions for the media-scraping log database.

The two tables, column names, nullability, unique key, foreign key, and
index name follow the existing SQLite schema so old databases remain
readable and writable.  SQLite stores the short strings as TEXT in older
databases; SQLAlchemy's VARCHAR types are compatible with those values.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)

# SQLite databases created by scrape_log.py 1.9 used TEXT for every string
# column.  Keep that physical type on SQLite while using bounded VARCHAR
# columns on MySQL/PostgreSQL (MySQL cannot use TEXT as an unbounded key).
RUN_KEY_TYPE = String(64).with_variant(Text(), "sqlite")
TIMESTAMP_TYPE = String(19).with_variant(Text(), "sqlite")

metadata = MetaData()

scrape_runs = Table(
    "scrape_runs",
    metadata,
    Column("run_id", RUN_KEY_TYPE, primary_key=True),
    Column("started_at", TIMESTAMP_TYPE, nullable=False),
    Column("finished_at", TIMESTAMP_TYPE, nullable=True),
    Column("workspace", Text, nullable=False),
    Column("mode", RUN_KEY_TYPE, nullable=False),
    Column("library_path", Text, nullable=True),
    Column("summary_added", Integer, nullable=False, server_default=text("0")),
    Column("summary_skipped", Integer, nullable=False, server_default=text("0")),
    Column(
        "summary_needs_review", Integer, nullable=False, server_default=text("0")
    ),
    Column("summary_errors", Integer, nullable=False, server_default=text("0")),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

scrape_items = Table(
    "scrape_items",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", RUN_KEY_TYPE, ForeignKey("scrape_runs.run_id"), nullable=False),
    Column("seq", Integer, nullable=False),
    Column("action", RUN_KEY_TYPE, nullable=False),
    Column("media_type", RUN_KEY_TYPE, nullable=True),
    Column("source_path", Text, nullable=True),
    Column("target_path", Text, nullable=True),
    Column("status", RUN_KEY_TYPE, nullable=False),
    Column("note", Text, nullable=True),
    Column("created_at", TIMESTAMP_TYPE, nullable=False),
    UniqueConstraint("run_id", "seq", name="uq_scrape_items_run_seq"),
    sqlite_autoincrement=True,
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

scrape_items_run_id_idx = Index("idx_scrape_items_run_id", scrape_items.c.run_id)


def create_schema(engine) -> None:
    """Create missing tables and their indexes; existing tables are untouched."""
    metadata.create_all(engine)
