"""Cookie/session-based admin authentication.

A successful POST to /api/v1/admin/login sets a signed session flag. Admin-only
endpoints depend on ``admin_required`` which rejects unauthenticated requests
with 401. Passwords are compared in constant time.
"""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

from .config import settings

SESSION_KEY = "playbook_admin"


def verify_password(candidate: str) -> bool:
    """Constant-time comparison against ADMIN_PASSWORD.

    Returns False when no admin password is configured (fail closed).
    """
    if not settings.admin_password:
        return False
    return hmac.compare_digest(candidate or "", settings.admin_password)


def login_session(request: Request) -> None:
    request.session[SESSION_KEY] = True


def logout_session(request: Request) -> None:
    request.session.pop(SESSION_KEY, None)


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get(SESSION_KEY))


def admin_required(request: Request) -> None:
    """FastAPI dependency guarding admin routes."""
    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required.",
        )
