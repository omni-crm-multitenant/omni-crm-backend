from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.route_policy import PUBLIC_ENDPOINTS, is_public_endpoint
from app.core.tenant_context import TenantContext
from app.db.base import Base
from app.main import create_app
from app.models.identity import Membership, Tenant, User
from app.services.authorization import (
    AuthorizationDenied,
    ResourceScope,
    authorize_assigned_resource,
    validate_assignee_membership,
)


def context(role, *, tenant_id=None, membership_id=None):
    return TenantContext(
        tenant_id=tenant_id or uuid4(),
        membership_id=membership_id or uuid4(),
        user_id=uuid4(),
        role=role,
    )


def test_agent_only_operates_assigned_resources() -> None:
    agent = context("agente_comercial")
    assigned = ResourceScope(agent.tenant_id, agent.membership_id)
    unassigned = ResourceScope(agent.tenant_id, uuid4())
    authorize_assigned_resource(agent, assigned, action="takeover")
    with pytest.raises(AuthorizationDenied, match="RESOURCE_NOT_ASSIGNED"):
        authorize_assigned_resource(agent, unassigned, action="write")
    with pytest.raises(AuthorizationDenied, match="REASSIGNMENT_FORBIDDEN"):
        authorize_assigned_resource(agent, assigned, action="reassign")


def test_supervisor_can_reassign_inside_tenant_but_never_cross_tenant() -> None:
    supervisor = context("supervisor")
    authorize_assigned_resource(
        supervisor,
        ResourceScope(supervisor.tenant_id, uuid4()),
        action="reassign",
    )
    with pytest.raises(AuthorizationDenied, match="CROSS_TENANT_ACCESS_DENIED"):
        authorize_assigned_resource(
            supervisor,
            ResourceScope(uuid4(), supervisor.membership_id),
            action="read",
        )


@pytest.mark.asyncio
async def test_assignee_must_be_active_in_current_tenant() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        first = Tenant(name="One", slug="auth-one")
        second = Tenant(name="Two", slug="auth-two")
        user = User(name="Agent", email="auth-agent@example.com", password_hash="hash")
        session.add_all([first, second, user])
        await session.flush()
        own = Membership(tenant_id=first.id, user_id=user.id, role="agente_comercial", status="active")
        foreign = Membership(tenant_id=second.id, user_id=user.id, role="agente_comercial", status="active")
        session.add_all([own, foreign])
        await session.flush()
        ids = first.id, own.id, foreign.id
    current = context("supervisor", tenant_id=ids[0])
    async with factory() as session:
        assert (await validate_assignee_membership(session, current, ids[1])).id == ids[1]
        with pytest.raises(AuthorizationDenied, match="INVALID_ASSIGNEE"):
            await validate_assignee_membership(session, current, ids[2])
    await engine.dispose()


def test_every_unsecured_openapi_operation_is_explicitly_public() -> None:
    schema = create_app().openapi()
    operations = {
        (method.upper(), path): operation
        for path, path_item in schema["paths"].items()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert PUBLIC_ENDPOINTS <= operations.keys()
    unsecured = {key for key, operation in operations.items() if not operation.get("security")}
    assert unsecured == PUBLIC_ENDPOINTS
    assert is_public_endpoint("post", "/api/v1/auth/login")
    assert not is_public_endpoint("POST", "/api/v1/tenants")
