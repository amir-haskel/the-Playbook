"""Live dropdown option fetching (the only outbound-API endpoint)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .. import http_client, store
from ..auth import admin_required
from ..models import Parameter, ParamType

router = APIRouter(prefix="/api/v1", tags=["dynamic"])


class DropdownTest(BaseModel):
    dynamic_type: str | None = None
    endpoint: str | None = None
    response_key: str | None = None
    auth_header: str | None = None


@router.post("/dynamic-options/test", dependencies=[Depends(admin_required)])
async def test_dropdown(cfg: DropdownTest) -> dict:
    """Admin: run a dynamic dropdown's config on demand (before saving the
    action) and return the fetched options, or a readable error."""
    # Throwaway param used only to carry the dynamic config into fetch_options;
    # its name is never surfaced, but it must still satisfy the Parameter name
    # rule (must start with a letter), so use a plain placeholder rather than
    # "_test" (a leading underscore is rejected by the name validator).
    param = Parameter(
        name="Test",
        type=ParamType.dynamic_select,
        dynamic_type=cfg.dynamic_type,
        endpoint=cfg.endpoint,
        response_key=cfg.response_key,
        auth_header=cfg.auth_header,
    )
    try:
        options = await http_client.fetch_options(param)
    except http_client.DynamicOptionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"count": len(options), "options": [o.model_dump() for o in options]}


@router.get("/dynamic-options/{type}")
async def dynamic_options(
    type: str,
    action_id: str = Query(..., description="Action owning the parameter"),
    param: str = Query(..., description="Parameter name to resolve"),
) -> list[dict]:
    """Resolve options for a dynamic_select parameter.

    ``type`` is the dropdown's dynamic_type; ``action_id`` + ``param`` locate the
    stored config (endpoint, response_key, secret-bearing auth header). Secrets
    are injected server-side and never returned to the caller.
    """
    action = store.get_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")

    parameter: Parameter | None = next(
        (p for p in action.parameters if p.name == param), None
    )
    if parameter is None:
        raise HTTPException(status_code=404, detail="Parameter not found")
    # A dynamic dropdown (dynamic_select) or a checkbox group whose options are
    # fetched from a dynamic source both resolve options the same way — they just
    # render differently on the run form.
    is_dynamic_select = parameter.type.value == "dynamic_select"
    is_dynamic_checkbox = parameter.type.value == "checkbox" and bool(
        parameter.endpoint or parameter.dynamic_type
    )
    if not (is_dynamic_select or is_dynamic_checkbox):
        raise HTTPException(status_code=400, detail="Parameter has no dynamic source")

    # ``type`` from the path takes precedence for source resolution.
    if type and type != "custom":
        parameter = parameter.model_copy(update={"dynamic_type": type})

    try:
        options = await http_client.fetch_options(parameter)
    except http_client.DynamicOptionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return [o.model_dump() for o in options]
