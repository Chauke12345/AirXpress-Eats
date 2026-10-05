"""
Django settings for AirXpress Eats.
"""

from pathlib import Path
import os

import dj_database_url


# =========================================================
# BASE DIRECTORY
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent


# Load local environment variables from .env
env_file = BASE_DIR / ".env"

if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)

            os.environ.setdefault(
                key.strip(),
                value.strip(),
            )


# =========================================================
# SECURITY
# =========================================================

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-local-development-key",
)

DEBUG = os.environ.get(
    "DEBUG",
    "True",
).lower() == "true"


# =========================================================
# ALLOWED HOSTS
# =========================================================

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "endorse-scroll-affix.ngrok-free.dev",
    ".railway.app",
]


# =========================================================
# CSRF TRUSTED ORIGINS
# =========================================================

CSRF_TRUSTED_ORIGINS = [
    "https://*.railway.app",
    "https://endorse-scroll-affix.ngrok-free.dev",
]


# =========================================================
# APPLICATIONS
# =========================================================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "orders",
]


# =========================================================
# MIDDLEWARE
# =========================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",

    # WhiteNoise must come directly after SecurityMiddleware
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# =========================================================
# URL CONFIGURATION
# =========================================================

ROOT_URLCONF = "config.urls"


# =========================================================
# TEMPLATES
# =========================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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


# =========================================================
# WSGI
# =========================================================

WSGI_APPLICATION = "config.wsgi.application"


# =========================================================
# DATABASE
# =========================================================

DATABASE_URL = os.environ.get(
    "DATABASE_URL"
)

if DATABASE_URL:

    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }

else:

    # Local development database
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# =========================================================
# PASSWORD VALIDATION
# =========================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# =========================================================
# INTERNATIONALIZATION
# =========================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Africa/Johannesburg"

USE_I18N = True

USE_TZ = True


# =========================================================
# STATIC FILES
# =========================================================

STATIC_URL = "/static/"

# Project-level static files
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Collected production static files
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage."
            "CompressedManifestStaticFilesStorage"
        ),
    },
}

# =========================================================
# MEDIA FILES
# =========================================================

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"


# =========================================================
# DEFAULT PRIMARY KEY
# =========================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# =========================================================
# EMAIL
# =========================================================

EMAIL_BACKEND = (
    "django.core.mail.backends.console.EmailBackend"
)


# =========================================================
# LOGIN
# =========================================================

LOGIN_REDIRECT_URL = "/staff/dashboard/"

LOGIN_URL = "/staff/login/"

# =========================================================
# PAYFAST
# =========================================================

# PayFast merchant credentials are loaded from environment variables.
# NEVER hard-code these values into the source code.
PAYFAST_PUBLIC_URL = os.environ.get(
    "PAYFAST_PUBLIC_URL",
    "",
)
PAYFAST_MERCHANT_ID = os.environ.get(
    "PAYFAST_MERCHANT_ID",
    ""
).strip()

PAYFAST_MERCHANT_KEY = os.environ.get(
    "PAYFAST_MERCHANT_KEY",
    ""
).strip()

PAYFAST_PASSPHRASE = os.environ.get(
    "PAYFAST_PASSPHRASE",
    ""
).strip()

# Use sandbox while testing. Set to False for live payments.
PAYFAST_SANDBOX = os.environ.get(
    "PAYFAST_SANDBOX",
    "True"
).lower() == "true"

# =========================================================
# MAPBOX
# =========================================================

# =========================================================
# MAPBOX
# =========================================================

MAPBOX_TOKEN = os.environ.get("MAPBOX_TOKEN", "").strip()

# Enforce the local .env token if the environment variable is empty.
if not MAPBOX_TOKEN:
    _mapbox_env = BASE_DIR / ".env"

    if _mapbox_env.exists():
        for _line in _mapbox_env.read_text(
            encoding="utf-8"
        ).splitlines():

            _line = _line.strip()

            if not _line or _line.startswith("#"):
                continue

            if _line.startswith("MAPBOX_TOKEN="):
                MAPBOX_TOKEN = (
                    _line.split("=", 1)[1]
                    .strip()
                    .strip("\"'")
                )
                break

            if _line.startswith("pk."):
                MAPBOX_TOKEN = _line
                break







