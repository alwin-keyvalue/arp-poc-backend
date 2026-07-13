import logging
import time
from typing import Optional

import aiohttp

from app.config import settings

logger = logging.getLogger("app.teams_bot")

GRAPH_SCOPE = "https://graph.microsoft.com/.default"

_cached_token: Optional[str] = None
_cached_token_expiry: float = 0.0


async def _get_graph_access_token() -> str:
    global _cached_token, _cached_token_expiry

    if _cached_token and time.time() < _cached_token_expiry:
        return _cached_token

    if not (settings.bot_app_id and settings.bot_app_password and settings.bot_app_tenant_id):
        raise RuntimeError("BOT_APP_ID / BOT_APP_PASSWORD / BOT_APP_TENANT_ID are not configured")

    token_url = f"https://login.microsoftonline.com/{settings.bot_app_tenant_id}/oauth2/v2.0/token"
    async with aiohttp.ClientSession() as session:
        async with session.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.bot_app_id,
                "client_secret": settings.bot_app_password,
                "scope": GRAPH_SCOPE,
            },
        ) as response:
            body = await response.json()
            if response.status != 200:
                raise RuntimeError(f"Failed to get Graph access token: {body}")

    _cached_token = body["access_token"]
    _cached_token_expiry = time.time() + int(body.get("expires_in", 3600)) - 60
    return _cached_token


async def get_user_email(aad_object_id: str) -> Optional[str]:
    """Look up a Teams user's email via Microsoft Graph (app-only auth). Returns None on any failure."""
    if not aad_object_id:
        return None

    try:
        token = await _get_graph_access_token()
        url = f"https://graph.microsoft.com/v1.0/users/{aad_object_id}?$select=mail,userPrincipalName"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={"Authorization": f"Bearer {token}"}) as response:
                body = await response.json()
                if response.status != 200:
                    logger.warning("Graph user lookup failed for %s: %s", aad_object_id, body)
                    return None
                return body.get("mail") or body.get("userPrincipalName")
    except Exception:
        logger.exception("Failed to fetch user email from Graph for %s", aad_object_id)
        return None
