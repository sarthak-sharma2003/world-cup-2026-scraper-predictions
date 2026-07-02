"""Tests for the data-integrity layer (the Mindrift centerpiece)."""
from src.validator import normalize_team_name, validate_team_stat


def test_cross_source_name_normalization():
    # Same team, different source spellings -> one canonical name.
    assert normalize_team_name("Korea Republic") == "South Korea"
    assert normalize_team_name("South Korea") == "South Korea"
    assert normalize_team_name("USA") == "United States"
    assert normalize_team_name("IR Iran") == "Iran"


def test_normalize_handles_whitespace_and_blanks():
    assert normalize_team_name("  Brazil ") == "Brazil"
    assert normalize_team_name("") is None
    assert normalize_team_name(None) is None
    # Unknown names pass through unchanged (not mangled).
    assert normalize_team_name("Argentina") == "Argentina"


def test_validate_coerces_numeric_strings():
    cleaned, errors = validate_team_stat(
        {"team": "Brazil", "games": "3", "wins": "2", "draws": "1", "losses": "0"}
    )
    assert errors == []
    assert cleaned["canonical_team"] == "Brazil"
    assert cleaned["games"] == 3 and cleaned["wins"] == 2


def test_validate_flags_bad_values_without_raising():
    cleaned, errors = validate_team_stat({"team": "", "games": "oops", "wins": "-1"})
    assert cleaned["canonical_team"] is None
    assert any("required field: team" in e for e in errors)
    assert any("non-numeric games" in e for e in errors)
    assert any("negative wins" in e for e in errors)
