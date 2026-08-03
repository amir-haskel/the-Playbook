"""Action CRUD. GET is public (dashboard); writes require admin."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from .. import scripts as script_utils
from .. import store
from ..auth import admin_required
from ..models import Action, ActionCreate, ActionUpdate

router = APIRouter(prefix="/api/v1/actions", tags=["actions"])


def _serialize(action, tag_map: dict) -> dict:
    """Public action dict with resolved tag_details (id, name, color, type)."""
    data = action.public_dict()
    data["tag_details"] = [
        {"id": t.id, "name": t.name, "color": t.color, "type": t.type.value}
        for tid in action.tags
        if (t := tag_map.get(tid)) is not None
    ]
    return data


def _validate_tags(tag_ids: list[str]) -> None:
    """An action may carry at most one function tag and at most one team tag."""
    tag_map = {t.id: t for t in store.list_tags()}
    functions = [tid for tid in tag_ids if (t := tag_map.get(tid)) and t.type.value == "function"]
    teams = [tid for tid in tag_ids if (t := tag_map.get(tid)) and t.type.value == "team"]
    if len(functions) > 1:
        raise HTTPException(status_code=400, detail="An action may have at most one function tag")
    if len(teams) > 1:
        raise HTTPException(status_code=400, detail="An action may have at most one team")


@router.get("")
def list_actions() -> list[dict]:
    """Public list for the dashboard — secret templates stripped."""
    tag_map = {t.id: t for t in store.list_tags()}
    return [_serialize(a, tag_map) for a in store.list_actions()]


@router.get("/{action_id}")
def get_action(action_id: str) -> dict:
    action = store.get_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    tag_map = {t.id: t for t in store.list_tags()}
    return _serialize(action, tag_map)


def _validate_script(script_path: str) -> None:
    try:
        script_utils.resolve_script(script_path)
    except script_utils.ScriptError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("", dependencies=[Depends(admin_required)], status_code=201)
def create_action(payload: ActionCreate) -> Action:
    _validate_script(payload.script_path)
    _validate_tags(payload.tags)
    return store.create_action(payload)


@router.put("/{action_id}", dependencies=[Depends(admin_required)])
def update_action(action_id: str, payload: ActionUpdate) -> Action:
    _validate_script(payload.script_path)
    _validate_tags(payload.tags)
    updated = store.update_action(action_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Action not found")
    return updated


@router.delete("/{action_id}", dependencies=[Depends(admin_required)])
def delete_action(action_id: str) -> Response:
    if not store.delete_action(action_id):
        raise HTTPException(status_code=404, detail="Action not found")
    return Response(status_code=204)
