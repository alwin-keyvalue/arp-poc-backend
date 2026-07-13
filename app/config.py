import os

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

        self.azure_tenant_id = os.getenv("AZURE_TENANT_ID", "")
        self.azure_client_id = os.getenv("AZURE_CLIENT_ID", "")
        self.azure_client_secret = os.getenv("AZURE_CLIENT_SECRET", "")
        self.webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "")
        self.webhook_client_state = os.getenv("WEBHOOK_CLIENT_STATE", "")

    @property
    def microsoft_graph_webhook_url(self) -> str:
        base = self.webhook_base_url.rstrip("/")
        return f"{base}/api/microsoft-graph/webhooks/outlook"


settings = Settings()
