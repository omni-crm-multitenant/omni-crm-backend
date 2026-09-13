import ast
from pathlib import Path


CONTACTS_ROUTER = Path(__file__).parents[1] / "app/api/v1/contacts.py"


def _endpoint_function(name: str) -> ast.AsyncFunctionDef:
    tree = ast.parse(CONTACTS_ROUTER.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    )
    return function


def _called_names(function: ast.AsyncFunctionDef) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def test_contact_http_endpoints_delegate_domain_work_to_application_cases():
    forbidden_calls = {"select", "paginate", "validate_custom_field_payload", "normalize_phone", "normalize_email"}
    for endpoint in ("create_contact", "list_contacts", "update_contact", "grant_consent", "revoke_consent", "export_contact_data", "delete_contact"):
        assert not (_called_names(_endpoint_function(endpoint)) & forbidden_calls)


def test_contact_http_endpoints_do_not_manage_transactions_or_persistence():
    for endpoint in ("create_contact", "list_contacts", "update_contact", "grant_consent", "revoke_consent", "export_contact_data", "delete_contact"):
        function = _endpoint_function(endpoint)
        assert not any(
            isinstance(node, ast.Attribute)
            and node.attr in {"add", "flush", "commit", "execute", "scalar"}
            for node in ast.walk(function)
        )


def test_repositories_do_not_import_application_services():
    repositories = Path(__file__).parents[1] / "app/repositories"
    for path in repositories.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "from app.services" not in source
        assert "import app.services" not in source
