"""
Test-only settings. Uses a separate PostgreSQL database so tests never touch dev data.
Requires PostgreSQL running with credentials from .env (same as backend.settings).
"""
from decouple import config

from .settings import *  # noqa: F401, F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_TEST_NAME', default='adosx_test_db'),
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
    }
}
