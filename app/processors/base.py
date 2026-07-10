from __future__ import annotations

from typing import Protocol

from app.schemas.parsed_email import GraphMessageMetadata, ParsedEmailInput


class EmailInputProcessor(Protocol):
    async def process(
        self,
        email: ParsedEmailInput,
        *,
        metadata: GraphMessageMetadata,
    ) -> None: ...
