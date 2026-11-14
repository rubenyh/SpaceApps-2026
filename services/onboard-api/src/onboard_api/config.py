from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CORS_ORIGINS = [
    "http://localhost:1420",  # Vite dev server inside the Tauri webview
    "tauri://localhost",  # Tauri production origin on macOS/Linux
    "http://tauri.localhost",  # Tauri production origin on Windows
]


class Settings(BaseSettings):
    """Settings read from environment variables prefixed with ONBOARD_.

    ONBOARD_DB_PATH: SQLite file path (relative paths resolve from the cwd).
    ONBOARD_CORS_ORIGINS: JSON list, e.g. '["http://localhost:1420"]'.
    """

    model_config = SettingsConfigDict(env_prefix="ONBOARD_")

    db_path: Path = Path("data/onboard.db")
    cors_origins: list[str] = DEFAULT_CORS_ORIGINS
