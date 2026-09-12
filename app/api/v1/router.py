from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.tenants import router as tenants_router
from app.api.v1.invitations import router as invitations_router
from app.api.v1.settings import router as settings_router
from app.api.v1.custom_fields import router as custom_fields_router
from app.api.v1.channel_assets import router as channel_assets_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.contacts import router as contacts_router
from app.api.v1.campaigns import router as campaigns_router
from app.api.v1.opportunities import router as opportunities_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.ai_profiles import router as ai_profiles_router
from app.api.v1.attributions import router as attributions_router
from app.api.v1.messages import router as messages_router
from app.api.v1.transfers import router as transfers_router
from app.api.v1.automation_rules import router as automation_rules_router
from app.api.v1.audit_events import router as audit_events_router
from app.api.v1.pipelines import router as pipelines_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.kpi import router as kpi_router
from app.api.v1.automation_executions import router as automation_executions_router
from app.api.v1.integration_events import router as integration_events_router
from app.api.v1.billing import router as billing_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(tenants_router)
router.include_router(invitations_router)
router.include_router(settings_router)
router.include_router(custom_fields_router)
router.include_router(channel_assets_router)
router.include_router(webhooks_router)
router.include_router(conversations_router)
router.include_router(contacts_router)
router.include_router(campaigns_router)
router.include_router(opportunities_router)
router.include_router(tasks_router)
router.include_router(ai_profiles_router)
router.include_router(attributions_router)
router.include_router(messages_router)
router.include_router(transfers_router)
router.include_router(automation_rules_router)
router.include_router(audit_events_router)
router.include_router(pipelines_router)
router.include_router(jobs_router)
router.include_router(kpi_router)
router.include_router(automation_executions_router)
router.include_router(integration_events_router)
router.include_router(billing_router)


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


api_router = router
