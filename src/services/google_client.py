from typing import Any, Dict

import httpx
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from src.core.config import get_settings

_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def verify_id_token(id_token: str) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.GOOGLE_CLIENT_ID:
        raise RuntimeError("GOOGLE_CLIENT_ID is not configured")
    return google_id_token.verify_oauth2_token(
        id_token,
        google_requests.Request(),
        settings.GOOGLE_CLIENT_ID,
    )


def get_user_info(access_token: str, timeout: float = 5.0) -> Dict[str, Any]:
    """Fetch the authenticated user's profile from Google using an access token.

    Returns a dict with at least: sub (Google user ID), email, name.
    Raises httpx.HTTPStatusError if the token is invalid or expired.
    """
    resp = httpx.get(
        _USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()
