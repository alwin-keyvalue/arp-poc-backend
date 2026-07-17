from typing import Optional

from fastapi import Header, HTTPException, status

from app.config import settings
from app.core.teams_auth import TeamsUser, get_current_teams_user


def verify_internal_auth_secret(x_internal_auth_secret: str = Header(...)) -> None:
    """Require a matching X-Internal-Auth-Secret header for internal/admin endpoints."""
    if not settings.internal_auth_secret or x_internal_auth_secret != settings.internal_auth_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing internal auth secret",
        )


def _secret_is_valid(x_internal_auth_secret: Optional[str]) -> bool:
    return bool(
        settings.internal_auth_secret
        and x_internal_auth_secret
        and x_internal_auth_secret == settings.internal_auth_secret
    )


async def require_internal_secret_or_teams_user(
    x_internal_auth_secret: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
) -> Optional[TeamsUser]:
    """Accept either a valid internal auth secret or a Teams Bearer token."""
    if _secret_is_valid(x_internal_auth_secret):
        return True
    return await get_current_teams_user(authorization)
