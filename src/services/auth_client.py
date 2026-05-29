from typing import Any, Dict
from uuid import UUID

import httpx

from src.core.config import get_settings


def issue_token(user_id: UUID, timeout: float = 5.0) -> Dict[str, Any]:
    """Call external auth service to issue a token for `user_id`.

    Expects the external service to expose `POST /token` accepting JSON
    payload `{ "user_id": "<uuid>" }` and returning a JSON body with at
    least `access_token` and `token_type`.
    """
    settings = get_settings()
    if not settings.AUTH_SERVICE_URL:
        raise RuntimeError("AUTH_SERVICE_URL is not configured")

    url = f"{settings.AUTH_SERVICE_URL.rstrip('/')}/token"

    resp = httpx.post(url, json={"user_id": str(user_id)}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def validate_token(authorization: str, timeout: float = 5.0) -> Dict[str, Any]:
    """Validate a bearer token against the external auth service."""
    settings = get_settings()
    if not settings.AUTH_SERVICE_URL:
        raise RuntimeError("AUTH_SERVICE_URL is not configured")

    url = f"{settings.AUTH_SERVICE_URL.rstrip('/')}/validate"

    resp = httpx.get(url, headers={"Authorization": authorization}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def delete_token(user_id: UUID, timeout: float = 5.0) -> None:
    """Revoke all tokens for a user at the external auth service (logout).
    
    Expects the external service to expose `DELETE /token` accepting JSON
    payload `{ "user_id": "<uuid>" }` and returning 204 No Content.
    """
    settings = get_settings()
    if not settings.AUTH_SERVICE_URL:
        raise RuntimeError("AUTH_SERVICE_URL is not configured")

    # Use a resource-style path so the DELETE request does not require a body.
    # This avoids issues with clients/proxies that mishandle DELETE bodies.
    url = f"{settings.AUTH_SERVICE_URL.rstrip('/')}/token/{str(user_id)}"

    resp = httpx.delete(url, timeout=timeout)
    resp.raise_for_status()
