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
    ONBOARD_MIGRATIONS_DIR: optional; defaults to <repo>/db/migrations/onboard.
    ONBOARD_CORS_ORIGINS: JSON list, e.g. '["http://localhost:1420"]'.
    """

    model_config = SettingsConfigDict(env_prefix="ONBOARD_")

    db_path: Path = Path("data/onboard.db")
    migrations_dir: Path | None = None
    cors_origins: list[str] = DEFAULT_CORS_ORIGINS

    # Local assistant. Everything runs on this machine.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "qwen2.5:3b"
    # Same model for ingest and query; changing it requires re-ingesting.
    ollama_embed_model: str = "bge-m3"
    ollama_timeout_seconds: float = 20.0
    # Max wait for the local interpreter (text -> observations) on non-alarm turns.
    ollama_interpret_timeout_seconds: float = 15.0
    chroma_path: Path = Path("data/chroma")
    guides_collection: str = "medical_guides"
    # Cosine distance above which a retrieved chunk is dropped (tuned on bge-m3 eval).
    retrieval_max_distance: float = 0.50
    # Optional JSON list of OperationalEvent used as the demo event source.
    demo_events_path: Path | None = None

    # Telemetry to ground (contracts/telemetry). A lost link never blocks onboard work.
    telemetry_enabled: bool = True
    ground_api_url: str = "http://127.0.0.1:8001"
    telemetry_interval_seconds: float = 5.0
    ship_id: str = "ship-01"
    # Demo controls (docs/demo-outage.md): POST /telemetry/pause|resume and
    # DELETE /demo/incidents. Off by default, also in docker-compose (DEMO_CONTROLS_ENABLED=true).
    demo_controls_enabled: bool = False
    # Approved knowledge bundles (contracts/medical-eval section 5): active/ and previous/.
    knowledge_dir: Path = Path("data/knowledge")
