"""Load settings from YAML, with .env support for secrets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

DEFAULT_CONFIG = Path("config/config.yaml")


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Read the YAML config and load .env into the environment."""
    load_dotenv()
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
