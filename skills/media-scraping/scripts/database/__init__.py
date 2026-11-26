"""Database layer for the media-scraping skill.

Log generation, validation, and Markdown parsing stay in ``scrape_log.py``
and remain standard-library only.  Only ``scrape_log.py migrate`` and the
``runs`` / ``items`` query commands import this package, so SQLAlchemy is
an optional dependency for the other commands.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


class DatabaseError(Exception):
    """A database configuration or access error."""


class MigrationError(DatabaseError):
    """A migration could not be completed safely."""


def write_text_atomic(path: Path, text: str) -> None:
    """Write UTF-8 text atomically in the same directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
