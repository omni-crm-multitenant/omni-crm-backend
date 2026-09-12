from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.crm import Contact, Conversation
from app.models.identity import ChannelAsset, Membership, Tenant, User
from app.services.authorization import AuthorizationDenied, ResourceScope, authorize_assigned_resource
from app.services.integration_context import WorkerEnvelope, revalidate_worker_envelope


def uid(value: int) -> UUID:
    return UUID(int=value)


@dataclass(frozen=True)
class TenantIsolationFixture:
    tenant_a_id: UUID
    tenant_b_id: UUID
    admin_a_user_id: UUID
    assigned_agent_user_id: UUID
    unassigned_agent_user_id: UUID
    agent_b_user_id: UUID
    admin_a_membership_id: UUID
    assigned_agent_membership_id: UUID
    unassigned_agent_membership_id: UUID
    agent_b_membership_id: UUID
    asset_a_id: UUID
    asset_b_id: UUID
    contact_a_id: UUID
    contact_b_id: UUID
    conversation_a_id: UUID
    conversation_b_id: UUID


async def seed_two_tenant_fixture(session: AsyncSession) -> TenantIsolationFixture:
    ids = TenantIsolationFixture(
        tenant_a_id=uid(101),
        tenant_b_id=uid(102),
        admin_a_user_id=uid(201),
        assigned_agent_user_id=uid(202),
        unassigned_agent_user_id=uid(203),
        agent_b_user_id=uid(204),
        admin_a_membership_id=uid(301),
        assigned_agent_membership_id=uid(302),
        unassigned_agent_membership_id=uid(303),
        agent_b_membership_id=uid(304),
        asset_a_id=uid(401),
        asset_b_id=uid(402),
        contact_a_id=uid(501),
        contact_b_id=uid(502),
        conversation_a_id=uid(601),
        conversation_b_id=uid(602),
    )
    session.add_all(
        [
            Tenant(id=ids.tenant_a_id, name="Tenant A", slug="isolation-a"),
            Tenant(id=ids.tenant_b_id, name="Tenant B", slug="isolation-b"),
            User(id=ids.admin_a_user_id, name="Admin A", email="isolation-admin-a@example.test", password_hash="x"),
            User(id=ids.assigned_agent_user_id, name="Assigned A", email="isolation-assigned-a@example.test", password_hash="x"),
            User(id=ids.unassigned_agent_user_id, name="Unassigned A", email="isolation-unassigned-a@example.test", password_hash="x"),
            User(id=ids.agent_b_user_id, name="Agent B", email="isolation-agent-b@example.test", password_hash="x"),
        ]
    )
    await session.flush()
    session.add_all(
        [
            Membership(id=ids.admin_a_membership_id, tenant_id=ids.tenant_a_id, user_id=ids.admin_a_user_id, role="administrador", status="active"),
            Membership(id=ids.assigned_agent_membership_id, tenant_id=ids.tenant_a_id, user_id=ids.assigned_agent_user_id, role="agente_comercial", status="active"),
            Membership(id=ids.unassigned_agent_membership_id, tenant_id=ids.tenant_a_id, user_id=ids.unassigned_agent_user_id, role="agente_comercial", status="active"),
            Membership(id=ids.agent_b_membership_id, tenant_id=ids.tenant_b_id, user_id=ids.agent_b_user_id, role="agente_comercial", status="active"),
            ChannelAsset(id=ids.asset_a_id, tenant_id=ids.tenant_a_id, channel="whatsapp", external_id="isolation-phone-a", meta_app_id="isolation-meta-app", credential_ref="ref-a", scopes=[]),
            ChannelAsset(id=ids.asset_b_id, tenant_id=ids.tenant_b_id, channel="whatsapp", external_id="isolation-phone-b", meta_app_id="isolation-meta-app", credential_ref="ref-b", scopes=[]),
            Contact(id=ids.contact_a_id, tenant_id=ids.tenant_a_id, name="Contact A", custom_fields={}, tags=[]),
            Contact(id=ids.contact_b_id, tenant_id=ids.tenant_b_id, name="Contact B", custom_fields={}, tags=[]),
        ]
    )
    await session.flush()
    session.add_all(
        [
            Conversation(id=ids.conversation_a_id, tenant_id=ids.tenant_a_id, contact_id=ids.contact_a_id, channel_asset_id=ids.asset_a_id, channel="whatsapp", assigned_user_id=ids.assigned_agent_user_id),
            Conversation(id=ids.conversation_b_id, tenant_id=ids.tenant_b_id, contact_id=ids.contact_b_id, channel_asset_id=ids.asset_b_id, channel="whatsapp", assigned_user_id=ids.agent_b_user_id),
        ]
    )
    await session.flush()
    return ids


def assert_http_cross_tenant_denied(response, *foreign_identifiers: UUID) -> None:
    assert response.status_code in {403, 404}
    body = response.text
    for identifier in foreign_identifiers:
        assert str(identifier) not in body


async def assert_worker_cross_tenant_denied(session: AsyncSession, envelope: WorkerEnvelope) -> None:
    assert not await revalidate_worker_envelope(session, envelope)


def assert_same_tenant_unassigned_denied(ids: TenantIsolationFixture) -> None:
    context = TenantContext(
        tenant_id=ids.tenant_a_id,
        membership_id=ids.unassigned_agent_membership_id,
        user_id=ids.unassigned_agent_user_id,
        role="agente_comercial",
    )
    resource = ResourceScope(
        tenant_id=ids.tenant_a_id,
        assignee_membership_id=ids.assigned_agent_membership_id,
    )
    try:
        authorize_assigned_resource(context, resource, action="write")
    except AuthorizationDenied as exc:
        assert exc.code == "RESOURCE_NOT_ASSIGNED"
    else:
        raise AssertionError("unassigned agent was unexpectedly authorized")
