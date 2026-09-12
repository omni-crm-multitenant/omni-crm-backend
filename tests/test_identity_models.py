from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.identity import Membership, Tenant, User


def test_identity_models_compile_for_postgresql() -> None:
    dialect = postgresql.dialect()
    for model in (Tenant, User, Membership):
        sql = str(CreateTable(model.__table__).compile(dialect=dialect))
        assert "CREATE TABLE" in sql


def test_required_identity_columns_exist() -> None:
    assert set(Tenant.__table__.columns.keys()) >= {
        "id", "name", "slug", "timezone", "locale", "status", "plan_code", "created_at", "updated_at"
    }
    assert set(User.__table__.columns.keys()) >= {
        "id", "name", "email", "password_hash", "mfa_enabled", "status", "last_login_at", "created_at", "updated_at"
    }
    assert set(Membership.__table__.columns.keys()) >= {
        "id", "tenant_id", "user_id", "role", "status", "invited_at", "accepted_at"
    }

