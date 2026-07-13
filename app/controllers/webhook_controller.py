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
    logger.info("GET webhook received with validation token present=%s", bool(token))
    return _respond_to_validation(token)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def validate_or_receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    service: WebhookProcessorService = Depends(get_webhook_processor_service),
):
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    logger.info("POST webhook received")

    validation_token = get_request_validation_token(request, body)
    if validation_token:
        logger.info("Validation token request received")
        return _respond_to_validation(validation_token)

    payload = WebhookNotificationPayload.model_validate(body)
    if payload.value:
        background_tasks.add_task(service.process_notification, payload)

    return Response(status_code=status.HTTP_202_ACCEPTED)


def _respond_to_validation(validation_token: str | None) -> Response:
    if not validation_token:
        return Response(
            content="Missing validationToken",
            media_type="text/plain",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return Response(content=validation_token, media_type="text/plain", status_code=status.HTTP_200_OK)
