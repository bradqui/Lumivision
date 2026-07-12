"""
Lumivision settings — configured via environment variables for Docker:

  LUMIVISION_SECRET_KEY      optional; auto-generated and persisted in the data dir if unset
  LUMIVISION_DEBUG           "1" to enable debug mode (default off)
  LUMIVISION_ALLOWED_HOSTS   comma-separated hostnames (default "*")
  LUMIVISION_TRUSTED_ORIGINS comma-separated origins for CSRF, e.g. "https://vision.example.com"
  LUMIVISION_DATA_DIR        writable dir for sqlite db + uploads (default ./data)
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("LUMIVISION_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "media").mkdir(parents=True, exist_ok=True)

DEBUG = os.environ.get("LUMIVISION_DEBUG", "0") == "1"

SECRET_KEY = os.environ.get("LUMIVISION_SECRET_KEY", "").strip()
if not SECRET_KEY:
    # Generate once and persist alongside the data so sessions survive restarts.
    _key_file = DATA_DIR / ".secret_key"
    if _key_file.exists():
        SECRET_KEY = _key_file.read_text().strip()
    else:
        from django.core.management.utils import get_random_secret_key

        SECRET_KEY = get_random_secret_key()
        _key_file.write_text(SECRET_KEY)

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("LUMIVISION_ALLOWED_HOSTS", "*").split(",")
    if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("LUMIVISION_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

# Honor X-Forwarded-Proto from the Virtualmin/nginx/Apache reverse proxy.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "lumivision.urls"

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

WSGI_APPLICATION = "lumivision.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
        "OPTIONS": {
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;",
            "transaction_mode": "IMMEDIATE",
        },
    }
}

AUTH_USER_MODEL = "core.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("LUMIVISION_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = DATA_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# Allow generous uploads (videos). Django streams large bodies to disk.
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# Hard cap enforced in forms (bytes); override via env if desired.
LUMIVISION_MAX_UPLOAD_BYTES = int(
    os.environ.get("LUMIVISION_MAX_UPLOAD_MB", "250")
) * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if not DEBUG:
    SESSION_COOKIE_SECURE = os.environ.get("LUMIVISION_COOKIE_SECURE", "1") == "1"
    CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
