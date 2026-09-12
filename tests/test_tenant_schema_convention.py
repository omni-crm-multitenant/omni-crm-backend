from app.db.base import tenant_identity_constraint, tenant_reference_constraint


def test_tenant_schema_convention_builds_composite_constraints() -> None:
    identity = tenant_identity_constraint(table_name="contacts")
    reference = tenant_reference_constraint("contact_id", "contacts")
    assert identity.name == "uq_contacts_tenant_identity"
    assert list(identity._pending_colargs) == ["tenant_id", "id"]
    assert list(reference.column_keys) == ["tenant_id", "contact_id"]
