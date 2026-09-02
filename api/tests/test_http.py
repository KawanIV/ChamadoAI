from fastapi.testclient import TestClient
from app.main import app

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

def test_admin_routes_require_authentication():
    assert client.get("/api/admin/ai/models").status_code==401
    assert client.get("/api/admin/users").status_code==401

def test_public_payload_rejects_secret_patterns():
    response=client.post("/api/public/zoho-suporte/tickets",json={"requester_name":"João","department":"Compras","description":"Minha senha: segredo123 e não consigo entrar","product":"Zoho CRM","public_context":"invalid"})
    assert response.status_code==422
