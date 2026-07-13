import logging
from typing import Any, Dict, Optional

import jwt
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.graph_client import get_user_email
from app.repositories.user_repository import UserRepository

logger = logging.getLogger("app.teams_bot")

GREETING_TEXT = (
    "👋 Hi! I'm your Task Bot. Forward me an email or flag a message here and "
    "I'll help turn it into a task."
)


class BotService:
    def __init__(self, adapter: BotFrameworkAdapter):
        self._adapter = adapter

    @staticmethod
    def _bot_was_added(activity: Activity) -> bool:
        recipient_id = activity.recipient.id if activity.recipient else None
        members_added = activity.members_added or []
        return any(member.id == recipient_id for member in members_added)

    def _remember_teams_user(self, activity: Activity, email: str, db: Session) -> None:
        conversation_reference = TurnContext.get_conversation_reference(activity)
        UserRepository(db).upsert_teams_info(
            email=email,
            aad_object_id=activity.from_property.aad_object_id,
            conversation_reference=conversation_reference.serialize(),
            display_name=activity.from_property.name if activity.from_property else None,
        )
        logger.info("Stored Teams conversation reference for %s", email)

    async def _turn_logic(self, activity: Activity, turn_context: TurnContext, db: Session) -> None:
        logger.info("Teams activity received: %s", activity.serialize())

        if activity.type == "conversationUpdate" and self._bot_was_added(activity):
            aad_object_id = activity.from_property.aad_object_id if activity.from_property else None
            email = await get_user_email(aad_object_id)
            logger.info("Teams user email: %s (aadObjectId=%s)", email, aad_object_id)

            if email:
                try:
                    self._remember_teams_user(activity, email, db)
                except Exception:
                    logger.exception("Failed to persist Teams conversation reference for %s", email)

            await turn_context.send_activity(GREETING_TEXT)

    async def receive_activity(self, body: Dict[str, Any], auth_header: str, db: Session):
        if not settings.bot_app_id or not settings.bot_app_password:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="BOT_APP_ID / BOT_APP_PASSWORD are not configured on the server",
            )

        activity = Activity().deserialize(body)

        async def turn_logic(turn_context: TurnContext) -> None:
            await self._turn_logic(activity, turn_context, db)

        try:
            invoke_response = await self._adapter.process_activity(activity, auth_header, turn_logic)
        except (PermissionError, jwt.PyJWTError) as exc:
            logger.warning("Teams bot token rejected: %s", exc)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

        if invoke_response:
            return JSONResponse(content=invoke_response.body, status_code=invoke_response.status)
        return {}


_bot_service: Optional[BotService] = None


def get_bot_service() -> BotService:
    global _bot_service
    if _bot_service is None:
        adapter = BotFrameworkAdapter(
            BotFrameworkAdapterSettings(
                settings.bot_app_id or "",
                settings.bot_app_password or "",
                channel_auth_tenant=settings.bot_app_tenant_id,
            )
        )
        _bot_service = BotService(adapter)
    return _bot_service
