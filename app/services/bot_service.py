import logging
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
import jwt
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, CardFactory, MessageFactory, TurnContext
from botbuilder.schema import Activity, ConversationReference
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.graph_client import get_user_email
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.repositories.task_repository import TaskRepository
from app.repositories.task_status_history_repository import TaskStatusHistoryRepository
from app.repositories.user_repository import UserRepository
from app.schemas.task import TaskUpdate
from app.services.subscription_service import build_subscription_service

logger = logging.getLogger("app.teams_bot")

GREETING_TEXT = (
    "👋 Hi! I'm your Task Bot. Forward me an email or flag a message here and "
    "I'll help turn it into a task."
)

TASK_ACTION_VERB = "task_action"


def _build_teams_entity_deep_link(app_id: str, entity_id: str, task_id: Any) -> str:
    query = urlencode({"taskId": str(task_id)})
    return f"https://teams.microsoft.com/l/entity/{app_id}/{entity_id}?{query}"


def _build_task_assigned_card(task: Task) -> Dict[str, Any]:
    logger.info("Building Teams task-assigned card for task: %s", task.id)
    body = [
        {
            "type": "TextBlock",
            "text": "📌 New task assigned",
            "weight": "Bolder",
            "size": "Medium",
        },
        {
            "type": "TextBlock",
            "text": task.title,
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        },
    ]
    if task.summary:
        body.append({"type": "TextBlock", "text": task.summary, "wrap": True, "isSubtle": True})

    facts = [{"title": "Priority", "value": task.priority}, {"title": "Status", "value": task.status}]
    if task.due_date:
        facts.append({"title": "Due date", "value": task.due_date.isoformat()})
    body.append({"type": "FactSet", "facts": facts})

    task_url = _build_teams_entity_deep_link(settings.teams_app_id, settings.teams_entity_id, task.id)
    actions: list = [
        {
            "type": "Action.Submit",
            "title": "✅ Mark as done",
            "data": {"verb": TASK_ACTION_VERB, "taskAction": "complete", "taskId": str(task.id)},
        },
        {"type": "Action.OpenUrl", "title": "🔗 View task", "url": task_url}
    ]

    return {
        "type": "AdaptiveCard",
        "$schema": "https://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
        "actions": actions,
    }


def _build_task_action_result_card(task: Task, confirmation: str) -> Dict[str, Any]:
    return {
        "type": "AdaptiveCard",
        "$schema": "https://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "text": confirmation, "weight": "Bolder", "wrap": True},
            {"type": "TextBlock", "text": task.title, "wrap": True, "isSubtle": True},
        ],
    }


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

    async def _subscribe_for_inbox_messages(self, email: str, db: Session) -> None:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            await build_subscription_service(db, http_client).subscribe_user(email)
        logger.info("Subscribed %s for inbox message notifications", email)

    async def _handle_task_card_action(self, activity: Activity, turn_context: TurnContext, db: Session) -> None:
        value = activity.value
        task_action = value.get("taskAction")
        try:
            task_id = uuid.UUID(str(value.get("taskId")))
        except (TypeError, ValueError):
            logger.warning("Ignoring task card action with invalid taskId: %s", value.get("taskId"))
            return

        repository = TaskRepository(db)
        task = repository.get_by_id(task_id)
        if task is None:
            await turn_context.send_activity("⚠️ That task no longer exists.")
            return

        previous_status = task.status
        if task_action == "complete":
            task = repository.update(task, TaskUpdate(status=TaskStatus.DONE))
            confirmation = "✅ Marked as done"
        elif task_action == "drop":
            task = repository.update(task, TaskUpdate(status=TaskStatus.DROPPED))
            confirmation = "🗑️ Task dropped"
        else:
            logger.warning("Unknown task card action: %s", task_action)
            return

        if task.status != previous_status:
            TaskStatusHistoryRepository(db).record(
                task=task,
                from_status=previous_status,
                to_status=task.status,
                source="teams_bot",
                changed_by_oid=activity.from_property.aad_object_id if activity.from_property else None,
                changed_by_name=activity.from_property.name if activity.from_property else None,
            )

        card = CardFactory.adaptive_card(_build_task_action_result_card(task, confirmation))
        await turn_context.send_activity(MessageFactory.attachment(card))

    async def _handle_bot_installed(self, activity: Activity, turn_context: TurnContext, db: Session) -> None:
        aad_object_id = activity.from_property.aad_object_id if activity.from_property else None
        email = await get_user_email(aad_object_id)
        logger.info("Teams user email: %s (aadObjectId=%s)", email, aad_object_id)

        if email:
            try:
                self._remember_teams_user(activity, email, db)
            except Exception:
                logger.exception("Failed to persist Teams conversation reference for %s", email)
            else:
                if email.lower() in settings.subscription_excluded_emails:
                    logger.info("Skipping inbox subscription for %s (in SUBSCRIPTION_EXCLUDED_EMAILS)", email)
                else:
                    try:
                        await self._subscribe_for_inbox_messages(email, db)
                    except Exception:
                        logger.exception("Failed to subscribe %s for inbox message notifications", email)

        await turn_context.send_activity(GREETING_TEXT)

    async def _turn_logic(self, activity: Activity, turn_context: TurnContext, db: Session) -> None:
        logger.info("Teams activity received: %s", activity.serialize())

        if activity.type == "message" and isinstance(activity.value, dict) and activity.value.get("verb") == TASK_ACTION_VERB:
            await self._handle_task_card_action(activity, turn_context, db)
            return

        if activity.type == "conversationUpdate" and self._bot_was_added(activity):
            await self._handle_bot_installed(activity, turn_context, db)

    async def notify_task_assigned(self, user: User, task: Task) -> None:
        if not user.teams_conversation_reference:
            logger.info("Skipping Teams notification for %s: no stored conversation reference", user.email)
            return
        if not settings.azure_client_id or not settings.bot_app_password:
            logger.info("Skipping Teams notification: bot is not configured")
            return

        reference = ConversationReference().deserialize(user.teams_conversation_reference)
        card = CardFactory.adaptive_card(_build_task_assigned_card(task))
        message = MessageFactory.attachment(card)

        async def callback(turn_context: TurnContext) -> None:
            await turn_context.send_activity(message)

        try:
            await self._adapter.continue_conversation(reference, callback, settings.azure_client_id)
        except Exception:
            logger.exception("Failed to send Teams task-assigned notification to %s", user.email)

    async def receive_activity(self, body: Dict[str, Any], auth_header: str, db: Session):
        if not settings.azure_client_id or not settings.bot_app_password:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AZURE_CLIENT_ID / BOT_APP_PASSWORD are not configured on the server",
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
                channel_auth_tenant=settings.azure_tenant_id,
            )
        )
        _bot_service = BotService(adapter)
    return _bot_service
