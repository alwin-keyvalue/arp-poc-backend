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
        self.cors_origins = [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        ]


settings = Settings()
