"""
Lumivision settings — configured via environment variables for Docker:

  LUMIVISION_SECRET_KEY      optional; auto-generated and persisted in the data dir if unset
  LUMIVISION_DEBUG           "1" to enable debug mode (default off)
  LUMIVISION_ALLOWED_HOSTS   comma-separated hostnames (default "*")
  LUMIVISION_TRUSTED_ORIGINS comma-separated origins for CSRF, e.g. "https://vision.example.com"
  LUMIVISION_DATA_DIR        writable dir for sqlite db + uploads (default ./data)
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("LUMIVISION_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "media").mkdir(parents=True, exist_ok=True)

DEBUG = os.environ.get("LUMIVISION_DEBUG", "0") == "1"
TESTING = "test" in sys.argv

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
# The container health check probes over loopback regardless of public hosts.
if "*" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS += ["127.0.0.1", "localhost"]

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("LUMIVISION_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

# Django's default Referrer-Policy (same-origin) strips the Referer from the
# YouTube embed iframe, which the player rejects with "configuration error
# (153)". strict-origin-when-cross-origin sends only the origin cross-site.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# Honor X-Forwarded-Proto from the reverse proxy (nginx/Apache/Caddy/…).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.forms",
    "axes",
    "core",
]

# Let widgets use project template dirs (custom clearable-file widget).
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.MaxBodySizeMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

# ---- Login rate limiting (django-axes) ----
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = int(os.environ.get("LUMIVISION_LOGIN_ATTEMPT_LIMIT", "6"))
AXES_COOLOFF_TIME = timedelta(
    minutes=int(os.environ.get("LUMIVISION_LOGIN_COOLOFF_MINUTES", "15"))
)
AXES_RESET_ON_SUCCESS = True
# Lock the username+IP pair: brute force from one address is blocked without
# letting an attacker lock a victim out from everywhere.
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_LOCKOUT_TEMPLATE = "auth/locked_out.html"
# The test suite drives Client.login() directly; axes is exercised by its
# own dedicated test via override_settings.
AXES_ENABLED = not TESTING

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
                "core.context_processors.site_settings",
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
        # Manifest storage needs collectstatic to have run; use plain
        # storage in debug and under the test runner.
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG or TESTING
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
