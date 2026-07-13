from __future__ import annotations

from typing import AsyncIterator

import httpx
from fastapi import Request

_http_client: httpx.AsyncClient | None = None


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


def get_request_validation_token(request: Request, body: dict | None = None) -> str | None:
    query_token = request.query_params.get("validationToken")
    if query_token:
        return query_token
    if body:
        token = body.get("validationToken")
        if isinstance(token, str) and token:
            return token
    return None
