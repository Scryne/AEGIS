"""/api/v1 router toplayıcısı."""

from __future__ import annotations

from fastapi import APIRouter

from aegis_api.routers.v1 import (
    adverse_media,
    audit,
    auth,
    batches,
    billing,
    cases,
    documents,
    entities,
    members,
    monitoring,
    reports,
    risk_score,
    screenings,
    settings,
    sib,
    system,
    ubo,
)

api_v1_router = APIRouter()
api_v1_router.include_router(adverse_media.router)
api_v1_router.include_router(audit.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(batches.router)
api_v1_router.include_router(billing.router)
api_v1_router.include_router(cases.router)
api_v1_router.include_router(documents.router)
api_v1_router.include_router(entities.router)
api_v1_router.include_router(members.router)
api_v1_router.include_router(monitoring.router)
api_v1_router.include_router(reports.router)
api_v1_router.include_router(risk_score.router)
api_v1_router.include_router(screenings.router)
api_v1_router.include_router(settings.router)
api_v1_router.include_router(sib.router)
api_v1_router.include_router(system.router)
api_v1_router.include_router(ubo.router)

__all__ = ["api_v1_router"]
