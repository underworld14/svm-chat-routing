"""Isolate tests from the developer SQLite DB used by the running API.

CRITICAL: set DATABASE_URL before any `app.*` import.
"""

from __future__ import annotations

import os
from pathlib import Path

_TEST_DB = Path(__file__).resolve().parent / "test_chat_routing.db"
_TEST_DB_URL = f"sqlite:///{_TEST_DB}"

# Must run before app.database / app.config are imported by test modules.
os.environ["DATABASE_URL"] = _TEST_DB_URL

from app.config import get_settings, settings as _settings_singleton  # noqa: E402

get_settings.cache_clear()

# Re-bind module-level settings used across the app.
import app.config as app_config  # noqa: E402

app_config.settings = get_settings()

from app.database import Base, engine, ensure_sqlite_columns  # noqa: E402
from app import models  # noqa: F401, E402


def _assert_isolated_db() -> None:
    url = str(get_settings().DATABASE_URL)
    if "chat_routing.db" in url and "test_chat_routing.db" not in url:
        raise RuntimeError(
            f"REFUSING to run tests against development DB: {url}. "
            "Expected DATABASE_URL to point at test_chat_routing.db"
        )
    if "test_chat_routing.db" not in url:
        raise RuntimeError(f"Tests must use isolated DB, got: {url}")


def pytest_sessionstart(session) -> None:
    _assert_isolated_db()
    # Recreate engine bind in case settings changed after first import.
    from app import database as app_database

    app_database.engine = engine
    if str(engine.url) != _TEST_DB_URL and "test_chat_routing.db" not in str(engine.url):
        # Force recreate engine with test URL
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        connect_args = {"check_same_thread": False}
        app_database.engine = create_engine(_TEST_DB_URL, connect_args=connect_args)
        app_database.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=app_database.engine
        )

    Base.metadata.drop_all(bind=app_database.engine)
    Base.metadata.create_all(bind=app_database.engine)
    ensure_sqlite_columns()

    from seed import main as seed_main

    seed_main()


def pytest_sessionfinish(session, exitstatus) -> None:
    from sqlalchemy.orm import close_all_sessions

    close_all_sessions()
    try:
        _TEST_DB.unlink(missing_ok=True)
    except TypeError:
        # Python < 3.8 fallback (not expected on 3.13)
        if _TEST_DB.exists():
            _TEST_DB.unlink()
