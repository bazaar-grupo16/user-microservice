from typing import Any, Dict
from uuid import UUID

import httpx

from src.core.config import get_settings
from src.core.observability import build_observability_headers


async def issue_token(user_id: UUID, is_admin: bool, timeout: float = 5.0) -> Dict[str, Any]:
    """Call external auth service to issue a token for `user_id`.

    Expects the external service to expose `POST /token` accepting JSON
    payload `{ "user_id": "<uuid>", "is_admin": <bool> }` and returning a
    JSON body with at least `access_token` and `token_type`.
    """
    settings = get_settings()
    if not settings.AUTH_SERVICE_URL:
        raise RuntimeError("AUTH_SERVICE_URL is not configured")

    url = f"{settings.AUTH_SERVICE_URL.rstrip('/')}/token"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json={"user_id": str(user_id), "is_admin": is_admin},
            headers=build_observability_headers(),
            timeout=timeout,
        )

    resp.raise_for_status()
    return resp.json()


async def validate_token(authorization: str, timeout: float = 5.0) -> Dict[str, Any]:
    """Validate a bearer token against the external auth service."""
    settings = get_settings()
    if not settings.AUTH_SERVICE_URL:
        raise RuntimeError("AUTH_SERVICE_URL is not configured")

    url = f"{settings.AUTH_SERVICE_URL.rstrip('/')}/validate"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={"Authorization": authorization, **build_observability_headers()},
            timeout=timeout,
        )
    resp.raise_for_status()
    return resp.json()


async def delete_token(user_id: UUID, timeout: float = 5.0) -> None:
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

    async with httpx.AsyncClient() as client:
        resp = await client.delete(url, timeout=timeout, headers=build_observability_headers())
    resp.raise_for_status()
