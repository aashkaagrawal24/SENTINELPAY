from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db_session

router = APIRouter()


@router.get("/health")
def health(request: Request):
    return {"status": "ok", "correlation_id": request.state.correlation_id}


@router.get("/ready")
def ready(request: Request, db: Session = Depends(get_db_session)):
    db.execute(text("select 1"))
    return {"status": "ready", "correlation_id": request.state.correlation_id}


@router.get("/api/me")
def me(user: AuthenticatedUser = Depends(get_current_user)):
    return {"id": str(user.id), "email": user.email}


@router.get("/api/version")
def version(settings: Settings = Depends(get_settings)):
    return {"name": "sentinelpay", "version": settings.app_version, "environment": settings.app_env}
