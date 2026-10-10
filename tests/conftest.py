import importlib

import pytest

import database.db as db


@pytest.fixture
def db_path(monkeypatch, tmp_path):
    """Point the data layer at a throwaway SQLite file for this test."""
    path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", str(path))
    return path


@pytest.fixture
def app(db_path):
    # Import lazily: app.py runs init_db()/seed_db() at import time, and
    # this must happen after DB_PATH is patched, never on the real DB.
    app_module = importlib.import_module("app")
    db.init_db()
    db.seed_db()
    flask_app = app_module.app
    flask_app.config.update(TESTING=True)
    yield flask_app


@pytest.fixture
def count_users(app):
    def _count():
        conn = db.get_db()
        try:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        finally:
            conn.close()
    return _count
