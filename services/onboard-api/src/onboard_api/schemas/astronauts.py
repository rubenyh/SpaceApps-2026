from pydantic import AwareDatetime, BaseModel, Field

ASTRONAUT_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{1,31}$"


class AstronautCreate(BaseModel):
    id: str = Field(pattern=ASTRONAUT_ID_PATTERN)
    display_name: str = Field(min_length=1, max_length=80)


class AstronautUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)


class Astronaut(BaseModel):
    id: str
    display_name: str
    created_at: AwareDatetime
