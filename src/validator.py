"""Validation + cross-source normalization — the data-integrity centerpiece.

This is literally the Mindrift job description: "cross-source consistency controls,
adherence to formatting specifications, and systematic verification prior to delivery."

The team-name alias map is what lets us reconcile the same team across FBref,
Sofascore, etc. (e.g. "Korea Republic" vs "South Korea").
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger("validator")

# Canonical team names keyed by lowercased source spellings.
# Extend this as new sources introduce new spellings — that IS the normalization work.
TEAM_ALIASES: dict[str, str] = {
    "korea republic": "South Korea",
    "south korea": "South Korea",
    "korea dpr": "North Korea",
    "ir iran": "Iran",
    "iran": "Iran",
    "usa": "United States",
    "united states": "United States",
    "usmnt": "United States",
    "czechia": "Czech Republic",
    "czech republic": "Czech Republic",
    "türkiye": "Turkey",
    "turkiye": "Turkey",
    "turkey": "Turkey",
    "côte d'ivoire": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast",
    "ivory coast": "Ivory Coast",
    "china pr": "China",
    "bosnia and herzegovina": "Bosnia",
    "cabo verde": "Cape Verde",
}


def normalize_team_name(name: str | None) -> str | None:
    """Return a canonical team name, or None if unusable."""
    if not name:
        return None
    cleaned = re.sub(r"\s+", " ", name).strip()
    if not cleaned:
        return None
    return TEAM_ALIASES.get(cleaned.lower(), cleaned)


def _to_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


TEAM_STATS_INT_FIELDS = ("games", "wins", "draws", "losses", "goals_for", "goals_against")


def validate_team_stat(record: dict) -> tuple[dict, list[str]]:
    """Coerce + validate one team-stats record.

    Returns (cleaned_record, errors). Never raises — a bad row logs and is skipped
    upstream, so one broken row can't kill a scheduled run.
    """
    errors: list[str] = []
    out = dict(record)

    canonical = normalize_team_name(out.get("team"))
    if canonical is None:
        errors.append("missing/blank required field: team")
    out["canonical_team"] = canonical

    for field in TEAM_STATS_INT_FIELDS:
        raw = out.get(field)
        coerced = _to_int(raw)
        if raw is not None and coerced is None:
            errors.append(f"non-numeric {field}: {raw!r}")
        if coerced is not None and coerced < 0:
            errors.append(f"negative {field}: {coerced}")
        out[field] = coerced

    return out, errors
