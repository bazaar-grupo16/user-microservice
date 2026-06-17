from typing import Any, Dict

import httpx

_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


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
