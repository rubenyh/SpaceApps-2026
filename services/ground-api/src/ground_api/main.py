from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ground_api import storage, telemetry
from ground_api.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Tests pass their own Settings (e.g. a temp db_path)."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        storage.init_db(settings.db_path)
        app.state.settings = settings
        yield

    app = FastAPI(title="Space Apps Ground API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(telemetry.router)
    return app


app = create_app()


def main() -> None:
    print("Hello from ground-api!")
