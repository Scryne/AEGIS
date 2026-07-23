"""/api/v1 router toplayıcısı."""

from __future__ import annotations

from fastapi import APIRouter

from aegis_api.routers.v1 import audit, auth, members, settings, system

api_v1_router = APIRouter()
api_v1_router.include_router(audit.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(members.router)
api_v1_router.include_router(settings.router)
api_v1_router.include_router(system.router)

__all__ = ["api_v1_router"]
