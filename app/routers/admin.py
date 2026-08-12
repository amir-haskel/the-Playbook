"""Admin session login/logout and script discovery for the builder."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import auth, scripts as script_utils
from ..models import LoginRequest

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/login")
def login(payload: LoginRequest, request: Request) -> dict:
    if not auth.verify_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    auth.login_session(request)
    return {"authenticated": True}


@router.post("/logout")
def logout(request: Request) -> dict:
    auth.logout_session(request)
    return {"authenticated": False}


@router.get("/session")
def session(request: Request) -> dict:
    return {"authenticated": auth.is_authenticated(request)}


@router.get("/scripts", dependencies=[Depends(auth.admin_required)])
def list_scripts() -> dict:
    """Available scripts under SCRIPTS_DIR for the builder's path picker."""
    return {"scripts": script_utils.list_scripts()}
