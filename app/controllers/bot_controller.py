from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.bot_service import BotService, get_bot_service

router = APIRouter(prefix="/webhooks/teams", tags=["teams-bot"])


@router.post("")
async def receive_teams_activity(
    request: Request,
    service: BotService = Depends(get_bot_service),
    db: Session = Depends(get_db),
):
    body = await request.json()
    auth_header = request.headers.get("Authorization", "")
    return await service.receive_activity(body, auth_header, db)
