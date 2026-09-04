from fastapi.testclient import TestClient
from app.main import app
from app.security import Principal, create_access_token

client=TestClient(app)
def test_health_has_security_headers():
    response=client.get("/health")
    assert response.status_code==200
    assert response.headers["x-frame-options"]=="DENY"
    assert response.headers["x-content-type-options"]=="nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]

def test_ticket_listing_requires_authentication():
    response=client.get("/api/tickets")
    assert response.status_code==401

def test_admin_is_forbidden_from_ticket_listing_before_database_access():
    token=create_access_token(Principal(user_id="00000000-0000-0000-0000-000000000001",tenant_id="00000000-0000-0000-0000-000000000002",role="platform_admin"))
    response=client.get("/api/tickets",headers={"Authorization":f"Bearer {token}"})
    assert response.status_code==403

def test_admin_routes_require_authentication():
    assert client.get("/api/admin/ai/models").status_code==401
    assert client.get("/api/admin/ai/catalog").status_code==401
    assert client.get("/api/admin/ai/runtime").status_code==401
    assert client.get("/api/admin/ai/connection").status_code==401
    assert client.get("/api/admin/ai/skills").status_code==401
    assert client.post("/api/admin/ai/skills/import",json={"source_url":"https://example.com/SKILL.md","scope":"all"}).status_code==401
    assert client.get("/api/platform/companies").status_code==401
    assert client.get("/api/platform/audit").status_code==401
    assert client.get("/api/company/audit").status_code==401
    assert client.get("/api/company/users").status_code==401
    assert client.get("/api/company/areas").status_code==401
    assert client.get("/api/company/knowledge/documents").status_code==401
    assert client.post("/api/company/knowledge/documents").status_code==401

def test_platform_and_company_roles_are_separated_before_database_access():
    platform=create_access_token(Principal(user_id="00000000-0000-0000-0000-000000000001",tenant_id="00000000-0000-0000-0000-000000000002",role="platform_admin"))
    company=create_access_token(Principal(user_id="00000000-0000-0000-0000-000000000003",tenant_id="00000000-0000-0000-0000-000000000004",role="company_admin"))
    assert client.get("/api/company/users",headers={"Authorization":f"Bearer {platform}"}).status_code==403
    assert client.get("/api/company/audit",headers={"Authorization":f"Bearer {platform}"}).status_code==403
    assert client.get("/api/admin/ai/runtime",headers={"Authorization":f"Bearer {company}"}).status_code==403
    assert client.get("/api/platform/audit",headers={"Authorization":f"Bearer {company}"}).status_code==403

def test_public_payload_rejects_secret_patterns():
    response=client.post("/api/public/zoho-suporte/tickets",json={"requester_name":"João","department":"Compras","description":"Minha senha: segredo123 e não consigo entrar","product":"Zoho CRM","public_context":"invalid"})
    assert response.status_code==422
