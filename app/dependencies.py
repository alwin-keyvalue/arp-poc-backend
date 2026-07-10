from __future__ import annotations

from collections import OrderedDict
from typing import AsyncIterator

import httpx
from fastapi import Request

from app.processors.logging_processor import LoggingEmailProcessor
from app.services.email_analysis import Analyzer, create_analyzer

_http_client: httpx.AsyncClient | None = None
_email_processor = LoggingEmailProcessor()
_analyzer: Analyzer | None = None
_seen_notifications: OrderedDict[tuple[str, str], None] = OrderedDict()
_MAX_SEEN_NOTIFICATIONS = 1000


async def get_http_client() -> AsyncIterator[httpx.AsyncClient]:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    yield _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


def get_email_processor() -> LoggingEmailProcessor:
    return _email_processor


def get_analyzer() -> Analyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = create_analyzer()
    return _analyzer


def is_duplicate_notification(subscription_id: str, message_id: str) -> bool:
    key = (subscription_id, message_id)
    if key in _seen_notifications:
        return True
    _seen_notifications[key] = None
    while len(_seen_notifications) > _MAX_SEEN_NOTIFICATIONS:
        _seen_notifications.popitem(last=False)
    return False


def get_request_validation_token(request: Request, body: dict | None = None) -> str | None:
    query_token = request.query_params.get("validationToken")
    if query_token:
        return query_token
    if body:
        token = body.get("validationToken")
        if isinstance(token, str) and token:
            return token
    return None
