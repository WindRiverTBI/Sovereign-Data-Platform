"""Django settings for the WRTBI buffalo data-entry application.

Every deploy-specific value comes from the environment (or a `.env` file
next to `manage.py`); see `.env.example` for the full list.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

DEBUG: bool = env.bool("DJANGO_DEBUG", default=False)
SECRET_KEY: str = env.str("DJANGO_SECRET_KEY")
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS: list[str] = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "django_cotton",
    "django_htmx",
    "django_tailwind_cli",
    "simple_history",
    "buffalo",
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
    "django_htmx.middleware.HtmxMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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

DATABASES = {"default": env.db_url("DATABASE_URL", engine="django.contrib.gis.db.backends.postgis")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "buffalo:index"
LOGOUT_REDIRECT_URL = "login"
# Reset links expire after 24 hours, matching the original application.
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24

LANGUAGE_CODE = "en-us"
TIME_ZONE = env.str("DJANGO_TIME_ZONE", default="America/Denver")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "assets"]

# Uploads live on the local filesystem for now. Moving to an S3-compatible
# store is a matter of swapping the "default" backend here for
# django-storages; nothing else references the storage location directly.
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env.str("DJANGO_MEDIA_ROOT", default=str(BASE_DIR / "media")))
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
ATTACHMENT_MAX_BYTES: int = env.int("ATTACHMENT_MAX_BYTES", default=2 * 1024**3)

# Django 6.1 replaces the EMAIL_* settings with MAILERS. EMAIL_URL is parsed
# by django-environ (e.g. smtp://user:pass@host:587/?tls=True) and mapped onto
# the default mailer's backend options.
_email = env.email_url("EMAIL_URL", default="consolemail://")
_email_options = {
    "host": _email.get("EMAIL_HOST"),
    "port": _email.get("EMAIL_PORT"),
    "username": _email.get("EMAIL_HOST_USER"),
    "password": _email.get("EMAIL_HOST_PASSWORD"),
    "use_tls": _email.get("EMAIL_USE_TLS"),
    "use_ssl": _email.get("EMAIL_USE_SSL"),
}
MAILERS = {
    "default": {
        "BACKEND": _email["EMAIL_BACKEND"],
        "OPTIONS": (
            {k: v for k, v in _email_options.items() if v not in (None, "")}
            if _email["EMAIL_BACKEND"].endswith("smtp.EmailBackend")
            else {}
        ),
    }
}
DEFAULT_FROM_EMAIL: str = env.str("DEFAULT_FROM_EMAIL", default="wyadapt-info@windriverbuffalo.org")
SUPPORT_EMAIL: str = env.str("SUPPORT_EMAIL", default="support@windriverbuffalo.org")

TAILWIND_CLI_VERSION = "4.3.3"
TAILWIND_CLI_SRC_CSS = "tailwind/source.css"
TAILWIND_CLI_DIST_CSS = "css/tailwind.css"
TAILWIND_CLI_PATH: str = env.str(
    "TAILWIND_CLI_PATH", default=str(BASE_DIR / ".django_tailwind_cli")
)

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env.str("DJANGO_LOG_LEVEL", default="INFO")},
}
