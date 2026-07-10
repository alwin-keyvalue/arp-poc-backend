from fastapi import APIRouter

from app.integrations.microsoft_graph.controllers.subscription_controller import (
    router as subscription_router,
)
from app.integrations.microsoft_graph.controllers.webhook_controller import (
    router as webhook_router,
)

router = APIRouter()
router.include_router(subscription_router)
router.include_router(webhook_router)
