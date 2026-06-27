import os
from datetime import timedelta


# Fungsi untuk membaca env boolean dengan fallback default.
def get_bool_env(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Fungsi untuk membaca env integer dengan fallback default.
def get_int_env(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# Konfigurasi default aplikasi Flask.
class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "secret123")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///users.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=60)
    ENABLE_PROXY_FIX = get_bool_env("ENABLE_PROXY_FIX", False)
    TRUSTED_PROXY_COUNT = max(get_int_env("TRUSTED_PROXY_COUNT", 1), 1)
    GEOIP_DB_PATH = os.environ.get("GEOIP_DB_PATH", "").strip()
