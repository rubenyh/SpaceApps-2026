from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Body of 404 and 409 responses."""

    detail: str
