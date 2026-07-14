import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
import jwt
from fastapi import Header, HTTPException, status

from app.config import settings

logger = logging.getLogger("app.teams_auth")

JWKS_CACHE_TTL_SECONDS = 24 * 60 * 60

_cached_keys: Dict[str, Any] = {}
_cached_at: float = 0.0


def _expected_issuers(tenant_id: str) -> List[str]:
    # Teams SSO tokens can be issued as v1 or v2 depending on the app registration's
    # `accessTokenAcceptedVersion`, so both issuer shapes are accepted.
    return [
        f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        f"https://sts.windows.net/{tenant_id}/",
    ]


async def _fetch_signing_keys(tenant_id: str) -> Dict[str, Any]:
    url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        jwks = response.json()["keys"]
    return {jwk["kid"]: jwt.algorithms.RSAAlgorithm.from_jwk(jwk) for jwk in jwks}


async def _get_signing_key(tenant_id: str, kid: str) -> Any:
    global _cached_keys, _cached_at

    if not _cached_keys or time.time() - _cached_at > JWKS_CACHE_TTL_SECONDS or kid not in _cached_keys:
        try:
            _cached_keys = await _fetch_signing_keys(tenant_id)
            _cached_at = time.time()
        except Exception as exc:
            logger.exception("Failed to fetch Azure AD signing keys")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Unable to verify token signature"
            ) from exc

    key = _cached_keys.get(kid)
    if key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unable to verify token signature")
    return key


@dataclass
class TeamsUser:
    oid: str
    name: Optional[str]
    preferred_username: Optional[str]

    @property
    def display_label(self) -> str:
        return self.preferred_username or self.name or self.oid


async def get_current_teams_user(authorization: Optional[str] = Header(None)) -> TeamsUser:
    """Validate an Azure AD access token (Teams Tab SSO or the standalone MSAL web app)."""
    if not settings.azure_tenant_id or not settings.azure_client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AZURE_TENANT_ID and AZURE_CLIENT_ID must be set to validate Teams SSO tokens",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization[len("Bearer "):]

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token") from exc

    kid = header.get("kid")
    if not kid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")

    signing_key = await _get_signing_key(settings.azure_tenant_id, kid)

    try:
        payload = jwt.decode(
            token,
            key=signing_key,
            algorithms=["RS256"],
            audience=settings.azure_client_id,
            issuer=_expected_issuers(settings.azure_tenant_id),
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}") from exc

    return TeamsUser(
        oid=payload.get("oid"),
        name=payload.get("name"),
        preferred_username=payload.get("preferred_username") or payload.get("upn"),
    )
