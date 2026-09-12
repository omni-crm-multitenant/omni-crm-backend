from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from app.core.pagination import decode_cursor, encode_cursor, paginate
from app.db.base import Base
from app.models.crm import Contact, ContactIdentity
from app.models.identity import ChannelAsset, Tenant
from app.services.message_authors import AuthorOrigin, MessageAuthor


class PaginationItem(Base):
    __tablename__ = "pagination_items"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False)
    value: Mapped[str] = mapped_column(String(40), nullable=False)


@pytest.fixture
async def data_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_contact_identity_is_scoped_and_external_sender_can_repeat(data_factory) -> None:
    async with data_factory.begin() as session:
        tenant = Tenant(name="Identity", slug="identity-scope")
        session.add(tenant)
        await session.flush()
        contact = Contact(tenant_id=tenant.id, name="Contact", tags=[], custom_fields={})
        asset_a = ChannelAsset(tenant_id=tenant.id, channel="whatsapp", external_id="a", meta_app_id="app", credential_ref="a", scopes=[])
        asset_b = ChannelAsset(tenant_id=tenant.id, channel="whatsapp", external_id="b", meta_app_id="app", credential_ref="b", scopes=[])
        session.add_all([contact, asset_a, asset_b])
        await session.flush()
        session.add_all([
            ContactIdentity(tenant_id=tenant.id, contact_id=contact.id, channel_asset_id=asset_a.id, external_user_id="same", identity_metadata={}),
            ContactIdentity(tenant_id=tenant.id, contact_id=contact.id, channel_asset_id=asset_b.id, external_user_id="same", identity_metadata={}),
        ])
    async with data_factory() as session:
        assert len((await session.scalars(select(ContactIdentity))).all()) == 2


@pytest.mark.asyncio
async def test_cursor_pagination_uses_occurred_at_and_id_pair(data_factory) -> None:
    first = datetime.now(UTC)
    ids = [uuid4() for _ in range(3)]
    async with data_factory.begin() as session:
        session.add_all([
            PaginationItem(id=ids[0], occurred_at=first, value="one"),
            PaginationItem(id=ids[1], occurred_at=first + timedelta(seconds=1), value="two"),
            PaginationItem(id=ids[2], occurred_at=first + timedelta(seconds=2), value="three"),
        ])
    async with data_factory() as session:
        page = await paginate(session, select(PaginationItem), None, 2, (PaginationItem.occurred_at, PaginationItem.id))
        assert [item.value for item in page.items] == ["one", "two"]
        assert page.next_cursor is not None
        decoded_at, decoded_id = decode_cursor(page.next_cursor)
        assert decoded_id == ids[1]
        next_page = await paginate(session, select(PaginationItem), page.next_cursor, 2, (PaginationItem.occurred_at, PaginationItem.id))
        assert [item.value for item in next_page.items] == ["three"]
        assert encode_cursor(decoded_at, decoded_id) == page.next_cursor


def test_message_author_contract_rejects_arbitrary_author_and_requires_source() -> None:
    user_id = uuid4()
    run_id = uuid4()
    assert MessageAuthor.agent(user_id).storage_fields() == {"author_type": "user", "author_user_id": user_id}
    assert MessageAuthor.ai(run_id).storage_fields()["author_type"] == "ai"
    with pytest.raises(ValueError, match="agent author requires user_id"):
        MessageAuthor(origin=AuthorOrigin.AGENT)
    with pytest.raises(ValueError, match="only agent author"):
        MessageAuthor(origin=AuthorOrigin.CONTACT, user_id=user_id, source_id=uuid4())
