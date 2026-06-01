"""
Configuration Loader
====================
Loads YAML config files and resolves environment variable placeholders.
"""

import json
import os
import re
import yaml
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


class Config:
    """
    Loads and provides access to YAML configuration with
    automatic environment variable resolution.

    Environment variables are referenced in YAML as: ${VAR_NAME}
    """

    _ENV_PATTERN = re.compile(r"\$\{(\w+)\}")

    def __init__(self, path: str | Path, root_key: str = None):
        self._path = Path(path)
        self.data: dict[str, Any] = {}
        self._load(root_key)

    def _load(self, root_key: str = None) -> None:
        if not self._path.exists():
            raise ConfigError(f"Config file not found: {self._path}")

        if self._path.suffix.lower() == ".json":
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        else:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)

        if not isinstance(raw, dict):
            raise ConfigError(f"Invalid config format in {self._path}")

        if root_key and root_key in raw:
            raw = raw[root_key]

        self.data = self._resolve_env_vars(raw)

    def _resolve_env_vars(self, obj: Any) -> Any:
        """Recursively resolve ${VAR} placeholders from environment."""
        if isinstance(obj, str):
            def _replacer(match):
                var_name = match.group(1)
                value = os.environ.get(var_name)
                if value is None:
                    # Return placeholder as-is if env var not set
                    return match.group(0)
                return value
            return self._ENV_PATTERN.sub(_replacer, obj)
        elif isinstance(obj, dict):
            return {k: self._resolve_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve_env_vars(item) for item in obj]
        return obj

    def get(self, *keys: str, default: Any = None) -> Any:
        """
        Access nested config values using dot-style keys.

        Example:
            config.get("rate_limit", "requests_per_minute")  → 20
        """
        current = self.data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def require(self, *keys: str) -> Any:
        """Like get(), but raises ConfigError if the key is missing."""
        result = self.get(*keys)
        if result is None:
            path = " → ".join(keys)
            raise ConfigError(f"Required config key missing: {path}")
        return result


    def __repr__(self) -> str:
        return f"Config({self._path.name})"
