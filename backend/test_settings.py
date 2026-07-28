"""
Test-only settings. Overrides the production DB with SQLite in-memory so
tests never touch the real PostgreSQL database.
"""
from .settings import *  # noqa: F401, F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}
