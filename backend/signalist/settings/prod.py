from .base import *  # noqa: F403
from .base import _env

DEBUG = False
ALLOWED_HOSTS = [h for h in _env("DJANGO_ALLOWED_HOSTS", "").split(",") if h]
SECRET_KEY = _env("DJANGO_SECRET_KEY", required=True)

SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
