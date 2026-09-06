"""
공통 설정. 환경별 파일(dev / prod / test)이 이 모듈을 확장한다.

스키마 소유자는 Django 마이그레이션이다. 이식 중에는 drizzle 이 소유했고 모델이
`managed = False` 였다 — 자세한 경위는 `news/models.py` 참고.
"""

import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent.parent
# 저장소 루트. .env 가 여기에 있다.
REPO_ROOT = BASE_DIR.parent


def _env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(
            f"{name} 환경변수가 없습니다. 저장소 루트의 .env 를 확인하세요"
            " (.env.example 참고)."
        )
    return value or ""


def _load_dotenv(path: Path) -> None:
    """의존성을 늘리지 않기 위해 최소한의 .env 로더를 둔다. 이미 있는 값은 덮지 않는다."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(REPO_ROOT / ".env")

SECRET_KEY = _env("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-in-prod")
DEBUG = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    # Admin 이 운영 조회 화면이고 인증이 그 전제다.
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.postgres",  # GinIndex 등 Postgres 전용 기능
    "django.contrib.staticfiles",
    "news",
    "research",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "signalist.urls"
WSGI_APPLICATION = "signalist.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


def _database_from_url(url: str) -> dict[str, object]:
    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError(f"PostgreSQL 접속 문자열이 아닙니다: {parsed.scheme}://…")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": (parsed.path or "/").lstrip("/"),
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "localhost",
        "PORT": str(parsed.port or 5432),
        "CONN_MAX_AGE": 60,
    }


DATABASES = {"default": _database_from_url(_env("DATABASE_URL", required=True))}

# 리서치 인덱스(SEC 티커·DART corp_code)는 하루 한 번 받는 수 MB 짜리 전량 파일이다.
# 워커별 LocMemCache 면 워커 수만큼 중복 다운로드가 생기므로, 공유 백엔드가 있으면 쓴다.
# MAX_ENTRIES 기본값 300 은 인덱스가 LRU 로 밀려날 수 있어 올려 둔다.
_CACHE_URL = _env("SIGNALIST_CACHE_URL")
CACHES = {
    "default": (
        {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": _CACHE_URL}
        if _CACHE_URL
        else {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "signalist-local",
            "OPTIONS": {"MAX_ENTRIES": 1000, "CULL_FREQUENCY": 4},
        }
    )
}

# 리서치 데이터 공급자 설정
SIGNALIST_DART_API_KEY = _env("SIGNALIST_DART_API_KEY")
SIGNALIST_SEC_USER_AGENT = _env("SIGNALIST_SEC_USER_AGENT")

# 저장은 항상 timestamptz, 표시·조회는 한국시간. published_date_kst 생성 열이
# 'Asia/Seoul'로 계산하므로 서버 타임존에 의존하지 않는다.
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "[{asctime}] {levelname} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": _env("LOG_LEVEL", "INFO")},
}
