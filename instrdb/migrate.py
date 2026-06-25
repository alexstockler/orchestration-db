"""Load all data/*.yaml files into the SQLite database.

Usage:
    python -m instrdb.migrate              # loads data/ into orchestration.db
    python -m instrdb.migrate --db my.db  # custom database path
    python -m instrdb.migrate --reset     # wipe and reload from scratch

The migration is idempotent: re-running skips works already in the DB.
Use --reset to do a full reload (e.g. after a schema change).
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import yaml

from .db import DB_PATH, init_db
from .model import Instrumentation
from . import vocab

DATA_DIR = Path("data")


def _composer_slug(name: str) -> str:
    last = name.split(",")[0].strip() if "," in name else name
    ascii_last = unicodedata.normalize("NFKD", last).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_last.lower()).strip("-")


def _parse_year(raw) -> tuple[int | None, int | None]:
    """Return (year_start, year_end). Handles '1862', '1985-88', '1876–1877'."""
    if raw is None:
        return None, None
    s = str(raw).strip()
    m = re.match(r"(\d{4})[–\-](\d{2,4})$", s)
    if m:
        y1 = int(m.group(1))
        y2_raw = m.group(2)
        y2 = int(str(y1)[:2] + y2_raw) if len(y2_raw) == 2 else int(y2_raw)
        return y1, y2
    m = re.search(r"\b(1[5-9]\d\d|20[012]\d)\b", s)
    return (int(m.group(1)), None) if m else (None, None)


def _get_or_create_composer(conn, name: str) -> int:
    row = conn.execute("SELECT id FROM composers WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO composers (name, slug) VALUES (?, ?)",
        (name, _composer_slug(name)),
    )
    return cur.lastrowid


def _insert_instruments(conn, work_id: int, instr: Instrumentation) -> None:
    rows: list[tuple] = []

    for fam in vocab.WOODWIND_FAMILIES:
        players = getattr(instr, fam)
        if not players:
            continue
        primary_count = sum(1 for p in players if not p.instrument)
        dedicated: dict[str, int] = {}
        doublings: set[str] = set()
        for p in players:
            if p.instrument:
                dedicated[p.instrument] = dedicated.get(p.instrument, 0) + 1
            doublings.update(p.doublings)
        if primary_count:
            rows.append((work_id, fam, "woodwind", primary_count, 0))
        for aux, cnt in dedicated.items():
            rows.append((work_id, aux, "woodwind", cnt, 0))
        for d in doublings:
            rows.append((work_id, d, "woodwind", None, 1))

    for fam in vocab.BRASS_FAMILIES:
        players = getattr(instr, fam)
        if not players:
            continue
        primary_count = sum(1 for p in players if not p.instrument)
        dedicated: dict[str, int] = {}
        doublings: set[str] = set()
        for p in players:
            if p.instrument:
                dedicated[p.instrument] = dedicated.get(p.instrument, 0) + 1
            doublings.update(p.doublings)
        if primary_count:
            rows.append((work_id, fam, "brass", primary_count, 0))
        for aux, cnt in dedicated.items():
            rows.append((work_id, aux, "brass", cnt, 0))
        for d in doublings:
            rows.append((work_id, d, "brass", None, 1))

    for kp in instr.keyboards:
        rows.append((work_id, kp.instrument, "keyboard", 1, 0))
        for d in kp.doublings:
            rows.append((work_id, d, "keyboard", None, 1))

    for ex in instr.extras:
        rows.append((work_id, ex.instrument, "extra", 1, 0))

    for sax in instr.saxophones:
        if isinstance(sax, dict):
            inst = sax.get("instrument", "saxophone")
            cnt = sax.get("count", 1)
        else:
            inst, cnt = "saxophone", 1
        rows.append((work_id, inst, "saxophone", cnt, 0))

    conn.executemany(
        """INSERT INTO work_instruments
           (work_id, instrument, family, player_count, is_doubling)
           VALUES (?, ?, ?, ?, ?)""",
        rows,
    )


def load_file(path: Path, conn) -> bool:
    """Insert one YAML file into the DB. Returns True if inserted, False if already present."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not raw:
        return False

    slug = raw.get("id") or path.stem
    if conn.execute("SELECT id FROM works WHERE slug = ?", (slug,)).fetchone():
        return False

    work_data = raw.get("work") or {}
    composer_name = work_data.get("composer") or "Unknown"
    composer_id = _get_or_create_composer(conn, composer_name)

    year_start, year_end = _parse_year(work_data.get("year"))
    version = raw.get("version") or {}
    instr = Instrumentation.from_obj(raw.get("instrumentation") or {})

    strings = instr.strings
    has_strings = 1 if strings else 0
    strings_desc = strings.description if strings and strings.description else None
    has_continuo = 1 if (strings and strings.continuo) else 0

    cur = conn.execute(
        """INSERT INTO works
           (slug, composer_id, title, catalog, year_start, year_end,
            duration_minutes, formula, has_strings, strings_description,
            has_continuo, timpani, perc_players, harp,
            publisher, publisher_label, additional_raw, chorus_raw, offstage)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            slug,
            composer_id,
            work_data.get("title") or slug,
            work_data.get("catalog"),
            year_start,
            year_end,
            raw.get("duration_minutes"),
            raw.get("formula"),
            has_strings,
            strings_desc,
            has_continuo,
            instr.percussion.timpani,
            instr.percussion.players,
            instr.harp,
            version.get("publisher"),
            version.get("label"),
            instr.additional_raw or None,
            instr.chorus_raw or None,
            instr.offstage or None,
        ),
    )
    work_id = cur.lastrowid

    for source, ext_id in (work_data.get("ids") or {}).items():
        if ext_id is not None:
            conn.execute(
                "INSERT INTO work_external_ids (work_id, source, external_id) VALUES (?,?,?)",
                (work_id, source, str(ext_id)),
            )

    _insert_instruments(conn, work_id, instr)

    prov = raw.get("provenance") or {}
    if prov:
        conn.execute(
            """INSERT INTO work_provenance
               (work_id, source, source_url, confidence, notes)
               VALUES (?,?,?,?,?)""",
            (
                work_id,
                prov.get("source"),
                prov.get("source_url"),
                prov.get("confidence"),
                prov.get("notes"),
            ),
        )

    return True


def main():
    ap = argparse.ArgumentParser(description="Migrate YAML data files into SQLite")
    ap.add_argument("--db", default=str(DB_PATH), help="SQLite database path")
    ap.add_argument("--data", default=str(DATA_DIR), help="Data directory (default: data/)")
    ap.add_argument("--reset", action="store_true",
                    help="Delete the database and reload from scratch")
    args = ap.parse_args()

    db_path = Path(args.db)
    data_dir = Path(args.data)

    if args.reset and db_path.exists():
        db_path.unlink()
        print(f"Deleted {db_path}")

    conn = init_db(db_path)
    print(f"Database: {db_path.resolve()}")

    files = sorted(data_dir.glob("*.yaml"))
    if not files:
        print(f"No YAML files found in {data_dir}", file=sys.stderr)
        sys.exit(1)

    inserted = skipped = errors = 0
    for f in files:
        try:
            with conn:
                if load_file(f, conn):
                    inserted += 1
                else:
                    skipped += 1
        except Exception as exc:
            print(f"  [error] {f.name}: {exc}", file=sys.stderr)
            errors += 1

    print(f"Done: {inserted} inserted, {skipped} skipped, {errors} errors.")
    conn.close()


if __name__ == "__main__":
    main()
