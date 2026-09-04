from pathlib import Path
import uuid

from app.main import serialize_runtime
from app.models import AIConfig, AuditLog, TicketAttachment, User


def test_runtime_profiles_keep_support_and_intake_independent():
    config=AIConfig(tenant_id=uuid.uuid4(),provider="ollama",model="support:4b",embedding_model="embed:latest",conversation_source="ollama",embedding_source="ollama",context_size=4096,max_tokens=512,temperature="0.2",response_timeout_seconds=90,valid_response_rules={},runtime_profiles={
        "support":{"model":"support:4b","embedding_model":"embed:latest","conversation_source":"ollama","embedding_source":"ollama","context_size":8192,"max_tokens":700,"temperature":0.5,"response_timeout_seconds":120,"valid_response_rules":{"require_context_reference":False}},
        "intake":{"model":"intake:3b","embedding_model":"embed:latest","conversation_source":"ollama","embedding_source":"ollama","context_size":4096,"max_tokens":256,"temperature":0.1,"response_timeout_seconds":60,"valid_response_rules":{"reject_repeated_questions":True,"require_summary_fields":True}},
    })
    assert serialize_runtime(config,"support")["model"]=="support:4b"
    assert serialize_runtime(config,"support")["temperature"]==0.5
    assert serialize_runtime(config,"intake")["model"]=="intake:3b"
    assert serialize_runtime(config,"intake")["response_timeout_seconds"]==60
    assert serialize_runtime(config,"intake")["valid_response_rules"]["reject_repeated_questions"] is True


def test_management_schema_has_soft_delete_attachments_and_audit():
    assert "deleted_at" in User.__table__.c
    assert {"ticket_id","content_type","size_bytes","data"}<={column.name for column in TicketAttachment.__table__.columns}
    assert {"actor_user_id","action","target_type","details"}<={column.name for column in AuditLog.__table__.columns}
    bootstrap=Path(__file__).resolve().parents[1].joinpath("app/bootstrap.py").read_text()
    for fragment in ("CREATE TABLE IF NOT EXISTS ticket_attachments","CREATE TABLE IF NOT EXISTS audit_logs","runtime_profiles jsonb","deleted_at timestamptz"):
        assert fragment in bootstrap


def test_management_routes_enforce_scope_and_preserve_history():
    source=Path(__file__).resolve().parents[1].joinpath("app/main.py").read_text()
    for fragment in ('@app.get("/api/company/audit")','@app.get("/api/platform/audit")','@app.patch("/api/company/areas/{area_id}")','@app.patch("/api/company/users/{user_id}")','@app.patch("/api/platform/companies/{tenant_id}")','@app.patch("/api/tickets/{ticket_id}")'):
        assert fragment in source
    assert '@app.delete("/api/company/users/{user_id}"' in source
    assert 'user.deleted_at=datetime.now(timezone.utc)' in source
    assert 'Chamados encerrados não podem ser editados' in source
    assert 'O administrador da empresa deve solicitar ao administrador master' in source


def test_public_ticket_images_are_bounded_and_magic_checked():
    source=Path(__file__).resolve().parents[1].joinpath("app/main.py").read_text()
    assert '@app.post("/api/public/{slug}/tickets/with-attachments"' in source
    assert 'len(uploads)>5' in source
    assert '15*1024*1024' in source
    assert 'image/jpeg' in source and 'image/png' in source and 'image/webp' in source
    assert 'image/svg' not in source
