from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from onboard_api.config import Settings
from onboard_api.dependencies import utc_now
from onboard_api.repositories.database import init_db
from onboard_api.routers import assistant, astronauts, readings, sensors, status


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Tests pass their own Settings (e.g. a temp db_path)."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Creates the DB directory, schema and sensor configuration if missing.
        init_db(settings.db_path, now=utc_now())
        app.state.settings = settings
        yield

    app = FastAPI(title="Space Apps Onboard API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(astronauts.router)
    app.include_router(status.router)
    app.include_router(sensors.router)
    app.include_router(readings.router)
    app.include_router(assistant.router)
    return app


app = create_app()
