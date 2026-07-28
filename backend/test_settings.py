"""
Test-only settings. Overrides the database to SQLite in-memory so tests
never need a running PostgreSQL instance. Zero external dependencies for CI.
"""

from .settings import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
