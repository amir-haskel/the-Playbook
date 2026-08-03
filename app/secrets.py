"""Server-side secret substitution.

Dynamic dropdown configs reference pod environment variables via ``${VAR}``
placeholders (e.g. ``PRIVATE-TOKEN: ${GITLAB_TOKEN}``). Substitution happens
here, on the server, immediately before an outbound API call. Substituted
values are NEVER serialised back to the browser.
"""
from __future__ import annotations

import os
import re

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def substitute(template: str | None, extra: dict[str, str] | None = None) -> str:
    """Replace ``${VAR}`` placeholders with environment (or ``extra``) values.

    Unknown variables resolve to an empty string so a missing secret never
    leaks the literal ``${VAR}`` text into an outbound request.
    """
    if not template:
        return ""
    extra = extra or {}

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in extra:
            return extra[name]
        return os.environ.get(name, "")

    return _PLACEHOLDER.sub(repl, template)


def parse_header(header_template: str | None) -> dict[str, str]:
    """Parse a ``Name: value`` header template with secret substitution.

    Returns an empty dict for blank/malformed input.
    """
    if not header_template or ":" not in header_template:
        return {}
    name, _, value = header_template.partition(":")
    name = name.strip()
    value = substitute(value.strip())
    if not name:
        return {}
    return {name: value}
