from __future__ import annotations

import time

import httpx

from app.config import settings

TOKEN_URL = "https://login.microsoftonline.com"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"


class GraphAuth:
    def __init__(self) -> None:
        self._cached_token: str | None = None
        self._expires_at: float = 0.0

    async def get_app_access_token(self, client: httpx.AsyncClient) -> str:
        if self._cached_token and time.time() < self._expires_at - 60:
            return self._cached_token

        if not settings.azure_tenant_id:
            raise ValueError("AZURE_TENANT_ID is not configured")
        if not settings.azure_client_id:
            raise ValueError("AZURE_CLIENT_ID is not configured")
        if not settings.azure_client_secret:
            raise ValueError("AZURE_CLIENT_SECRET is not configured")

        token_url = f"{TOKEN_URL}/{settings.azure_tenant_id}/oauth2/v2.0/token"
        response = await client.post(
            token_url,
            data={
                "client_id": settings.azure_client_id,
                "client_secret": settings.azure_client_secret,
                "scope": GRAPH_SCOPE,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        payload = response.json()

        self._cached_token = payload["access_token"]
        self._expires_at = time.time() + payload.get("expires_in", 3600)
        return self._cached_token


graph_auth = GraphAuth()
