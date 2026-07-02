"""SQLite storage + CSV/JSON exports.

The DB is rebuilt each run and kept out of git; the human-readable exports in
data/exports/ are what get committed (so the dashboard and any reviewer can read
the latest scraped data straight from the repo).
"""
from __future__ import annotations

import csv
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("storage")

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "wc2026.db"
EXPORT_DIR = ROOT / "data" / "exports"

SCHEMA = """
CREATE TABLE IF NOT EXISTS team_stats (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    team           TEXT NOT NULL,
    canonical_team TEXT NOT NULL,
    games          INTEGER,
    wins           INTEGER,
    draws          INTEGER,
    losses         INTEGER,
    goals_for      INTEGER,
    goals_against  INTEGER,
    source         TEXT NOT NULL,
    scraped_at     TEXT NOT NULL,
    UNIQUE(canonical_team, source)
);

CREATE TABLE IF NOT EXISTS fixtures (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    match_date    TEXT,
    home_team     TEXT,
    away_team     TEXT,
    home_score    INTEGER,
    away_score    INTEGER,
    stage         TEXT,
    status        TEXT,
    source        TEXT NOT NULL,
    scraped_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id     INTEGER,
    home_win_prob  REAL,
    draw_prob      REAL,
    away_win_prob  REAL,
    model          TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knockout_matches (
    match_no    INTEGER PRIMARY KEY,
    round       TEXT,
    round_idx   INTEGER,
    match_date  TEXT,
    venue       TEXT,
    home_ref    TEXT,
    away_ref    TEXT,
    home_team   TEXT,
    away_team   TEXT,
    home_score  INTEGER,
    away_score  INTEGER,
    home_pens   INTEGER,
    away_pens   INTEGER,
    winner      TEXT,
    home_from   INTEGER,
    away_from   INTEGER,
    status      TEXT,
    source      TEXT NOT NULL,
    scraped_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_inputs (
    team        TEXT PRIMARY KEY,
    elo         INTEGER,
    fifa_rank   INTEGER,
    xg_for      REAL,
    xg_against  REAL,
    xg_games    INTEGER,
    source      TEXT NOT NULL,
    scraped_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT NOT NULL,
    records      INTEGER,
    failures     INTEGER,
    status       TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_team_stats(conn: sqlite3.Connection, records: list[dict], source: str) -> int:
    scraped_at = _now()
    stored = 0
    for rec in records:
        params = {
            "team": rec.get("team"),
            "canonical_team": rec.get("canonical_team"),
            "games": rec.get("games"),
            "wins": rec.get("wins"),
            "draws": rec.get("draws"),
            "losses": rec.get("losses"),
            "goals_for": rec.get("goals_for"),
            "goals_against": rec.get("goals_against"),
            "source": source,
            "scraped_at": scraped_at,
        }
        conn.execute(
            """
            INSERT INTO team_stats
                (team, canonical_team, games, wins, draws, losses,
                 goals_for, goals_against, source, scraped_at)
            VALUES
                (:team, :canonical_team, :games, :wins, :draws, :losses,
                 :goals_for, :goals_against, :source, :scraped_at)
            ON CONFLICT(canonical_team, source) DO UPDATE SET
                team=excluded.team,
                games=excluded.games,
                wins=excluded.wins,
                draws=excluded.draws,
                losses=excluded.losses,
                goals_for=excluded.goals_for,
                goals_against=excluded.goals_against,
                scraped_at=excluded.scraped_at
            """,
            params,
        )
        stored += 1
    conn.commit()
    return stored


_KO_COLS = (
    "match_no", "round", "round_idx", "match_date", "venue",
    "home_ref", "away_ref", "home_team", "away_team",
    "home_score", "away_score", "home_pens", "away_pens",
    "winner", "home_from", "away_from", "status",
)


def upsert_knockout(conn: sqlite3.Connection, matches: list[dict], source: str) -> int:
    scraped_at = _now()
    placeholders = ", ".join(f":{c}" for c in _KO_COLS) + ", :source, :scraped_at"
    updates = ", ".join(f"{c}=excluded.{c}" for c in _KO_COLS if c != "match_no")
    for m in matches:
        params = {c: m.get(c) for c in _KO_COLS}
        params["source"] = source
        params["scraped_at"] = scraped_at
        conn.execute(
            f"""INSERT INTO knockout_matches ({", ".join(_KO_COLS)}, source, scraped_at)
                VALUES ({placeholders})
                ON CONFLICT(match_no) DO UPDATE SET {updates}, scraped_at=excluded.scraped_at""",
            params,
        )
    conn.commit()
    return len(matches)


_MI_COLS = ("team", "elo", "fifa_rank", "xg_for", "xg_against", "xg_games")


def upsert_model_inputs(conn: sqlite3.Connection, rows: list[dict], source: str) -> int:
    scraped_at = _now()
    placeholders = ", ".join(f":{c}" for c in _MI_COLS) + ", :source, :scraped_at"
    updates = ", ".join(f"{c}=excluded.{c}" for c in _MI_COLS if c != "team")
    for r in rows:
        params = {c: r.get(c) for c in _MI_COLS}
        params["source"] = source
        params["scraped_at"] = scraped_at
        conn.execute(
            f"""INSERT INTO model_inputs ({", ".join(_MI_COLS)}, source, scraped_at)
                VALUES ({placeholders})
                ON CONFLICT(team) DO UPDATE SET {updates}, source=excluded.source,
                    scraped_at=excluded.scraped_at""",
            params,
        )
    conn.commit()
    return len(rows)


def log_run(
    conn: sqlite3.Connection,
    source: str,
    started_at: str,
    records: int,
    failures: int,
    status: str,
) -> None:
    conn.execute(
        """INSERT INTO scrape_runs (source, started_at, finished_at, records, failures, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (source, started_at, _now(), records, failures, status),
    )
    conn.commit()


def export_table(conn: sqlite3.Connection, table: str) -> None:
    """Write <table>.json and <table>.csv into data/exports/."""
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    (EXPORT_DIR / f"{table}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    csv_path = EXPORT_DIR / f"{table}.csv"
    if rows:
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        csv_path.write_text("", encoding="utf-8")

    log.info("exported %d rows -> %s.{json,csv}", len(rows), table)
