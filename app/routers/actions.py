"""Action CRUD. GET is public (dashboard); writes require admin."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from .. import scripts as script_utils
from .. import store
from ..auth import admin_required
from ..models import Action, ActionCreate, ActionUpdate

router = APIRouter(prefix="/api/v1/actions", tags=["actions"])


@router.get("")
def list_actions() -> list[dict]:
    """Public list for the dashboard — secret templates stripped."""
    return [a.public_dict() for a in store.list_actions()]


@router.get("/{action_id}")
def get_action(action_id: str) -> dict:
    action = store.get_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    return action.public_dict()


def _validate_script(script_path: str) -> None:
    try:
        script_utils.resolve_script(script_path)
    except script_utils.ScriptError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("", dependencies=[Depends(admin_required)], status_code=201)
def create_action(payload: ActionCreate) -> Action:
    _validate_script(payload.script_path)
    return store.create_action(payload)


@router.put("/{action_id}", dependencies=[Depends(admin_required)])
def update_action(action_id: str, payload: ActionUpdate) -> Action:
    _validate_script(payload.script_path)
    updated = store.update_action(action_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Action not found")
    return updated


@router.delete("/{action_id}", dependencies=[Depends(admin_required)])
def delete_action(action_id: str) -> Response:
    if not store.delete_action(action_id):
        raise HTTPException(status_code=404, detail="Action not found")
    return Response(status_code=204)
