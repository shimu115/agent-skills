"""Database connection and config parsing for media-scraping.

``config.json`` stores non-secret connection fields.  The password is read
from the environment variable named by ``database.password_env`` (default
``MEDIA_SCRAPING_DB_PASSWORD``) and is never written back to the config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, URL

from . import DatabaseError
from . import models

DEFAULT_SQLITE_PATH = "data/scraping-logs.db"
DEFAULT_PASSWORD_ENV = "MEDIA_SCRAPING_DB_PASSWORD"
SUPPORTED_TYPES = ("sqlite", "mysql", "postgresql")
TYPE_ALIASES = {"postgres": "postgresql", "mariadb": "mysql"}
DEFAULT_PORTS = {"mysql": 3306, "postgresql": 5432}
DRIVERS = {"mysql": "mysql+pymysql", "postgresql": "postgresql+psycopg"}


@dataclass(frozen=True)
class DatabaseSettings:
    type: str
    url: URL
    sqlite_path: Optional[Path]
    raw: Dict[str, Any]


def _database_block(config: Dict[str, Any]) -> Dict[str, Any]:
    raw = config.get("database")
    if raw is None:
        return {"type": "sqlite"}
    if not isinstance(raw, dict):
        raise DatabaseError("config.json database must be an object or null")
    block = dict(raw)
    if "password" in block or "url" in block:
        raise DatabaseError(
            "database.password and database.url are not supported; "
            "use structured fields and password_env"
        )
    db_type = str(block.get("type") or "sqlite").lower()
    db_type = TYPE_ALIASES.get(db_type, db_type)
    if db_type not in SUPPORTED_TYPES:
        raise DatabaseError(
            "unsupported database.type %r; supported: sqlite, mysql, postgresql"
            % block.get("type")
        )
    block["type"] = db_type
    return block


def _required_text(block: Dict[str, Any], key: str) -> str:
    value = block.get(key)
    if value is None or not str(value).strip():
        raise DatabaseError(
            "database.%s is required for %s" % (key, block["type"])
        )
    return str(value)


def _database_name(block: Dict[str, Any]) -> str:
    value = block.get("database")
    if value is None:
        value = block.get("name")
    if value is None or not str(value).strip():
        raise DatabaseError(
            "database.database (or database.name) is required for %s"
            % block["type"]
        )
    return str(value)


def _port(block: Dict[str, Any]) -> int:
    raw = block.get("port")
    if raw is None:
        return DEFAULT_PORTS[block["type"]]
    if isinstance(raw, bool):
        raise DatabaseError("database.port must be an integer")
    try:
        port = int(raw)
    except (TypeError, ValueError):
        raise DatabaseError("database.port must be an integer")
    if not 1 <= port <= 65535:
        raise DatabaseError("database.port must be between 1 and 65535")
    return port


def _password(block: Dict[str, Any]) -> Tuple[str, str]:
    env_name = block.get("password_env")
    if env_name is None:
        env_name = DEFAULT_PASSWORD_ENV
    env_name = str(env_name)
    if not env_name:
        raise DatabaseError("database.password_env must not be empty")
    if env_name not in os.environ:
        raise DatabaseError(
            "environment variable %s is not set; set it to the database "
            "password (passwords are never read from config.json)" % env_name
        )
    return env_name, os.environ[env_name]


def _sqlite_path(raw_path: str, config: Dict[str, Any]) -> Path:
    candidate = Path(os.path.expanduser(raw_path))
    if candidate.is_absolute():
        return candidate
    workspace = config.get("workspace")
    if isinstance(workspace, str) and workspace:
        return Path(os.path.expanduser(workspace)) / candidate
    return candidate


def resolve_database(
    config: Dict[str, Any], db_override: Optional[str] = None
) -> DatabaseSettings:
    """Resolve config into a SQLAlchemy URL without opening a connection."""
    block = _database_block(config)
    db_type = block["type"]

    if db_type == "sqlite":
        configured = block.get("path")
        if db_override is not None:
            if not str(db_override).strip():
                raise DatabaseError("--db must not be empty")
            override = Path(os.path.expanduser(str(db_override)))
            if configured:
                configured_path = _sqlite_path(str(configured), config)
                if override.resolve() != configured_path.resolve():
                    raise DatabaseError(
                        "--db does not match config.json database.path"
                    )
            db_path = override
            raw_path = str(db_override)
        else:
            raw_path = str(configured) if configured else DEFAULT_SQLITE_PATH
            db_path = _sqlite_path(raw_path, config)

        sqlite_path = db_path.resolve()
        url = URL.create(
            "sqlite", database=str(sqlite_path).replace("\\", "/")
        )
        raw = {"type": "sqlite", "path": raw_path}
        return DatabaseSettings(
            type="sqlite", url=url, sqlite_path=sqlite_path, raw=raw
        )

    if db_override is not None:
        raise DatabaseError(
            "--db is only supported for sqlite; configure other databases "
            "in config.json"
        )

    host = _required_text(block, "host")
    user = _required_text(block, "user")
    name = _database_name(block)
    port = _port(block)
    password_env, password = _password(block)

    block["port"] = port
    block["password_env"] = password_env

    if db_type == "mysql":
        url = URL.create(
            DRIVERS[db_type],
            username=user,
            password=password,
            host=host,
            port=port,
            database=name,
            query={"charset": "utf8mb4"},
        )
    else:
        url = URL.create(
            DRIVERS[db_type],
            username=user,
            password=password,
            host=host,
            port=port,
            database=name,
        )
    return DatabaseSettings(type=db_type, url=url, sqlite_path=None, raw=block)


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def build_engine(
    config: Dict[str, Any], db_override: Optional[str] = None
) -> Tuple[Engine, DatabaseSettings]:
    """Create an engine; the database is not contacted until first use."""
    settings = resolve_database(config, db_override)
    engine_kwargs: Dict[str, Any] = {
        "future": True,
        "pool_pre_ping": True,
    }
    if settings.type == "sqlite":
        engine_kwargs["connect_args"] = {"timeout": 30}
    try:
        engine = create_engine(settings.url, **engine_kwargs)
    except ImportError as exc:
        raise DatabaseError(
            "database driver for %s is not installed: %s; install "
            "scripts/database/requirements.txt" % (settings.type, exc)
        )
    if settings.type == "sqlite":
        _enable_sqlite_foreign_keys(engine)
    return engine, settings


def create_schema(engine: Engine) -> None:
    models.create_schema(engine)


def relative_db_path(db_path: Path, config: Dict[str, Any]) -> str:
    workspace = config.get("workspace")
    base = None
    if isinstance(workspace, str) and workspace:
        base = Path(os.path.abspath(os.path.expanduser(workspace)))
    if base is not None:
        try:
            rel = os.path.relpath(str(db_path.resolve()), str(base))
            if not rel.startswith(".."):
                return rel.replace("\\", "/")
        except ValueError:
            pass
    return str(db_path.resolve()).replace("\\", "/")


def build_config_update(
    config: Dict[str, Any], settings: DatabaseSettings
) -> Dict[str, Any]:
    new_config = dict(config)
    new_config["log_storage"] = "database"
    if settings.type == "sqlite":
        if settings.sqlite_path is None:
            raise DatabaseError("sqlite database path is not resolved")
        new_config["database"] = {
            "type": "sqlite",
            "path": relative_db_path(settings.sqlite_path, config),
        }
    else:
        raw = dict(settings.raw)
        raw.pop("password", None)
        raw.pop("url", None)
        new_config["database"] = raw
    return new_config


def database_config_hint(
    settings: DatabaseSettings, config: Dict[str, Any]
) -> str:
    if settings.type == "sqlite":
        if settings.sqlite_path is None:
            raise DatabaseError("sqlite database path is not resolved")
        return (
            'set config.json log_storage="database" and database='
            '{"type": "sqlite", "path": "%s"}'
            % relative_db_path(settings.sqlite_path, config)
        )
    return (
        'set config.json log_storage="database" '
        "(the database connection block is already configured)"
    )
