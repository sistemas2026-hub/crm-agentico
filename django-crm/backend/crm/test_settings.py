"""
Test settings for Django CRM backend.

Uses SQLite in-memory database instead of PostgreSQL for fast, isolated tests.
RLS (Row-Level Security) is PostgreSQL-only and is skipped on SQLite.
"""

from crm.settings import *  # noqa: F401, F403

# SQLite por defecto: es lo que hace que la suite corra en segundos y sin
# depender de que alguien tenga un servidor levantado.
#
# Pero deja fuera las pruebas marcadas 'postgres_only', y esas no son un lujo:
# hay comportamiento que SQLite no reproduce. El caso concreto que motivo esta
# variante (08/09/2026) es un INSERT que viola una constraint dentro de una
# transaccion -- en PostgreSQL la aborta y toda consulta posterior falla, en
# SQLite no pasa nada. Un arreglo al que le faltaba el SAVEPOINT pasaba la
# suite entera en verde y habria fallado solo en produccion, y solo con dos
# peticiones simultaneas.
#
# Con TEST_DATABASE_URL apuntando a un Postgres cualquiera, esas pruebas
# corren de verdad. Uno efimero alcanza:
#
#   docker run -d --name pg-campo-test -e POSTGRES_PASSWORD=test #       -e POSTGRES_USER=test -e POSTGRES_DB=test -p 55432:5432 postgres:16-alpine
#   set TEST_DATABASE_URL=postgres://test:test@localhost:55432/test
#   uv run pytest campo/tests/ --no-cov -v
import os as _os
from urllib.parse import urlparse as _urlparse

_TEST_DB_URL = _os.environ.get("TEST_DATABASE_URL", "").strip()
if _TEST_DB_URL:
    _u = _urlparse(_TEST_DB_URL)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": (_u.path or "/test").lstrip("/"),
            "USER": _u.username or "",
            "PASSWORD": _u.password or "",
            "HOST": _u.hostname or "localhost",
            "PORT": str(_u.port or 5432),
            "ATOMIC_REQUESTS": False,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

# Disable Celery broker/result backend in tests (no Redis needed)
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# The default PBKDF2 hasher costs ~190ms per hash. Fixtures create users on
# nearly every test, so that dominates the run. MD5 is fine here: it is never
# used outside crm.test_settings, and no test asserts on the hash algorithm.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Uploads land in a throwaway directory rather than in `backend/media/`.
# Without this every attachment test leaves its file behind: the tree had grown
# to 51 MB of `update_YXw1f7b.txt` and friends by the time anyone looked, and
# the size-limit test below writes a 25 MB file on every run.
#
# `mkdtemp` rather than `TemporaryDirectory` because nothing here would call
# `cleanup()`; the OS reclaims it, and a test that needs to read back a file it
# just wrote still can.
import tempfile  # noqa: E402

MEDIA_ROOT = tempfile.mkdtemp(prefix="bottlecrm-test-media-")
