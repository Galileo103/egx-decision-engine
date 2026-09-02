"""Application configuration.

Loads settings from environment variables (optionally via a `.env` file at the
project root) using python-dotenv. Importing this module never raises: a
missing `.env` file is fine, and malformed numeric env values fall back to
their defaults.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = parent of the app/ package directory.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# load_dotenv is a no-op (returns False) when the file does not exist.
load_dotenv(PROJECT_ROOT / ".env")


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_opt(name: str) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else None


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env_str(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env_str(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


class Settings:
    """Runtime settings, loaded once at import time from the environment."""

    def __init__(self) -> None:
        self.host: str = _env_str("HOST", "127.0.0.1")
        self.port: int = _env_int("PORT", 8642)

        default_db = str(PROJECT_ROOT / "data" / "egx.db")
        self.db_path: str = _env_str("DB_PATH", default_db)

        self.anthropic_api_key: str | None = _env_opt("ANTHROPIC_API_KEY")
        self.telegram_bot_token: str | None = _env_opt("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id: str | None = _env_opt("TELEGRAM_CHAT_ID")

        self.scheduler_enabled: bool = _env_bool("SCHEDULER_ENABLED", True)
        self.account_size: float = _env_float("ACCOUNT_SIZE", 100_000.0)
        self.risk_pct: float = _env_float("RISK_PCT", 1.0)

        # EGX market-realism settings (Tier 2).
        # All-in per-side transaction cost percent: brokerage commission +
        # stamp duty (0.05% resident) + FRA/EGX/MCDR fees + risk insurance.
        # Typical EGX retail all-in is ~0.2-0.3% per side.
        self.fee_pct_per_side: float = _env_float("FEE_PCT_PER_SIDE", 0.25)
        # Annual EGP risk-free rate percent for Sharpe (EGP T-bill yield).
        self.risk_free_rate_pct: float = _env_float("RISK_FREE_RATE_PCT", 25.0)
        # Daily price-limit band percent (EGX main market default ±20%;
        # tighter regimes apply to some boards/stocks).
        self.price_band_pct: float = _env_float("PRICE_BAND_PCT", 20.0)
        # Candidates below this 20-day median traded value (EGP) are flagged
        # or filtered as illiquid.
        self.min_daily_value_egp: float = _env_float("MIN_DAILY_VALUE_EGP", 5_000_000.0)

        # Ensure the database directory exists so sqlite can create the file.
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Non-fatal here; db.get_conn() will surface a clear error later.
            pass


settings = Settings()
