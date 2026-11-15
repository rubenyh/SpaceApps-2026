from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ASTRONAUT_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{1,31}$"


class Settings(BaseSettings):
    """Settings read from environment variables prefixed with WELLBEING_VISION_.

    WELLBEING_VISION_API_URL: onboard-api base URL.
    WELLBEING_VISION_CAMERAS: JSON map camera index -> module id, e.g. '{"0":"modulo-a"}'.
    WELLBEING_VISION_ASTRONAUTS: JSON map astronaut id -> display name.
    WELLBEING_VISION_CAMERA_BACKEND: auto | dshow | msmf.
    """

    model_config = SettingsConfigDict(env_prefix="WELLBEING_VISION_")

    api_url: str = "http://127.0.0.1:8000"
    models_dir: Path = Path("models")
    data_dir: Path = Path("data")
    outbox_path: Path = Path("outbox/pending.jsonl")
    # PROVISIONAL: below this face width (cheek to cheek, px) eye landmarks get too noisy for blinks.
    # ~256 px at 50 cm and ~128 px at 1 m on a 720p webcam with a 70 degree field of view.
    min_face_px: float = 160.0
    cameras: dict[int, str] = Field(default={0: "modulo-a", 1: "modulo-b"})
    # auto: DSHOW, then MSMF if DSHOW does not open or gives no frame in 2 s (USB phone webcams need MSMF).
    camera_backend: Literal["auto", "dshow", "msmf"] = "auto"
    # Per camera, applied to every frame before processing and display, e.g. a phone webcam that arrives
    # mirrored: WELLBEING_VISION_CAMERA_FLIP='[1]'. Turn is clockwise: WELLBEING_VISION_CAMERA_TURN='{"1": 180}'.
    camera_flip: list[int] = Field(default_factory=list)
    camera_turn: dict[int, Literal[0, 90, 180, 270]] = Field(default_factory=dict)
    # Ambient mode captures smaller: 640x480 is ~3.5x cheaper for face detection than 1280x720.
    ambient_width: int = 640
    ambient_height: int = 480
    min_track_s: float = 3.0  # PROVISIONAL: a track counts as occupant and in pairs only after this long
    astronauts: dict[str, str] = Field(
        default={f"ast-0{i}": f"ast-0{i}" for i in range(1, 5)}
    )
