from fastapi import FastAPI

from app.config import settings
from app.controllers.task_controller import router as task_router

app = FastAPI(title=settings.app_name)

app.include_router(task_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
