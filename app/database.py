from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


if settings.db_schema and not settings.database_url.startswith("sqlite"):
    # Set via a regular SQL command rather than the "options=-c search_path=..." startup
    # parameter, since poolers like Neon's PgBouncer endpoint reject startup parameters.
    @event.listens_for(engine, "connect")
    def _set_search_path(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f"SET search_path TO {quote_ident(settings.db_schema)}")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
