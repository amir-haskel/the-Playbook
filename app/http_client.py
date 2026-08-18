"""Outbound HTTP for dynamic dropdowns — the ONLY place OpsPulse calls APIs.

A dropdown parameter declares an endpoint, an optional secret-bearing auth
header, and a ``response_key`` describing how to pluck option values out of the
JSON response. Secrets are injected here, server-side, and never returned to
the browser.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from . import secrets as secret_utils
from .config import settings
from .models import OptionItem, Parameter

# --- Pagination safety caps -------------------------------------------------
# Real paged APIs (GitLab, Nexus, …) serve results in pages of <=100. We follow
# the paging chain and aggregate every page, but bound the walk so a
# mis-detected or misbehaving endpoint can never loop forever.
MAX_PAGES = 60          # never follow more than this many pages
MAX_ITEMS = 10_000      # never aggregate more than this many parsed values

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


_NATURAL_CHUNK = re.compile(r"\d+")


def _natural_key(text: str) -> list[tuple[int, Any]]:
    """Build a natural/version-aware sort key for ``text``.

    The string is split into alternating non-digit / digit chunks. Digit chunks
    compare numerically (as ints), text chunks compare case-insensitively. Each
    chunk is tagged with a leading type flag (0 = text, 1 = number) so a text
    chunk is never compared against a numeric chunk. This yields the expected
    order for embedded separators and leading ``v`` markers::

        1.2.9  <  1.2.10          (9 < 10 numerically, not lexically)
        v2     <  v10             ("v" ties, then 2 < 10)

    Ascending order only. (For newest-first the caller can reverse visually.)
    """
    key: list[tuple[int, Any]] = []
    pos = 0
    for match in _NATURAL_CHUNK.finditer(text or ""):
        if match.start() > pos:
            key.append((0, text[pos:match.start()].lower()))
        key.append((1, int(match.group())))
        pos = match.end()
    if pos < len(text or ""):
        key.append((0, text[pos:].lower()))
    return key


def _sort_options(options: list[OptionItem], sort: str) -> list[OptionItem]:
    """Order fetched options by the parameter's ``sort`` mode.

    ``"none"`` preserves the as-returned (de-duplicated) order; ``"alpha"`` sorts
    case-insensitively by label (falling back to value); ``"version"`` applies a
    natural/version-aware sort (see ``_natural_key``). Unknown modes are treated
    as ``"none"``. Sorting is stable, so ties keep their original relative order.
    """
    mode = sort if sort in ("none", "alpha", "version") else "none"
    if mode == "alpha":
        return sorted(options, key=lambda o: (o.label or o.value).lower())
    if mode == "version":
        return sorted(options, key=lambda o: _natural_key(o.label or o.value))
    return options


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


_LINK_NEXT = re.compile(r"<([^>]+)>\s*;[^,]*\brel\s*=\s*\"?next\"?", re.IGNORECASE)


def _parse_link_next(link_header: str | None) -> str | None:
    """Return the URL of the ``rel="next"`` entry in an RFC 5988 Link header.

    GitLab (and many others) return e.g.::

        <https://gl/api/v4/projects?page=2&per_page=100>; rel="next", <...>; rel="last"
    """
    if not link_header:
        return None
    match = _LINK_NEXT.search(link_header)
    return match.group(1).strip() if match else None


def _set_query_param(url: str, key: str, value: str) -> str:
    """Return ``url`` with query parameter ``key`` set/overwritten to ``value``."""
    parts = urlparse(url)
    pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != key]
    pairs.append((key, value))
    return urlunparse(parts._replace(query=urlencode(pairs)))


def _query_value(url: str, key: str) -> str | None:
    """Return the current value of query parameter ``key`` (or ``None``)."""
    for k, v in parse_qsl(urlparse(url).query, keep_blank_values=True):
        if k == key:
            return v
    return None


def _next_page_url(
    current_url: str,
    data: Any,
    resp_headers: Any,
    raw_count: int,
    added: int,
) -> str | None:
    """Auto-detect the next page's URL from a response, or ``None`` when done.

    Detection order (first match wins), covering the common paging styles:

    1. **Link header** ``rel="next"`` (GitLab, GitHub, many REST APIs).
    2. **X-Next-Page** header (GitLab): the next page number; blank when last.
    3. **continuationToken** in the JSON body (Nexus): re-request with
       ``?continuationToken=…`` until the token is null/absent.
    4. **Generic offset/limit or ``?page=`` incrementing**: only when the
       endpoint was already configured with an ``offset`` or ``page`` query
       param, and only while the page is still yielding *new* values — so a
       non-paginated endpoint that ignores the param stops after one page.
    """
    # 1. RFC 5988 Link header (GitLab, GitHub, …). If present it is authoritative:
    #    follow rel="next", or stop when there is no next — never fall through to
    #    the generic guess (which would over-fetch past the real last page).
    link = resp_headers.get("link")
    if link is not None:
        return _parse_link_next(link)

    # 2. GitLab X-Next-Page header: the next page number, blank on the last page.
    #    Also authoritative when present.
    x_next = resp_headers.get("x-next-page")
    if x_next is not None:
        x_next = x_next.strip()
        return _set_query_param(current_url, "page", x_next) if x_next else None

    # 3. Nexus-style continuation token embedded in the JSON body. Present-but-null
    #    means "last page"; absent means this isn't a token-paged response.
    if isinstance(data, dict) and "continuationToken" in data:
        token = data.get("continuationToken")
        return _set_query_param(current_url, "continuationToken", str(token)) if token else None

    # 4. Generic increment — only when opted into via an existing query param and
    #    the page is still contributing new, non-duplicate values.
    if raw_count > 0 and added > 0:
        offset = _query_value(current_url, "offset")
        if offset is not None and offset.isdigit():
            return _set_query_param(current_url, "offset", str(int(offset) + raw_count))
        page = _query_value(current_url, "page")
        if page is not None and page.isdigit():
            return _set_query_param(current_url, "page", str(int(page) + 1))

    return None


async def fetch_options(param: Parameter) -> list[OptionItem]:
    """Fetch and parse dropdown options for a dynamic_select parameter.

    Walks the upstream paging chain (auto-detected — see ``_next_page_url``) and
    aggregates every page's parsed options into one ordered, de-duplicated list.
    The walk is bounded by ``MAX_PAGES`` / ``MAX_ITEMS`` and every request
    respects the configured ``HTTP_TIMEOUT``. The aggregated list is finally
    ordered per the parameter's ``sort`` mode (see ``_sort_options``).
    """
    url, auth_header, response_key = _resolve_source(param)
    if not url:
        raise DynamicOptionError(
            "dynamic dropdown has no resolvable endpoint (set endpoint or a "
            "known dynamic_type)."
        )

    headers = secret_utils.parse_header(auth_header)
    seen: set[str] = set()
    options: list[OptionItem] = []
    next_url: str | None = url
    pages = 0

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            while next_url and pages < MAX_PAGES and len(options) < MAX_ITEMS:
                pages += 1
                resp = await client.get(next_url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                values = parse_response_key(data, response_key)
                added = 0
                for v in values:
                    if v not in seen:
                        seen.add(v)
                        options.append(OptionItem(value=v, label=v))
                        added += 1
                        if len(options) >= MAX_ITEMS:
                            break

                next_url = _next_page_url(
                    next_url, data, resp.headers, raw_count=len(values), added=added
                )
    except httpx.HTTPError as exc:
        raise DynamicOptionError(f"upstream request failed: {exc}") from exc
    except ValueError as exc:  # non-JSON body
        raise DynamicOptionError(f"upstream returned non-JSON: {exc}") from exc

    return _sort_options(options, getattr(param, "sort", "none"))
