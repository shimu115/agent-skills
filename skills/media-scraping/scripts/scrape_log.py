#!/usr/bin/env python3
"""Generate, validate, and migrate media-scraping Markdown logs.

Log generation and validation use only the Python standard library.  The
``migrate`` command lazily imports ``scripts/database/`` and therefore
requires SQLAlchemy plus the driver for the target database.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LOG_SCHEMA = "media-scraping-log/v1"
RUN_ID_RE = re.compile(r"^\d{8}-\d{6}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
HEADER = ["seq", "action", "media_type", "status", "source_path", "target_path", "note"]
ACTIONS = {"rename", "hardlink", "move", "backup", "skip", "review", "error"}
MEDIA_TYPES = {
    "movie", "tv", "anime", "anime_movie", "special", "subtitle",
    "danmaku", "artwork", "metadata", "music", "other",
}
STATUSES = {"done", "skipped", "needs_review", "error"}
SUMMARY_KEYS = (
    "summary_added", "summary_skipped", "summary_needs_review", "summary_errors",
)
REQUIRED_KEYS = (
    "log_schema", "run_id", "started_at", "finished_at", "workspace",
    "mode", "library",
) + SUMMARY_KEYS
SUMMARY_LABELS = {
    "summary_added": "Added",
    "summary_skipped": "Skipped",
    "summary_needs_review": "Needs Manual Review",
    "summary_errors": "Errors",
}

class ToolError(Exception):
    pass


@dataclass
class Record:
    seq: int
    action: str
    media_type: str
    status: str
    source_path: Optional[str]
    target_path: Optional[str]
    note: str


@dataclass
class LogDoc:
    path: Path
    lines: List[str]
    frontmatter: Dict[str, Any]
    fm_start: int
    fm_end: int
    records_heading: int
    table_header: int
    table_end: int
    summary_heading: Optional[int]
    records: List[Record]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text_atomic(path: Path, text: str) -> None:
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


def render_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ToolError("frontmatter values must be single-line")
    return "'" + text.replace("'", "''") + "'"


def escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_path(value: Optional[str]) -> str:
    if value is None:
        return "-"
    return "`" + escape_cell(value) + "`"


def render_table(records: List[Record]) -> List[str]:
    lines = [
        "| " + " | ".join(HEADER) + " |",
        "| " + " | ".join(["---"] * len(HEADER)) + " |",
    ]
    for record in records:
        lines.append("| " + " | ".join([
            str(record.seq),
            record.action,
            record.media_type,
            record.status,
            render_path(record.source_path),
            render_path(record.target_path),
            escape_cell(record.note),
        ]) + " |")
    return lines


def split_row(line: str) -> List[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    cells: List[str] = []
    current: List[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text) and text[i + 1] == "|":
            current.append("|")
            i += 2
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            i += 1
            continue
        current.append(char)
        i += 1
    cells.append("".join(current).strip())
    return cells


def is_separator(line: str, columns: int) -> bool:
    cells = split_row(line)
    return len(cells) == columns and all(
        re.fullmatch(r":?-{3,}:?", cell) for cell in cells
    )


def parse_scalar(raw: str, path: Path, line_number: int) -> Any:
    if raw == "null":
        return None
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    raise ToolError(
        "%s:%d: string values must be single-quoted: %r" % (path, line_number, raw)
    )


def parse_path(cell: str, path: Path, line_number: int, name: str) -> Optional[str]:
    if cell == "-":
        return None
    if len(cell) < 2 or not (cell.startswith("`") and cell.endswith("`")):
        raise ToolError(
            "%s:%d: %s must be wrapped in backticks or be '-'" % (path, line_number, name)
        )
    value = cell[1:-1]
    if "`" in value:
        raise ToolError(
            "%s:%d: %s must not contain a backtick" % (path, line_number, name)
        )
    if not value.strip():
        raise ToolError("%s:%d: %s must not be empty" % (path, line_number, name))
    return value


def parse_record(cells: List[str], path: Path, line_number: int) -> Record:
    seq_raw, action, media_type, status, source, target, note = cells
    if not re.fullmatch(r"\d+", seq_raw):
        raise ToolError("%s:%d: seq must be a positive integer" % (path, line_number))
    seq = int(seq_raw)
    if seq < 1:
        raise ToolError("%s:%d: seq must be a positive integer" % (path, line_number))
    if action not in ACTIONS:
        raise ToolError(
            "%s:%d: action %r is not one of %s"
            % (path, line_number, action, ", ".join(sorted(ACTIONS)))
        )
    if media_type not in MEDIA_TYPES:
        raise ToolError(
            "%s:%d: media_type %r is not one of %s"
            % (path, line_number, media_type, ", ".join(sorted(MEDIA_TYPES)))
        )
    if status not in STATUSES:
        raise ToolError(
            "%s:%d: status %r is not one of %s"
            % (path, line_number, status, ", ".join(sorted(STATUSES)))
        )
    return Record(
        seq=seq,
        action=action,
        media_type=media_type,
        status=status,
        source_path=parse_path(source, path, line_number, "source_path"),
        target_path=parse_path(target, path, line_number, "target_path"),
        note=note,
    )


def parse_frontmatter(lines: List[str], start: int, end: int, path: Path) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    for i in range(start + 1, end):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in raw:
            raise ToolError(
                "%s:%d: invalid frontmatter line (expected key: value)" % (path, i + 1)
            )
        key, value = raw.split(":", 1)
        key = key.strip()
        if not key:
            raise ToolError("%s:%d: empty frontmatter key" % (path, i + 1))
        if key in values:
            raise ToolError("%s:%d: duplicate frontmatter key %r" % (path, i + 1, key))
        values[key] = parse_scalar(value.strip(), path, i + 1)
    return values


def parse_log_text(path: Path, text: str) -> LogDoc:
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ToolError("%s: missing YAML frontmatter (first line must be ---)" % path)
    fm_end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_end = i
            break
    if fm_end is None:
        raise ToolError("%s: unterminated YAML frontmatter" % path)
    frontmatter = parse_frontmatter(lines, 0, fm_end, path)

    heading_lines = [
        i for i, line in enumerate(lines) if re.fullmatch(r"## Records[ \t]*", line)
    ]
    if len(heading_lines) != 1:
        raise ToolError(
            "%s: expected exactly one line-start '## Records' heading, found %d"
            % (path, len(heading_lines))
        )
    records_heading = heading_lines[0]
    cursor = records_heading + 1
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    if cursor >= len(lines) or not lines[cursor].lstrip().startswith("|"):
        raise ToolError(
            "%s:%d: '## Records' must be followed by the table header"
            % (path, records_heading + 1)
        )
    table_header = cursor
    if split_row(lines[table_header]) != HEADER:
        raise ToolError(
            "%s:%d: table header must be: | %s |"
            % (path, table_header + 1, " | ".join(HEADER))
        )
    separator = table_header + 1
    if separator >= len(lines) or not is_separator(lines[separator], len(HEADER)):
        raise ToolError(
            "%s:%d: missing table separator row" % (path, separator + 1)
        )
    cursor = separator + 1
    records: List[Record] = []
    while cursor < len(lines) and lines[cursor].lstrip().startswith("|"):
        cells = split_row(lines[cursor])
        if len(cells) != len(HEADER):
            raise ToolError(
                "%s:%d: table row has %d columns, expected %d"
                % (path, cursor + 1, len(cells), len(HEADER))
            )
        records.append(parse_record(cells, path, cursor + 1))
        cursor += 1
    table_end = cursor
    seqs = [record.seq for record in records]
    if seqs != list(range(1, len(records) + 1)):
        raise ToolError(
            "%s: seq must start at 1 and be contiguous; got %s" % (path, seqs)
        )

    next_heading = None
    for i in range(table_end, len(lines)):
        if re.fullmatch(r"## .+", lines[i]):
            next_heading = i
            break
    summary_heading = None
    if next_heading is not None and re.fullmatch(r"## Summary[ \t]*", lines[next_heading]):
        summary_heading = next_heading
    return LogDoc(
        path=path,
        lines=lines,
        frontmatter=frontmatter,
        fm_start=0,
        fm_end=fm_end,
        records_heading=records_heading,
        table_header=table_header,
        table_end=table_end,
        summary_heading=summary_heading,
        records=records,
    )


def parse_summary(doc: LogDoc) -> Tuple[Optional[Dict[str, int]], List[str]]:
    if doc.summary_heading is None:
        return None, []
    start = doc.summary_heading + 1
    end = len(doc.lines)
    for i in range(start, len(doc.lines)):
        if re.fullmatch(r"## .+", doc.lines[i]):
            end = i
            break
    values: Dict[str, int] = {}
    errors: List[str] = []
    for i in range(start, end):
        match = re.fullmatch(
            r"- (Added|Skipped|Needs Manual Review|Errors): (\d+)", doc.lines[i].strip()
        )
        if not match:
            continue
        label = match.group(1)
        if label in values:
            errors.append("## Summary has duplicate '%s'" % label)
        else:
            values[label] = int(match.group(2))
    return values, errors


def validate_doc(doc: LogDoc, require_finished: bool = False) -> List[str]:
    errors: List[str] = []
    fm = doc.frontmatter
    for key in REQUIRED_KEYS:
        if key not in fm:
            errors.append("frontmatter missing key: %s" % key)
    for key in sorted(set(fm) - set(REQUIRED_KEYS)):
        errors.append("unknown frontmatter key: %s" % key)

    if fm.get("log_schema") != LOG_SCHEMA:
        errors.append("log_schema must be %r" % LOG_SCHEMA)
    run_id = fm.get("run_id")
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        errors.append("run_id must be a quoted YYYYMMDD-HHmmss string")
    started_at = fm.get("started_at")
    if not isinstance(started_at, str) or not TIMESTAMP_RE.fullmatch(started_at):
        errors.append("started_at must be a quoted YYYY-MM-DD HH:MM:SS string")
    finished_at = fm.get("finished_at")
    if finished_at is not None:
        if not isinstance(finished_at, str) or not TIMESTAMP_RE.fullmatch(finished_at):
            errors.append("finished_at must be null or a quoted YYYY-MM-DD HH:MM:SS string")
    elif require_finished:
        errors.append("finished_at is null (run is not finished)")
    workspace = fm.get("workspace")
    if not isinstance(workspace, str) or not workspace:
        errors.append("workspace must be a non-empty quoted string")
    mode = fm.get("mode")
    if mode not in ("in_place", "ingest"):
        errors.append("mode must be 'in_place' or 'ingest'")
    library = fm.get("library")
    if mode == "in_place":
        if library is not None:
            errors.append("library must be null when mode is in_place")
    elif mode == "ingest":
        if not isinstance(library, str) or not library:
            errors.append("library must be a non-empty quoted path when mode is ingest")
    for key in SUMMARY_KEYS:
        if key not in fm:
            continue
        value = fm.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append("%s must be a non-negative integer" % key)

    if isinstance(run_id, str) and doc.path.suffix.lower() == ".md" and doc.path.stem != run_id:
        errors.append("filename must be %s.md" % run_id)

    summary, summary_errors = parse_summary(doc)
    errors.extend(summary_errors)
    if summary is not None:
        for key, label in SUMMARY_LABELS.items():
            if label not in summary:
                errors.append("## Summary missing '- %s: <n>'" % label)
            elif key in fm and summary[label] != fm[key]:
                errors.append(
                    "## Summary %s=%d does not match frontmatter %s=%r"
                    % (label, summary[label], key, fm[key])
                )
    return errors


def classify_log(path: Path, require_finished: bool = False) -> Tuple[str, Any]:
    try:
        text = read_text(path)
    except (OSError, UnicodeDecodeError) as exc:
        return "invalid", ["cannot read file: %s" % exc]
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "legacy", "no YAML frontmatter"
    close = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close = i
            break
    if close is None:
        return "invalid", ["unterminated YAML frontmatter"]
    schema = None
    for i in range(1, close):
        stripped = lines[i].strip()
        if stripped.startswith("log_schema:"):
            raw = stripped.split(":", 1)[1].strip()
            if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
                schema = raw[1:-1].replace("''", "'")
            else:
                schema = raw
            break
    if schema != LOG_SCHEMA:
        return "legacy", "log_schema is %r, not %r" % (schema, LOG_SCHEMA)
    try:
        doc = parse_log_text(path, text)
    except ToolError as exc:
        return "invalid", [str(exc)]
    errors = validate_doc(doc, require_finished=require_finished)
    if errors:
        return "invalid", errors
    return "valid", doc


def load_config(path: str) -> Dict[str, Any]:
    config_path = Path(path)
    try:
        with open(config_path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError("cannot read config %s: %s" % (config_path, exc))
    if not isinstance(data, dict):
        raise ToolError("config must be a JSON object: %s" % config_path)
    return data


def normalize_path_arg(value: Optional[str], name: str) -> Optional[str]:
    if value is None:
        raise ToolError("%s is required; use '-' for none" % name)
    if value == "-":
        return None
    if not value.strip():
        raise ToolError("%s must not be empty" % name)
    if "\n" in value or "\r" in value:
        raise ToolError("%s must be a single line" % name)
    if "`" in value:
        raise ToolError("%s must not contain a backtick" % name)
    return value


def cmd_init(args: argparse.Namespace) -> int:
    config: Dict[str, Any] = load_config(args.config) if args.config else {}
    if config.get("log_storage") not in (None, "markdown"):
        raise ToolError(
            "config.json log_storage is not 'markdown'; refusing to create a Markdown log"
        )
    workspace = args.workspace or config.get("workspace")
    if not workspace:
        raise ToolError("--workspace is required (or provide --config with workspace)")
    mode = args.mode
    if mode is None and "ingest" in config:
        mode = "ingest" if config.get("ingest") else "in_place"
    if mode not in ("in_place", "ingest"):
        raise ToolError("--mode is required (or provide --config with ingest)")
    library = args.library
    if mode == "ingest" and library is None and config:
        library = config.get("jellyfin_library")
    workspace_abs = os.path.abspath(os.path.expanduser(str(workspace)))
    if mode == "in_place":
        if library is not None:
            raise ToolError("library must not be set when mode is in_place")
        library_abs = None
    else:
        if not library:
            raise ToolError("library is required when mode is ingest")
        library_abs = os.path.abspath(os.path.expanduser(str(library)))
    for label, value in (("workspace", workspace_abs), ("library", library_abs)):
        if value is not None and ("\n" in value or "\r" in value):
            raise ToolError("%s must be a single line" % label)

    now = datetime.now()
    if args.run_id:
        run_id = args.run_id
        if not RUN_ID_RE.fullmatch(run_id):
            raise ToolError("--run-id must be YYYYMMDD-HHmmss")
    else:
        run_id = now.strftime("%Y%m%d-%H%M%S")
    if args.started_at:
        started_at = args.started_at
    elif args.run_id:
        try:
            started_at = datetime.strptime(run_id, "%Y%m%d-%H%M%S").strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except ValueError:
            raise ToolError("--run-id must be YYYYMMDD-HHmmss")
    else:
        started_at = now.strftime("%Y-%m-%d %H:%M:%S")
    if not TIMESTAMP_RE.fullmatch(started_at):
        raise ToolError("--started-at must be YYYY-MM-DD HH:MM:SS")

    doc_dir = Path(args.doc_dir) if args.doc_dir else Path(workspace_abs) / "doc"
    log_path = doc_dir / (run_id + ".md")
    if log_path.exists():
        raise ToolError("log already exists: %s" % log_path)
    lines = [
        "---",
        "log_schema: " + render_scalar(LOG_SCHEMA),
        "run_id: " + render_scalar(run_id),
        "started_at: " + render_scalar(started_at),
        "finished_at: null",
        "workspace: " + render_scalar(workspace_abs),
        "mode: " + render_scalar(mode),
        "library: " + render_scalar(library_abs),
        "summary_added: 0",
        "summary_skipped: 0",
        "summary_needs_review: 0",
        "summary_errors: 0",
        "---",
        "",
        "# Scrape Log: " + run_id,
        "",
        "## Records",
        "",
        "| " + " | ".join(HEADER) + " |",
        "| " + " | ".join(["---"] * len(HEADER)) + " |",
        "",
        "## Summary",
        "",
        "- Added: 0",
        "- Skipped: 0",
        "- Needs Manual Review: 0",
        "- Errors: 0",
        "",
        "## Notes",
        "",
    ]
    text = "\n".join(lines) + "\n"
    parsed = parse_log_text(log_path, text)
    errors = validate_doc(parsed)
    if errors:
        raise ToolError("internal template validation failed: " + "; ".join(errors))
    write_text_atomic(log_path, text)
    print("log_path=%s" % log_path)
    print("run_id=%s" % run_id)
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    log_path = Path(args.log)
    if not log_path.exists():
        raise ToolError("log not found: %s" % log_path)
    text = read_text(log_path)
    doc = parse_log_text(log_path, text)
    errors = validate_doc(doc)
    if errors:
        raise ToolError("log is invalid: " + "; ".join(errors))
    if doc.frontmatter.get("finished_at") is not None:
        raise ToolError("log is already finished; add is not allowed")

    source = normalize_path_arg(args.source, "--source")
    target = normalize_path_arg(args.target, "--target")
    note = (args.note or "").replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    record = Record(
        seq=len(doc.records) + 1,
        action=args.action,
        media_type=args.media_type,
        status=args.status,
        source_path=source,
        target_path=target,
        note=note,
    )
    records = doc.records + [record]
    new_lines = doc.lines[:doc.table_header] + render_table(records) + doc.lines[doc.table_end:]
    new_text = "\n".join(new_lines) + "\n"
    new_doc = parse_log_text(log_path, new_text)
    new_errors = validate_doc(new_doc)
    if new_errors:
        raise ToolError("internal validation failed: " + "; ".join(new_errors))
    write_text_atomic(log_path, new_text)
    print("seq=%d" % record.seq)
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    log_path = Path(args.log)
    if not log_path.exists():
        raise ToolError("log not found: %s" % log_path)
    text = read_text(log_path)
    doc = parse_log_text(log_path, text)
    errors = validate_doc(doc)
    if errors:
        raise ToolError("log is invalid: " + "; ".join(errors))
    if doc.frontmatter.get("finished_at") is not None:
        raise ToolError("log is already finished")

    finished_at = args.finished_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not TIMESTAMP_RE.fullmatch(finished_at):
        raise ToolError("--finished-at must be YYYY-MM-DD HH:MM:SS")
    values = {
        "summary_added": args.added,
        "summary_skipped": args.skipped,
        "summary_needs_review": args.needs_review,
        "summary_errors": args.errors,
    }
    for key, value in values.items():
        if value < 0:
            raise ToolError("--%s must be non-negative" % key.replace("_", "-"))

    lines = list(doc.lines)
    for key, value in [("finished_at", finished_at)] + list(values.items()):
        updated = False
        for i in range(doc.fm_start + 1, doc.fm_end):
            if lines[i].split(":", 1)[0].strip() == key:
                lines[i] = key + ": " + render_scalar(value)
                updated = True
                break
        if not updated:
            raise ToolError("frontmatter key not found: %s" % key)

    summary_lines = [
        "## Summary",
        "",
        "- Added: %d" % values["summary_added"],
        "- Skipped: %d" % values["summary_skipped"],
        "- Needs Manual Review: %d" % values["summary_needs_review"],
        "- Errors: %d" % values["summary_errors"],
        "",
    ]
    if doc.summary_heading is not None:
        start = doc.summary_heading
        end = start + 1
        while end < len(lines) and not re.fullmatch(r"## .+", lines[end]):
            end += 1
        lines[start:end] = summary_lines
    else:
        insert_at = None
        for i in range(doc.table_end, len(lines)):
            if re.fullmatch(r"## .+", lines[i]):
                insert_at = i
                break
        if insert_at is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines.extend(summary_lines)
        else:
            prefix: List[str] = []
            if insert_at > 0 and lines[insert_at - 1].strip():
                prefix = [""]
            lines[insert_at:insert_at] = prefix + summary_lines

    new_text = "\n".join(lines) + "\n"
    new_doc = parse_log_text(log_path, new_text)
    new_errors = validate_doc(new_doc, require_finished=True)
    if new_errors:
        raise ToolError("internal validation failed: " + "; ".join(new_errors))
    write_text_atomic(log_path, new_text)
    print("finished_at=%s" % finished_at)
    print("summary_added=%d" % values["summary_added"])
    print("summary_skipped=%d" % values["summary_skipped"])
    print("summary_needs_review=%d" % values["summary_needs_review"])
    print("summary_errors=%d" % values["summary_errors"])
    return 0


def collect_log_paths(args: argparse.Namespace) -> List[Path]:
    paths: List[Path] = []
    if args.log:
        paths.extend(Path(item) for item in args.log)
    if args.doc_dir:
        doc_dir = Path(args.doc_dir)
        if not doc_dir.is_dir():
            raise ToolError("doc directory not found: %s" % doc_dir)
        paths.extend(sorted(path for path in doc_dir.glob("*.md") if path.is_file()))
    seen = set()
    unique: List[Path] = []
    for path in paths:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(path)
    if not unique:
        raise ToolError("no log files given; use --log or --doc-dir")
    return unique


def cmd_validate(args: argparse.Namespace) -> int:
    failed = 0
    for path in collect_log_paths(args):
        kind, payload = classify_log(path, require_finished=args.require_finished)
        if kind == "valid":
            print("OK: %s (%d records)" % (path, len(payload.records)))
        elif kind == "legacy":
            print("LEGACY: %s: %s" % (path, payload))
        else:
            failed += 1
            print("ERROR: %s" % path)
            for error in payload:
                print("  - %s" % error)
    if failed:
        print("FAILED: %d file(s)" % failed)
        return 1
    print("OK: no invalid v1 logs")
    return 0


def _migration_doc(doc: LogDoc, migration_doc_cls: Any) -> Any:
    fm = doc.frontmatter
    return migration_doc_cls(
        path=doc.path,
        run={
            "run_id": fm["run_id"],
            "started_at": fm["started_at"],
            "finished_at": fm["finished_at"],
            "workspace": fm["workspace"],
            "mode": fm["mode"],
            "library_path": fm["library"],
            "summary_added": fm["summary_added"],
            "summary_skipped": fm["summary_skipped"],
            "summary_needs_review": fm["summary_needs_review"],
            "summary_errors": fm["summary_errors"],
        },
        items=[
            {
                "run_id": fm["run_id"],
                "seq": record.seq,
                "action": record.action,
                "media_type": record.media_type,
                "source_path": record.source_path,
                "target_path": record.target_path,
                "status": record.status,
                "note": record.note or None,
                "created_at": fm["started_at"],
            }
            for record in doc.records
        ],
    )


def cmd_migrate(args: argparse.Namespace) -> int:
    config: Dict[str, Any] = load_config(args.config) if args.config else {}

    doc_dir = Path(args.doc_dir)
    if not doc_dir.is_dir():
        raise ToolError("doc directory not found: %s" % doc_dir)
    logs = sorted(path for path in doc_dir.glob("*.md") if path.is_file())
    valid: List[LogDoc] = []
    legacy: List[Tuple[Path, str]] = []
    invalid: List[Tuple[Path, List[str]]] = []
    for path in logs:
        kind, payload = classify_log(path, require_finished=True)
        if kind == "valid":
            valid.append(payload)
        elif kind == "legacy":
            legacy.append((path, payload))
        else:
            invalid.append((path, payload))
    if invalid:
        print("ERROR: migration aborted; invalid v1 logs found:", file=sys.stderr)
        for path, errors in invalid:
            print("  %s" % path, file=sys.stderr)
            for error in errors:
                print("    - %s" % error, file=sys.stderr)
        return 1

    print("Found: %d md file(s)" % len(logs))
    print("  valid: %d" % len(valid))
    print("  legacy (skipped): %d" % len(legacy))

    try:
        from database import DatabaseError, connection, migration
        from sqlalchemy.exc import SQLAlchemyError
    except ImportError as exc:
        requirements = (
            Path(__file__).resolve().parent / "database" / "requirements.txt"
        )
        raise ToolError(
            "migrate requires SQLAlchemy and a database driver; install with "
            "`python -m pip install -r %s` (%s)" % (requirements, exc)
        )

    engine = None
    try:
        engine, settings = connection.build_engine(config, db_override=args.db)
        docs = [_migration_doc(doc, migration.MigrationDoc) for doc in valid]
        result = migration.migrate(
            docs,
            engine,
            settings,
            migrations_dir=(
                Path(args.migrations_dir)
                if args.migrations_dir
                else doc_dir.parent / "data" / "migrations"
            ),
            archive_dir=doc_dir / "archive",
            config_path=Path(args.config) if args.config else None,
            config=config,
            dry_run=args.dry_run,
            no_archive=args.no_archive,
        )
    except (DatabaseError, SQLAlchemyError, OSError) as exc:
        raise ToolError(str(exc))
    finally:
        if engine is not None:
            engine.dispose()

    print("  duplicate run_id (skipped): %d" % len(result.skipped))

    if result.sql_path is None:
        print("Nothing to migrate.")
        for path, reason in legacy:
            print("  legacy: %s: %s" % (path, reason))
        for doc in result.skipped:
            print("  duplicate: %s (run_id=%s)" % (doc.path, doc.run_id))
        return 0

    print("SQL: %s" % result.sql_path)
    if result.dry_run:
        print("Dry run: SQL generated, database and logs unchanged.")
        return 0

    print(
        "Imported: %d run(s), %d item(s)"
        % (result.imported_runs, result.imported_items)
    )
    if result.archived:
        print(
            "Archived: %d file(s) -> %s"
            % (len(result.archived), doc_dir / "archive")
        )
    for path, reason in legacy:
        print("Legacy skipped: %s: %s" % (path, reason))
    for doc in result.skipped:
        print("Duplicate skipped: %s (run_id=%s)" % (doc.path, doc.run_id))
    if args.config:
        print("Config updated: %s" % args.config)
    else:
        hint_config = config
        if not isinstance(hint_config.get("workspace"), str) or not hint_config.get(
            "workspace"
        ):
            hint_config = {"workspace": str(doc_dir.resolve().parent)}
        print(
            "Next: %s"
            % connection.database_config_hint(settings, hint_config)
        )
    return 0


def non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer")
    if number < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scrape_log.py",
        description="Generate, validate, and migrate media-scraping Markdown logs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a new run log")
    init_parser.add_argument("--workspace", help="workspace absolute path")
    init_parser.add_argument("--mode", choices=["in_place", "ingest"])
    init_parser.add_argument("--library", help="media library path (ingest mode)")
    init_parser.add_argument("--run-id", help="YYYYMMDD-HHmmss (default: now)")
    init_parser.add_argument("--started-at", help="YYYY-MM-DD HH:MM:SS")
    init_parser.add_argument("--doc-dir", help="default: <workspace>/doc")
    init_parser.add_argument("--config", help="read workspace/mode/library from config.json")
    init_parser.set_defaults(func=cmd_init)

    add_parser = subparsers.add_parser("add", help="append one operation to a run log")
    add_parser.add_argument("--log", required=True)
    add_parser.add_argument("--action", required=True, choices=sorted(ACTIONS))
    add_parser.add_argument("--media-type", required=True, choices=sorted(MEDIA_TYPES))
    add_parser.add_argument("--status", required=True, choices=sorted(STATUSES))
    add_parser.add_argument("--source", required=True, help="source path, or - for none")
    add_parser.add_argument("--target", required=True, help="target path, or - for none")
    add_parser.add_argument("--note", default="")
    add_parser.set_defaults(func=cmd_add)

    finish_parser = subparsers.add_parser("finish", help="finish a run log")
    finish_parser.add_argument("--log", required=True)
    finish_parser.add_argument("--finished-at", help="YYYY-MM-DD HH:MM:SS")
    finish_parser.add_argument("--added", type=non_negative_int, required=True)
    finish_parser.add_argument("--skipped", type=non_negative_int, required=True)
    finish_parser.add_argument("--needs-review", type=non_negative_int, required=True)
    finish_parser.add_argument("--errors", type=non_negative_int, required=True)
    finish_parser.set_defaults(func=cmd_finish)

    validate_parser = subparsers.add_parser("validate", help="validate run logs")
    validate_parser.add_argument("--log", action="append", help="repeatable")
    validate_parser.add_argument("--doc-dir", help="validate all *.md in this directory")
    validate_parser.add_argument("--require-finished", action="store_true")
    validate_parser.set_defaults(func=cmd_validate)

    migrate_parser = subparsers.add_parser(
        "migrate",
        help="migrate v1 Markdown logs to a database",
        description=(
            "Migrate v1 Markdown logs to SQLite, MySQL, or PostgreSQL. "
            "MySQL/PostgreSQL require --config and the database drivers."
        ),
    )
    migrate_parser.add_argument("--doc-dir", default="doc")
    migrate_parser.add_argument(
        "--db", help="SQLite database path (default: data/scraping-logs.db)"
    )
    migrate_parser.add_argument(
        "--migrations-dir", help="default: <doc-dir>/../data/migrations"
    )
    migrate_parser.add_argument(
        "--config",
        help=(
            "read database settings from config.json; required for "
            "MySQL/PostgreSQL, and updated after a successful migration"
        ),
    )
    migrate_parser.add_argument("--dry-run", action="store_true")
    migrate_parser.add_argument("--no-archive", action="store_true")
    migrate_parser.set_defaults(func=cmd_migrate)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ToolError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
