from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict:
    settings = request.app.state.settings
    database = request.app.state.database
    state, error = await database.status()

    response = {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "database": state,
        "schemas": settings.schemas,
    }
    if error and settings.environment != "production":
        response["databaseError"] = error
    return response
