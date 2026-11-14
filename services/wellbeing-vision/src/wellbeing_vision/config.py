from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ASTRONAUT_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{1,31}$"


class Settings(BaseSettings):
    """Settings read from environment variables prefixed with WELLBEING_VISION_.

    WELLBEING_VISION_API_URL: onboard-api base URL.
    WELLBEING_VISION_CAMERAS: JSON map camera index -> module id, e.g. '{"0":"modulo-a"}'.
    WELLBEING_VISION_ASTRONAUTS: JSON map astronaut id -> display name.
    """

    model_config = SettingsConfigDict(env_prefix="WELLBEING_VISION_")

    api_url: str = "http://127.0.0.1:8000"
    models_dir: Path = Path("models")
    data_dir: Path = Path("data")
    outbox_path: Path = Path("outbox/pending.jsonl")
    cameras: dict[int, str] = Field(default={0: "modulo-a", 1: "modulo-b"})
    astronauts: dict[str, str] = Field(
        default={f"ast-0{i}": f"ast-0{i}" for i in range(1, 5)}
    )
