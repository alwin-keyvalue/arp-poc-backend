import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
import httpx

from app.dependencies import get_analyzer, get_http_client, get_request_validation_token
from app.services.email_analysis import Analyzer
from app.schemas.subscription import WebhookNotificationPayload
from app.services.webhook_processor_service import WebhookProcessorService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/microsoft-graph/webhooks/outlook",
    tags=["microsoft-graph"],
)


def get_webhook_processor_service(
    http_client: httpx.AsyncClient = Depends(get_http_client),
    analyzer: Analyzer = Depends(get_analyzer),
) -> WebhookProcessorService:
    return WebhookProcessorService(http_client, analyzer)


@router.get("")
async def validate_webhook_get(
    request: Request,
    validation_token: str | None = None,
):
    token = validation_token or get_request_validation_token(request)
    return _respond_to_validation(token)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def validate_or_receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    service: WebhookProcessorService = Depends(get_webhook_processor_service),
):
    logger.info("Received Outlook webhook POST from %s", request.client.host if request.client else "unknown")

    try:
        body = await request.json()
    except Exception:
        logger.warning("Failed to parse webhook request body as JSON; treating as empty")
        body = {}
    if not isinstance(body, dict):
        logger.warning("Webhook request body was not a JSON object (got %s); treating as empty", type(body).__name__)
        body = {}

    # The raw body includes clientState (a shared secret) and, for rich notifications, only
    # encrypted content — but logging it wholesale is still an anti-pattern (it's whatever
    # Microsoft sends, not schema-guaranteed). Log shape only: top-level keys and item count.
    notification_items = body.get("value")
    logger.info(
        "Webhook payload received: keys=%s item_count=%s",
        sorted(body.keys()),
        len(notification_items) if isinstance(notification_items, list) else "n/a",
    )

    validation_token = get_request_validation_token(request, body)
    if validation_token:
        logger.info("Responding to Graph subscription validation handshake")
        return _respond_to_validation(validation_token)

    try:
        payload = WebhookNotificationPayload.model_validate(body)
    except Exception:
        logger.exception("Failed to parse webhook notification payload (keys=%s)", sorted(body.keys()))
        raise

    if payload.value:
        logger.info("Queuing %d notification(s) for background processing", len(payload.value))
        background_tasks.add_task(service.process_notification, payload)
    else:
        logger.info("Webhook POST contained no notifications; nothing to process")

    return Response(status_code=status.HTTP_202_ACCEPTED)


def _respond_to_validation(validation_token: str | None) -> Response:
    if not validation_token:
        return Response(
            content="Missing validationToken",
            media_type="text/plain",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return Response(content=validation_token, media_type="text/plain", status_code=status.HTTP_200_OK)
