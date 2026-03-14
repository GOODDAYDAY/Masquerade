"""Configuration loading and validation for the Masquerade platform.

app_config.yaml — application-level settings (logging, LLM defaults).
config/games/<game>.yaml — game-specific config, free-form, parsed by each engine.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from backend.core.exceptions import ConfigError


class LLMDefaults(BaseModel):
    """Global default LLM parameters — inherited by players who don't specify their own."""

    model: str = "deepseek-chat"
    api_base: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    temperature: float = 0.7
    max_retries: int = 3
    timeout: int = 60


class AppSettings(BaseSettings):
    """Application-level settings. Env vars with MASQUERADE_ prefix override YAML values."""

    log_level: str = "INFO"
    log_dir: str = "logs"
    scripts_dir: str = "output/scripts"
    output_dir: str = "output"
    llm: LLMDefaults = Field(default_factory=LLMDefaults)

    model_config = {"env_prefix": "MASQUERADE_", "env_nested_delimiter": "__", "env_file": ".env"}


class PlayerConfig(BaseModel):
    """LLM player configuration. Empty LLM fields inherit from AppSettings.llm."""

    name: str
    model: str = ""
    api_base: str = ""
    api_key: str = ""
    persona: str = ""
    appearance: str = ""


def load_yaml(path: Path | str) -> dict:
    """Load a YAML file and return its content as a dict."""
    p = Path(path)
    if not p.exists():
        raise ConfigError("Config file not found: %s" % p)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if data else {}
    except yaml.YAMLError as e:
        raise ConfigError("Failed to parse YAML %s: %s" % (p, e)) from e


def _strip_empty(data: dict) -> dict:
    """Recursively remove empty-string values so env vars are not overridden."""
    cleaned = {}
    for k, v in data.items():
        if isinstance(v, dict):
            nested = _strip_empty(v)
            if nested:
                cleaned[k] = nested
        elif v != "":
            cleaned[k] = v
    return cleaned


def load_app_settings(path: str = "config/app_config.yaml") -> AppSettings:
    """Load application settings from YAML, with .env and env var overrides.

    Empty strings in YAML are stripped so that .env / env vars take precedence.
    """
    config_path = Path(path)
    if config_path.exists():
        data = load_yaml(config_path)
        return AppSettings(**_strip_empty(data))
    return AppSettings()


def resolve_player_llm(player: PlayerConfig, defaults: LLMDefaults) -> PlayerConfig:
    """Fill in missing LLM fields on a player config from app-level defaults."""
    return PlayerConfig(
        name=player.name,
        model=player.model or defaults.model,
        api_base=player.api_base or defaults.api_base,
        api_key=player.api_key or defaults.api_key,
        persona=player.persona,
        appearance=player.appearance,
    )
