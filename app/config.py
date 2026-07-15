import os
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy.engine import URL

load_dotenv()


class Settings:
    def __init__(self):
        self.db_host = os.getenv("DB_HOST")
        self.db_port = os.getenv("DB_PORT", "5432")
        self.db_name = os.getenv("DB_NAME")
        self.db_user = os.getenv("DB_USER")
        self.db_password = os.getenv("DB_PASSWORD")
        self.db_sslmode = os.getenv("DB_SSLMODE", "require")
        self.db_schema = os.getenv("DB_SCHEMA")

        if self.db_host:
            self.database_url = URL.create(
                drivername="postgresql+psycopg2",
                username=self.db_user,
                password=self.db_password,
                host=self.db_host,
                port=int(self.db_port),
                database=self.db_name,
                query={"sslmode": self.db_sslmode},
            ).render_as_string(hide_password=False)
        else:
            self.database_url = os.getenv("DATABASE_URL", "sqlite:///./app.db")

        self.app_name = os.getenv("APP_NAME", "Task Management API")
        self.cors_origins = [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        ]
        self.bot_app_id = os.getenv("AZURE_CLIENT_ID")
        self.bot_app_password = os.getenv("BOT_APP_PASSWORD")
        self.bot_app_tenant_id = os.getenv("AZURE_TENANT_ID")

        self.llm_provider = os.getenv("LLM_PROVIDER", "gemini")
        self.model = os.getenv("MODEL", "gemini-2.5-flash-lite")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.litellm_proxy = os.getenv("LITELLM_PROXY")
        self.llm_timeout = int(os.getenv("TIMEOUT", "60"))
        self.llm_temperature = float(os.getenv("TEMPERATURE", "0.0"))
        # Comma-separated. When non-empty, LLM analysis runs only if a listed
        # address appears on the message (from/to/cc/bcc or mailbox owner).
        self.llm_email_whitelist = {
            email.strip().lower()
            for email in os.getenv("LLM_EMAIL_WHITELIST", "").split(",")
            if email.strip()
        }

        self.azure_tenant_id = os.getenv("AZURE_TENANT_ID", "")
        self.azure_client_id = os.getenv("AZURE_CLIENT_ID", "")
        self.azure_client_secret = os.getenv("AZURE_CLIENT_SECRET", "")
        self.webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "")
        self.webhook_client_state = os.getenv("WEBHOOK_CLIENT_STATE", "")
        # basic: notification id only, then Graph GET message
        # rich: encrypted resource data in notification (Outlook cannot include body)
        self.webhook_notification_mode = os.getenv(
            "WEBHOOK_NOTIFICATION_MODE", "basic"
        ).strip().lower()
        self.graph_notification_certificate_id = os.getenv(
            "GRAPH_NOTIFICATION_CERTIFICATE_ID", ""
        ).strip()
        self.graph_notification_certificate = os.getenv(
            "GRAPH_NOTIFICATION_CERTIFICATE", ""
        ).strip()
        self.graph_notification_private_key = os.getenv(
            "GRAPH_NOTIFICATION_PRIVATE_KEY", ""
        ).strip()
        # When rich payload has no Body (Outlook forbids it), use bodyPreview instead
        # of calling Graph. Set false to always Graph-GET the full message in rich mode.
        self.webhook_rich_use_body_preview = os.getenv(
            "WEBHOOK_RICH_USE_BODY_PREVIEW", "true"
        ).strip().lower() in {"1", "true", "yes", "on"}

        self.web_app_url = os.getenv("WEB_APP_URL", "")
        self.teams_app_id = os.getenv("TEAMS_APP_ID", "")

    @property
    def webhook_include_resource_data(self) -> bool:
        return self.webhook_notification_mode == "rich"

    @property
    def microsoft_graph_webhook_url(self) -> str:
        base = self.webhook_base_url.rstrip("/")
        return f"{base}/api/microsoft-graph/webhooks/outlook"

    def task_web_url(self, task_id) -> Optional[str]:
        # Prefer a Teams deep link (opens inside the installed custom app) over a plain
        # browser URL. Uses Teams' "/l/app/<appId>" share-link format; unverified whether
        # Teams forwards the taskId query param through to the app's page — test after deploy.
        if self.teams_app_id:
            return f"https://teams.cloud.microsoft/l/app/{self.teams_app_id}?taskId={task_id}"
        if self.web_app_url:
            return f"{self.web_app_url.rstrip('/')}/?taskId={task_id}"
        return None


settings = Settings()
