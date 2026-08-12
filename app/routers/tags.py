"""Tag bank CRUD. GET is public (dashboard filter + card pills); writes admin."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from .. import store
from ..auth import admin_required
from ..models import Tag, TagCreate

router = APIRouter(prefix="/api/v1/tags", tags=["tags"])


@router.get("")
def list_tags() -> list[Tag]:
    return store.list_tags()


@router.post("", dependencies=[Depends(admin_required)], status_code=201)
def create_tag(payload: TagCreate) -> Tag:
    return store.create_tag(payload)


@router.put("/{tag_id}", dependencies=[Depends(admin_required)])
def update_tag(tag_id: str, payload: TagCreate) -> Tag:
    updated = store.update_tag(tag_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return updated


@router.delete("/{tag_id}", dependencies=[Depends(admin_required)])
def delete_tag(tag_id: str) -> Response:
    if not store.delete_tag(tag_id):
        raise HTTPException(status_code=404, detail="Tag not found")
    return Response(status_code=204)
