import pytest
from fastapi import HTTPException
from app.config import Settings
from app.models import Ticket, TicketStatus, User
from app.security import Principal, create_access_token, decode_access_token, hash_password, require_admin, require_agent, sign_public_context, verify_password
from app.main import ALLOWED_TRANSITIONS, verify_context

def test_database_password_with_url_characters_keeps_the_correct_host():
    password = "forte@com:/#caracteres?reservados"
    settings = Settings(
        _env_file=None,
        database_url=None,
        db_host="db",
        db_port=5432,
        db_name="chamados",
        db_user="chamados",
        db_password=password,
        jwt_secret="test-jwt-secret-that-is-at-least-32-characters",
        public_link_secret="test-public-secret-that-is-at-least-32-chars",
    )
    url = settings.sqlalchemy_database_url()
    assert url.host == "db"
    assert url.password == password
    assert password not in url.render_as_string(hide_password=True)

def test_python_enums_match_the_existing_varchar_database_columns():
    assert User.__table__.c.role.type.native_enum is False
    assert User.__table__.c.role.type.length == 20
    assert Ticket.__table__.c.status.type.native_enum is False
    assert Ticket.__table__.c.status.type.length == 30

def test_ai_credentials_are_binary_and_runtime_schema_is_migrated():
    from app.models import AIConfig
    from pathlib import Path
    assert str(AIConfig.__table__.c.api_key_encrypted.type)=="BLOB"
    bootstrap=Path(__file__).resolve().parents[1].joinpath("app/bootstrap.py").read_text()
    assert "api_key_encrypted bytea" in bootstrap

@pytest.mark.asyncio
async def test_runtime_schema_sends_json_defaults_as_raw_driver_sql():
    from app.bootstrap import ensure_runtime_schema
    executed=[]
    class Connection:
        async def exec_driver_sql(self,statement):executed.append(statement)
    class Session:
        async def connection(self):return Connection()
        async def execute(self,*_):raise AssertionError("text() reinterpretaria :true e :false como parâmetros")
    await ensure_runtime_schema(Session())
    rule_statement=next(statement for statement in executed if "valid_response_rules" in statement)
    assert '"allow_plain_text_repair":true' in rule_statement
    assert '"require_context_reference":false' in rule_statement

def test_passwords_are_argon2_and_verify():
    digest=hash_password("uma-senha-bem-forte")
    assert digest.startswith("$argon2")
    assert verify_password("uma-senha-bem-forte",digest)
    assert not verify_password("errada",digest)

def test_jwt_contains_server_signed_tenant():
    token=create_access_token(Principal(user_id="u1",tenant_id="t1",role="agent"))
    p=decode_access_token(token)
    assert p.tenant_id=="t1" and p.role=="agent"

def test_agent_cannot_access_admin_configuration():
    try:require_admin(Principal(user_id="u1",tenant_id="t1",role="agent"))
    except HTTPException as exc:assert exc.status_code==403
    else:raise AssertionError("agent recebeu acesso administrativo")

def test_admin_cannot_access_provider_ticket_management():
    with pytest.raises(HTTPException) as error:require_agent(Principal(user_id="u1",tenant_id="t1",role="admin"))
    assert error.value.status_code==403

def test_closed_is_a_terminal_ticket_stage():
    assert TicketStatus.closed in ALLOWED_TRANSITIONS[TicketStatus.resolved]
    assert ALLOWED_TRANSITIONS[TicketStatus.closed]==set()

def test_public_context_is_bound_to_slug():
    token=sign_public_context("zoho-suporte")
    verify_context("zoho-suporte",token)
    try:verify_context("outro-tenant",token)
    except HTTPException as exc:assert exc.status_code==403
    else:raise AssertionError("token público atravessou tenant")
    try:verify_context("zoho-suporte","zoho-suporte.data-invalida.assinatura")
    except HTTPException as exc:assert exc.status_code==403
    else:raise AssertionError("timestamp público inválido foi aceito")
