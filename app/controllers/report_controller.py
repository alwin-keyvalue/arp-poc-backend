import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.teams_auth import get_current_teams_user
from app.database import get_db
from app.dependencies import get_http_client
from app.integrations.microsoft_graph.client import GraphClient
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.report import TaskReportRequest, TaskReportResponse
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/reports", tags=["reports"], dependencies=[Depends(get_current_teams_user)])


def get_report_service(
    db: Session = Depends(get_db),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> ReportService:
    return ReportService(TaskRepository(db), UserRepository(db), GraphClient(http_client))


@router.post("/tasks/email", response_model=TaskReportResponse)
async def send_task_report(
    body: TaskReportRequest,
    service: ReportService = Depends(get_report_service),
):
    task_count = await service.send_task_status_report(
        body.from_date, body.to_date, [str(recipient) for recipient in body.recipients]
    )
    return TaskReportResponse(
        from_date=body.from_date,
        to_date=body.to_date,
        recipients=body.recipients,
        task_count=task_count,
    )
