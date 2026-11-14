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

    # Local assistant. Everything runs on this machine.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "qwen2.5:0.5b"
    # Same model for ingest and query; changing it requires re-ingesting.
    ollama_embed_model: str = "bge-m3"
    ollama_timeout_seconds: float = 20.0
    chroma_path: Path = Path("data/chroma")
    guides_collection: str = "medical_guides"
    # Cosine distance above which a retrieved chunk is dropped (tuned on bge-m3 eval).
    retrieval_max_distance: float = 0.50
    # Optional JSON list of OperationalEvent used as the demo event source.
    demo_events_path: Path | None = None
