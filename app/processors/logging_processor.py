from __future__ import annotations

import json
import logging

from app.processors.base import EmailInputProcessor
from app.schemas.parsed_email import GraphMessageMetadata, ParsedEmailInput

logger = logging.getLogger(__name__)


class LoggingEmailProcessor:
    async def process(
        self,
        email: ParsedEmailInput,
        *,
        metadata: GraphMessageMetadata,
    ) -> None:
        payload = {
            "parsed_email": email.model_dump(),
            "metadata": metadata.model_dump(),
        }
        formatted = json.dumps(payload, indent=2, default=str)
        logger.info("Parsed email ready for LLM module:\n%s", formatted)
