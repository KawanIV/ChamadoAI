from fastapi import HTTPException
from app.security import Principal, create_access_token, decode_access_token, hash_password, require_admin, sign_public_context, verify_password
from app.main import verify_context

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

def test_public_context_is_bound_to_slug():
    token=sign_public_context("zoho-suporte")
    verify_context("zoho-suporte",token)
    try:verify_context("outro-tenant",token)
    except HTTPException as exc:assert exc.status_code==403
    else:raise AssertionError("token público atravessou tenant")
