"""Test settings: development-style defaults applied before the real settings load.

Plain static storage (no manifest needed) and no HTTPS redirect. pytest-django still
forces DEBUG off while tests run.
"""

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from .settings import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
