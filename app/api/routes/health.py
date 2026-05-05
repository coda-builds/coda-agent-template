"""
Health check endpoints.

GET /health  — liveness probe used by Railway and load balancers.
               Always returns 200 if the process is running.
               Railway uses this to decide whether to route traffic —
               it should not call external APIs.

GET /ready   — readiness probe for dependency checks.
               Returns 200 if OpenRouter and Supabase are reachable, 503 otherwise.
               Call this from your own monitoring; do not use as Railway's healthcheck.
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
    summary="Liveness probe",
    description=(
        "Returns 200 if the process is running. Used by Railway's healthcheck. "
        "Does not call external APIs."
    ),
)
async def health(request: Request) -> JSONResponse:
    """
    Liveness check — always 200 if the app is up.

    Railway polls this every 30 seconds to decide whether the deployment
    succeeded and whether to keep routing traffic. Calling external APIs
    here would cause Railway to mark the deployment as failed any time
    a dependency has a transient error or billing issue.
    """
    settings = request.app.state.settings
    payload = HealthResponse(
        status="ok",
        version=VERSION,
        environment=settings.app_env,
        checks={"process": "ok"},
    )
    return JSONResponse(content=payload.model_dump(), status_code=200)


@router.get(
    "/ready",
    response_model=HealthResponse,
    summary="Readiness probe — checks external dependencies",
    description=(
        "Returns 200 if OpenRouter and Supabase are reachable, 503 otherwise. "
        "Use this for monitoring dashboards, not Railway's healthcheck."
    ),
)
async def ready(request: Request) -> JSONResponse:
    """
    Readiness check — calls OpenRouter and Supabase.

    Use this endpoint in your monitoring stack (e.g. UptimeRobot, Datadog)
    to alert on dependency failures. Do NOT configure Railway to poll this —
    a billing issue or transient API error would take your deployment offline.
    """
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
