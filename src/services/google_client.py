from typing import Any, Dict

from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from src.core.config import get_settings


def verify_id_token(id_token: str) -> Dict[str, Any]:
    # NOTE: ``google.oauth2.id_token.verify_oauth2_token`` performs a *blocking*
    # network call (via google-auth's sync transport) and has no async
    # equivalent without adding a new dependency.  Callers must therefore
    # invoke this from async code through ``asyncio.to_thread`` so the event
    # loop is not blocked.
    settings = get_settings()
    if not settings.GOOGLE_CLIENT_ID:
        raise RuntimeError("GOOGLE_CLIENT_ID is not configured")
    return google_id_token.verify_oauth2_token(
        id_token,
        google_requests.Request(),
        settings.GOOGLE_CLIENT_ID,
    )
