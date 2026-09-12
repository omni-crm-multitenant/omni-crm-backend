from uuid import uuid4

import pytest

from app.core.tenant_context import get_current_tenant_id, set_current_tenant_id
from app.db import session as session_module


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_session_failure_rolls_back_and_clears_tenant_context(monkeypatch) -> None:
    fake_session = FakeSession()
    monkeypatch.setattr(session_module, "SessionFactory", lambda: fake_session)
    set_current_tenant_id(uuid4())

    with pytest.raises(RuntimeError, match="failure"):
        async with session_module.session_scope():
            raise RuntimeError("failure")

    assert fake_session.rolled_back is True
    assert fake_session.committed is False
    assert fake_session.closed is True
    assert get_current_tenant_id() is None

