"""Fail fast when the generated API contract has incomplete operations."""

from app.main import create_app


schema = create_app().openapi()
assert schema["openapi"].startswith("3.")
assert "BearerAuth" in schema["components"]["securitySchemes"]
for path, operations in schema["paths"].items():
    for method, operation in operations.items():
        if method not in {"get", "post", "put", "patch", "delete", "options", "head"}:
            continue
        assert operation.get("summary"), f"missing summary: {method} {path}"
        assert operation.get("description"), f"missing description: {method} {path}"
        assert operation.get("responses"), f"missing responses: {method} {path}"
print(f"OpenAPI valid: {len(schema['paths'])} paths")
