"""
Health check endpoint.

GET /health — used by Railway, load balancers, and monitoring tools.
Returns 200 OK if all downstream services are reachable, 503 otherwise.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.models.schemas import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])

VERSION = "1.0.0"


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    description="Returns 200 when all dependencies are reachable, 503 otherwise.",
)
async def health(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    llm_svc = request.app.state.openrouter_service
    db_svc = request.app.state.supabase_service

    checks: dict[str, str] = {}
    all_ok = True

    # Check OpenRouter
    try:
        llm_ok = await llm_svc.health_check()
        checks["openrouter"] = "ok" if llm_ok else "unreachable"
        if not llm_ok:
            all_ok = False
    except Exception as exc:
        checks["openrouter"] = f"error: {exc}"
        all_ok = False

    # Check Supabase
    try:
        db_ok = await db_svc.health_check()
        checks["supabase"] = "ok" if db_ok else "unreachable"
        if not db_ok:
            all_ok = False
    except Exception as exc:
        checks["supabase"] = f"error: {exc}"
        all_ok = False

    payload = HealthResponse(
        status="ok" if all_ok else "degraded",
        version=VERSION,
        environment=settings.app_env,
        checks=checks,
    )

    status_code = 200 if all_ok else 503
    return JSONResponse(content=payload.model_dump(), status_code=status_code)
