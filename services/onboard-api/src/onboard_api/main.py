from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from onboard_api.assistant.integrations.chroma import GuideRetriever
from onboard_api.assistant.integrations.ollama import OllamaClient
from onboard_api.assistant.state import AssistantDeps
from onboard_api.assistant.workflows.medical.context import (
    SqliteReadingsProvider,
    StaticEventSource,
    load_events_file,
)
from onboard_api.config import Settings
from onboard_api.repositories.database import init_db
from onboard_api.routers import assistant, astronauts, readings, sensors, status
from onboard_api.wellbeing.router import router as wellbeing_router


def build_assistant_deps(settings: Settings) -> AssistantDeps:
    """Shared clients. No network or index work here: Ollama is called and the
    Chroma client is opened lazily on the first request that needs them."""
    ollama = OllamaClient(
        settings.ollama_base_url,
        settings.ollama_chat_model,
        settings.ollama_embed_model,
        settings.ollama_timeout_seconds,
        json_timeout_seconds=settings.ollama_interpret_timeout_seconds,
    )
    events = load_events_file(settings.demo_events_path) if settings.demo_events_path else []
    return AssistantDeps(
        llm=ollama,
        retriever=GuideRetriever(
            settings.chroma_path,
            settings.guides_collection,
            ollama,
            settings.retrieval_max_distance,
        ),
        readings=SqliteReadingsProvider(settings.db_path),
        events=StaticEventSource(events),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Tests pass their own Settings (e.g. a temp db_path)."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Creates the DB directory and applies pending migrations (schema + seed).
        init_db(settings.db_path, migrations_dir=settings.migrations_dir)
        app.state.settings = settings
        app.state.assistant_deps = build_assistant_deps(settings)
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
    app.include_router(wellbeing_router)
    return app


app = create_app()
