from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASIS = (
    "Parámetros de diseño del equipo, sin validación clínica. "
    "Se comparan desviaciones contra la línea base personal."
)


class WellbeingSettings(BaseSettings):
    """Settings of the wellbeing module, read from WELLBEING_* variables.

    Every threshold here is a PROVISIONAL design parameter, not a clinical
    cut-off. Relative paths resolve from the working directory, like the
    onboard database.
    """

    model_config = SettingsConfigDict(env_prefix="WELLBEING_")

    # Own database (read/write).
    db_path: Path = Path("data/wellbeing.db")
    # Physical readings database owned by the onboard service, opened read-only.
    # Shares ONBOARD_DB_PATH with the onboard service.
    onboard_db_path: Path = Field(
        default=Path("data/onboard.db"),
        validation_alias=AliasChoices("ONBOARD_DB_PATH", "WELLBEING_ONBOARD_DB_PATH"),
    )

    z_threshold: float = Field(default=1.5, gt=0)
    sustain_days: int = Field(default=3, ge=1)
    baseline_days: int = Field(default=7, ge=1)
    baseline_min_days: int = Field(default=5, ge=1)
    adaptation_days: int = Field(default=0, ge=0)
    stale_after_days: int = Field(default=2, ge=0)
    trend_window_days: int = Field(default=3, ge=1)
    trend_min_delta: float = Field(default=0.5, ge=0)
    z_cap: float = Field(default=5.0, gt=0)
    # Minimum good heart_rate readings in a day to derive the daily low.
    min_heart_rate_readings: int = Field(default=10, ge=1)


@lru_cache
def get_wellbeing_settings() -> WellbeingSettings:
    return WellbeingSettings()
