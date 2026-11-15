from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CORS_ORIGINS = [
    "http://localhost:1421",  # base-app Vite dev server
    "tauri://localhost",  # Tauri production origin on macOS/Linux
    "http://tauri.localhost",  # Tauri production origin on Windows
]


class Settings(BaseSettings):
    """Settings read from environment variables prefixed with GROUND_.

    GROUND_DB_PATH: SQLite file path (relative paths resolve from the cwd).
    GROUND_CORS_ORIGINS: JSON list.
    """

    model_config = SettingsConfigDict(env_prefix="GROUND_")

    db_path: Path = Path("data/ground.db")
    cors_origins: list[str] = DEFAULT_CORS_ORIGINS
    # DELETE /demo/incidents for the outage demo (docs/demo-outage.md). Off by default.
    demo_controls_enabled: bool = False
    # Staging root for approved knowledge bundles: manifest component paths resolve from
    # here (GET /medical-eval/approved/bundle). Default: the repo root when run from
    # services/ground-api.
    bundle_root: Path = Path("../..")
