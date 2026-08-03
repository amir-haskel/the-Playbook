"""Live dropdown option fetching (the only outbound-API endpoint)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .. import http_client, store
from ..models import Parameter

router = APIRouter(prefix="/api/v1", tags=["dynamic"])


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
    if parameter.type.value != "dynamic_select":
        raise HTTPException(status_code=400, detail="Parameter is not a dynamic dropdown")

    # ``type`` from the path takes precedence for source resolution.
    if type and type != "custom":
        parameter = parameter.model_copy(update={"dynamic_type": type})

    try:
        options = await http_client.fetch_options(parameter)
    except http_client.DynamicOptionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return [o.model_dump() for o in options]
