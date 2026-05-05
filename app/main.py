"""
FastAPI application entry point.

Responsibilities:
  - Create and configure the FastAPI app.
  - Initialise all services on startup (OpenRouter, Supabase, state machine).
  - Register routers.
  - Configure CORS and structured logging.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.state_machine import StateMachine
from app.agent.states import load_agent_config
from app.api.routes import chat, health
from app.config import get_settings
from app.services.openrouter_service import OpenRouterService
from app.services.supabase_service import SupabaseService

# ── Logging ───────────────────────────────────────────────────────────────────

def configure_logging(level: str) -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # Silence overly verbose third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Startup / shutdown lifecycle manager.

    On startup:
      1. Load configuration from environment.
      2. Load and validate the agent state machine config from YAML.
      3. Initialise OpenRouter and Supabase services.
      4. Attach everything to app.state for dependency-free access in routes.

    On shutdown:
      - Gracefully close any open connections (currently handled by clients internally).
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Starting Coda Agent Template (env=%s)", settings.app_env)

    # Load agent config
    agent_config = load_agent_config(settings.agent_config_path)
    logger.info(
        "Loaded agent '%s' with %d states",
        agent_config.agent_name,
        len(agent_config.states),
    )

    # Initialise services
    openrouter_service = OpenRouterService(settings=settings)
    supabase_service = await SupabaseService.create(settings=settings)

    # Assemble state machine
    state_machine = StateMachine(
        config=agent_config,
        openrouter_service=openrouter_service,
        supabase_service=supabase_service,
        max_conversation_turns=settings.max_conversation_turns,
    )

    # Attach to app.state for access in route handlers
    app.state.settings = settings
    app.state.agent_config = agent_config
    app.state.openrouter_service = openrouter_service
    app.state.supabase_service = supabase_service
    app.state.state_machine = state_machine

    logger.info("All services initialised. Ready to serve requests.")
    yield

    logger.info("Shutting down Coda Agent Template.")


# ── Application factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Coda Agent Template",
        description=(
            "A production-ready, multi-state conversational AI agent scaffold. "
            "Powered by OpenRouter (Llama 3.1 70B) with Supabase persistence."
        ),
        version="1.0.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api/v1")

    return app


app = create_app()
