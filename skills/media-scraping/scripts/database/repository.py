"""Unified data-access helpers for the media-scraping log database.

This is intentionally the small phase-one surface used by the Markdown
migration.  Query/pagination/filter methods can be added here later without
changing the connection or table definitions.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from . import models


class Repository:
    """Read/write access bound to one SQLAlchemy connection/transaction."""

    def __init__(self, connection: Connection):
        self.connection = connection

    def existing_run_ids(self) -> set:
        rows = self.connection.execute(select(models.scrape_runs.c.run_id))
        return {row[0] for row in rows}

    def run_exists(self, run_id: str) -> bool:
        stmt = select(models.scrape_runs.c.run_id).where(
            models.scrape_runs.c.run_id == run_id
        )
        return self.connection.execute(stmt).first() is not None

    def insert_run(self, row: Mapping[str, Any]) -> None:
        self.connection.execute(
            models.scrape_runs.insert().values(**dict(row))
        )

    def insert_items(self, rows: Sequence[Mapping[str, Any]]) -> None:
        if rows:
            self.connection.execute(
                models.scrape_items.insert(), [dict(row) for row in rows]
            )

    def count_runs(self, run_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(models.scrape_runs)
            .where(models.scrape_runs.c.run_id == run_id)
        )
        return int(self.connection.execute(stmt).scalar_one())

    def count_items(self, run_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(models.scrape_items)
            .where(models.scrape_items.c.run_id == run_id)
        )
        return int(self.connection.execute(stmt).scalar_one())
