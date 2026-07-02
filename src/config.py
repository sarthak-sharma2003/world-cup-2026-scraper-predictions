"""Load the config-driven source definitions."""
from __future__ import annotations

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sources.yaml"


def load_config(path: Path | str = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
