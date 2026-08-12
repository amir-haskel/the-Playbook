"""App settings (currently just the history retention limit)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import store
from ..auth import admin_required

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class SettingsIn(BaseModel):
    history_limit: int = Field(..., ge=1, le=1000)


@router.get("")
def get_settings() -> dict:
    """Public: the dashboard needs the history limit to size its list."""
    return {"history_limit": store.get_history_limit()}


@router.put("", dependencies=[Depends(admin_required)])
def update_settings(payload: SettingsIn) -> dict:
    store.set_setting("history_limit", str(payload.history_limit))
    removed = store.prune_executions(payload.history_limit)
    return {"history_limit": store.get_history_limit(), "pruned": removed}
