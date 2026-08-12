"""Outbound HTTP for dynamic dropdowns — the ONLY place OpsPulse calls APIs.

A dropdown parameter declares an endpoint, an optional secret-bearing auth
header, and a ``response_key`` describing how to pluck option values out of the
JSON response. Secrets are injected here, server-side, and never returned to
the browser.
"""
from __future__ import annotations

from typing import Any

import httpx

from . import secrets as secret_utils
from .config import settings
from .models import OptionItem, Parameter

# Well-known dynamic sources map to a base URL + default auth header. Custom
# dropdowns can override endpoint/auth_header on the parameter itself.
BUILTIN_SOURCES: dict[str, dict[str, str]] = {
    "gitlab-branches": {
        "base": "${GITLAB_API_URL}",
        "auth_header": "PRIVATE-TOKEN: ${GITLAB_TOKEN}",
        "response_key": "[].name",
    },
    "oc-namespaces": {
        "base": "${OPENSHIFT_API_URL}",
        "auth_header": "Authorization: Bearer ${OPENSHIFT_TOKEN}",
        "response_key": "items[].metadata.name",
    },
}


class DynamicOptionError(RuntimeError):
    pass


def parse_response_key(data: Any, key: str) -> list[str]:
    """Extract a flat list of strings from ``data`` using a ``response_key``.

    Supports dotted paths and a single ``[]`` list projection, e.g.::

        "[].name"                  -> [d["name"] for d in data]
        "items[].metadata.name"    -> [i["metadata"]["name"] for i in data["items"]]
        "value"                    -> [data["value"]]  (scalar)

    Unresolvable segments are skipped rather than raising, so a partially
    shaped response still yields whatever options it can.
    """
    key = (key or "").strip()
    if not key:
        # No key: best-effort — a top-level list of scalars.
        if isinstance(data, list):
            return [str(x) for x in data if _is_scalar(x)]
        return []

    before, sep, after = key.partition("[]")
    if not sep:
        # No list projection: walk a dotted path to a scalar or list.
        value = _walk(data, key)
        if isinstance(value, list):
            return [str(x) for x in value if _is_scalar(x)]
        return [str(value)] if _is_scalar(value) else []

    # List projection: <before>[] . <after>
    container = _walk(data, before.strip(".")) if before.strip(".") else data
    if not isinstance(container, list):
        return []

    after = after.strip(".")
    out: list[str] = []
    for item in container:
        value = _walk(item, after) if after else item
        if _is_scalar(value):
            out.append(str(value))
    return out


def _walk(obj: Any, dotted: str) -> Any:
    if not dotted:
        return obj
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _is_scalar(x: Any) -> bool:
    return isinstance(x, (str, int, float, bool))


def _resolve_source(param: Parameter) -> tuple[str, str, str]:
    """Return (url, auth_header_template, response_key) for a dropdown param."""
    builtin = BUILTIN_SOURCES.get(param.dynamic_type or "", {})

    # Endpoint supports ${VAR} substitution so a manually-configured dropdown
    # can reference ${GITLAB_API_URL} / ${OPENSHIFT_API_URL} directly.
    endpoint = secret_utils.substitute(param.endpoint or "")
    base = builtin.get("base", "")
    if endpoint.startswith(("http://", "https://")):
        url = endpoint
    else:
        base_url = secret_utils.substitute(base).rstrip("/")
        url = f"{base_url}/{endpoint.lstrip('/')}" if base_url else endpoint

    auth_header = param.auth_header or builtin.get("auth_header", "")
    response_key = param.response_key or builtin.get("response_key", "")
    return url, auth_header, response_key


async def fetch_options(param: Parameter) -> list[OptionItem]:
    """Fetch and parse dropdown options for a dynamic_select parameter."""
    url, auth_header, response_key = _resolve_source(param)
    if not url:
        raise DynamicOptionError(
            "dynamic dropdown has no resolvable endpoint (set endpoint or a "
            "known dynamic_type)."
        )

    headers = secret_utils.parse_header(auth_header)
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise DynamicOptionError(f"upstream request failed: {exc}") from exc
    except ValueError as exc:  # non-JSON body
        raise DynamicOptionError(f"upstream returned non-JSON: {exc}") from exc

    values = parse_response_key(data, response_key)
    # De-duplicate while preserving order.
    seen: set[str] = set()
    options: list[OptionItem] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            options.append(OptionItem(value=v, label=v))
    return options
