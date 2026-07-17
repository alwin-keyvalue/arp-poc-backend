import logging
from datetime import date, timedelta
from html import escape
from typing import List

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.database import SessionLocal
from app.integrations.microsoft_graph.client import GraphClient, GraphClientError
from app.models.task import Task
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class ReportService:
    def __init__(
        self,
        task_repository: TaskRepository,
        user_repository: UserRepository,
        graph_client: GraphClient,
    ):
        self.task_repository = task_repository
        self.user_repository = user_repository
        self.graph_client = graph_client

    def _assignee_label(self, task: Task) -> str:
        if not task.assignees:
            return "Unassigned"
        return ", ".join(user.display_name or user.email for user in task.assignees)

    def _build_report_html(self, tasks: List[Task], from_date: date, to_date: date) -> str:
        rows = "".join(
            "<tr>"
            f"<td>{escape(task.title)}</td>"
            f"<td>{escape(task.status)}</td>"
            f"<td>{escape(task.priority)}</td>"
            f"<td>{task.due_date.isoformat() if task.due_date else '-'}</td>"
            f"<td>{escape(self._assignee_label(task))}</td>"
            "</tr>"
            for task in tasks
        )
        if not rows:
            rows = "<tr><td colspan='5'>No tasks created in this period.</td></tr>"

        return f"""
        <html>
          <body style="font-family: sans-serif;">
            <h2>Task Status Report</h2>
            {f"<p>Report for {from_date.isoformat()}</p>" if from_date == to_date else f"<p>Report for {from_date.isoformat()} to {to_date.isoformat()}</p>"}
            <table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse;">
              <thead>
                <tr>
                  <th>Title</th><th>Status</th><th>Priority</th><th>Due date</th><th>Assignee</th>
                </tr>
              </thead>
              <tbody>
                {rows}
              </tbody>
            </table>
          </body>
        </html>
        """

    async def send_task_status_report(
        self,
        from_date: date,
        to_date: date,
        recipients: List[str],
    ) -> int:
        if not settings.reports_sender_mailbox:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="REPORTS_SENDER_MAILBOX is not configured",
            )

        tasks = self.task_repository.get_created_between(from_date, to_date)
        html_body = self._build_report_html(tasks, from_date, to_date)

        try:
            await self.graph_client.send_mail(
                from_user_id=settings.reports_sender_mailbox,
                to_recipients=recipients,
                subject=f"Task Status Report ({from_date.isoformat()} to {to_date.isoformat()})",
                html_body=html_body,
            )
        except GraphClientError as exc:
            logger.exception("Failed to send task status report email via Graph")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Failed to send report email via Microsoft Graph: "
                    f"{exc}. Check that REPORTS_SENDER_MAILBOX's app registration has "
                    "Mail.Send (Application) permission granted with admin consent."
                ),
            ) from exc
        return len(tasks)


async def run_task_report(
    http_client: httpx.AsyncClient,
    from_date: date,
    to_date: date,
    recipients: List[str],
) -> int | None:
    """Background job: opens its own DB session, logs outcome, safe after HTTP 202."""
    db = SessionLocal()
    try:
        service = ReportService(TaskRepository(db), UserRepository(db), GraphClient(http_client))
        task_count = await service.send_task_status_report(from_date, to_date, recipients)
        logger.info(
            "Task report sent: from=%s to=%s recipients=%d task_count=%d",
            from_date.isoformat(),
            to_date.isoformat(),
            len(recipients),
            task_count,
        )
        return task_count
    except Exception:
        logger.exception("Task report job failed unexpectedly")
        return None
    finally:
        db.close()


def default_report_date_range() -> tuple[date, date]:
    """Yesterday's calendar day — stable even if the cron fires late."""
    yesterday = date.today() - timedelta(days=1)
    return yesterday, yesterday
