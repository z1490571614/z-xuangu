"""
Tushare client helpers.

The desktop/dev environment can already contain a stale TUSHARE_TOKEN.  Project
services should prefer the repository .env token so scripts, tests, and FastAPI
startup all create the same Pro client.
"""
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import tushare as ts


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ENV = PROJECT_ROOT / ".env"


@lru_cache(maxsize=1)
def ensure_project_env() -> None:
    """Load project .env once, overriding stale process-level values."""
    if PROJECT_ENV.exists():
        load_dotenv(PROJECT_ENV, override=True)
    else:
        load_dotenv(override=True)


def get_tushare_token(token: Optional[str] = None) -> str:
    """Return the explicit token or the project configured Tushare token."""
    if token:
        return token.strip()
    ensure_project_env()
    return os.getenv("TUSHARE_TOKEN", "").strip()


def get_tushare_pro(token: Optional[str] = None):
    """Create a Tushare Pro client using the project token."""
    resolved = get_tushare_token(token)
    if not resolved:
        return None
    try:
        ts.set_token(resolved)
        return ts.pro_api()
    except OSError:
        return ts.pro_api(resolved)
