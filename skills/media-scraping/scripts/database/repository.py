"""Unified data-access helpers for the media-scraping log database.

The repository is usable by the CLI and by future scraping tools.  It
covers the migration reads/writes plus read-only queries with time/status/
media-type filters and pagination.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from . import models


@dataclass(frozen=True)
class Page:
    """One page of query results plus the total number of matches."""

    total: int
    items: List[Dict[str, Any]]
    limit: int
    offset: int


def _check_page(limit: int, offset: int) -> None:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if offset < 0:
        raise ValueError("offset must be >= 0")


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

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Return one run record as a mapping, or ``None`` when missing."""
        stmt = select(models.scrape_runs).where(
            models.scrape_runs.c.run_id == run_id
        )
        row = self.connection.execute(stmt).first()
        return dict(row._mapping) if row is not None else None

    def list_runs(
        self,
        *,
        run_id: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page:
        """Return runs newest first.

        ``since``/``until`` compare against ``started_at`` and are
        inclusive.  Timestamps use the fixed ``YYYY-MM-DD HH:MM:SS``
        format stored by the log tools.
        """
        _check_page(limit, offset)
        conditions = []
        if run_id is not None:
            conditions.append(models.scrape_runs.c.run_id == run_id)
        if since is not None:
            conditions.append(models.scrape_runs.c.started_at >= since)
        if until is not None:
            conditions.append(models.scrape_runs.c.started_at <= until)

        total = int(
            self.connection.execute(
                select(func.count())
                .select_from(models.scrape_runs)
                .where(*conditions)
            ).scalar_one()
        )
        stmt = (
            select(models.scrape_runs)
            .where(*conditions)
            .order_by(
                models.scrape_runs.c.started_at.desc(),
                models.scrape_runs.c.run_id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        rows = [dict(row._mapping) for row in self.connection.execute(stmt)]
        return Page(total=total, items=rows, limit=limit, offset=offset)

    def list_items(
        self,
        *,
        run_id: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        statuses: Optional[Sequence[str]] = None,
        media_types: Optional[Sequence[str]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page:
        """Return operation records newest first.

        ``since``/``until`` compare against ``created_at``.  ``statuses``
        and ``media_types`` are OR-lists; an empty sequence means no filter.
        """
        _check_page(limit, offset)
        conditions = []
        if run_id is not None:
            conditions.append(models.scrape_items.c.run_id == run_id)
        if since is not None:
            conditions.append(models.scrape_items.c.created_at >= since)
        if until is not None:
            conditions.append(models.scrape_items.c.created_at <= until)
        if statuses:
            conditions.append(models.scrape_items.c.status.in_(list(statuses)))
        if media_types:
            conditions.append(
                models.scrape_items.c.media_type.in_(list(media_types))
            )

        total = int(
            self.connection.execute(
                select(func.count())
                .select_from(models.scrape_items)
                .where(*conditions)
            ).scalar_one()
        )
        stmt = (
            select(models.scrape_items)
            .where(*conditions)
            .order_by(
                models.scrape_items.c.created_at.desc(),
                models.scrape_items.c.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        rows = [dict(row._mapping) for row in self.connection.execute(stmt)]
        return Page(total=total, items=rows, limit=limit, offset=offset)

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
