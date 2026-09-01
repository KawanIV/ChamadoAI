import hashlib, hmac, secrets, time
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from .config import get_settings

ph=PasswordHasher(); bearer=HTTPBearer(auto_error=False)
class Principal(BaseModel): user_id:str; tenant_id:str; role:str
def hash_password(value:str)->str:return ph.hash(value)
def verify_password(value:str,digest:str)->bool:
    try:return ph.verify(digest,value)
    except Exception:return False
def create_access_token(p:Principal)->str:
    now=datetime.now(timezone.utc);return jwt.encode({"sub":p.user_id,"tenant_id":p.tenant_id,"role":p.role,"iat":now,"exp":now+timedelta(minutes=30)},get_settings().jwt_secret,algorithm="HS256")
def current_principal(credentials:HTTPAuthorizationCredentials|None=Depends(bearer))->Principal:
    if not credentials:raise HTTPException(status.HTTP_401_UNAUTHORIZED,"Autenticação necessária")
    try:data=jwt.decode(credentials.credentials,get_settings().jwt_secret,algorithms=["HS256"],options={"require":["sub","tenant_id","role","exp"]});return Principal(user_id=data["sub"],tenant_id=data["tenant_id"],role=data["role"])
    except jwt.PyJWTError:raise HTTPException(status.HTTP_401_UNAUTHORIZED,"Sessão inválida")
def require_admin(p:Principal=Depends(current_principal))->Principal:
    if p.role!="admin":raise HTTPException(status.HTTP_403_FORBIDDEN,"Permissão insuficiente")
    return p
def new_public_token()->tuple[str,str]:
    raw=secrets.token_urlsafe(32);return raw,hashlib.sha256(raw.encode()).hexdigest()
def valid_public_token(raw:str,digest:str)->bool:return hmac.compare_digest(hashlib.sha256(raw.encode()).hexdigest(),digest)
def sign_public_context(slug:str)->str:
    ts=str(int(time.time()));payload=f"{slug}.{ts}";sig=hmac.new(get_settings().public_link_secret.encode(),payload.encode(),hashlib.sha256).hexdigest();return f"{payload}.{sig}"
