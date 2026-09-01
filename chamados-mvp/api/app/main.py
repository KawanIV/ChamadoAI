import hashlib, hmac, time, uuid
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from .config import get_settings
from .database import get_db, set_tenant_context
from .models import AIConfig, Resolution, Tenant, Ticket, TicketStatus, User
from .ollama import list_models
from .schemas import AIConfigIn, LoginIn, PublicTicketIn, ResolutionIn
from .security import Principal, create_access_token, current_principal, new_public_token, require_admin, verify_password

settings=get_settings();app=FastAPI(title="Chamados API",docs_url=None if settings.environment=="production" else "/docs")
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.cors_origins.split(",")],allow_credentials=True,allow_methods=["GET","POST","PATCH"],allow_headers=["Authorization","Content-Type"])
_hits:dict[str,list[float]]={}
@app.middleware("http")
async def security_headers(request:Request,call_next):
    response=await call_next(request);response.headers.update({"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"no-referrer","Permissions-Policy":"camera=(), microphone=(), geolocation=()","Content-Security-Policy":"default-src 'none'; frame-ancestors 'none'"});return response
def public_limit(request:Request):
    key=request.client.host if request.client else "unknown";now=time.time();recent=[x for x in _hits.get(key,[]) if now-x<60]
    if len(recent)>=10:raise HTTPException(429,"Muitas tentativas. Aguarde um minuto.")
    _hits[key]=recent+[now]
def verify_context(slug:str,token:str):
    try:token_slug,ts,sig=token.rsplit(".",2);payload=f"{token_slug}.{ts}";expected=hmac.new(settings.public_link_secret.encode(),payload.encode(),hashlib.sha256).hexdigest()
    except ValueError:raise HTTPException(403,"Link público inválido")
    if token_slug!=slug or not hmac.compare_digest(sig,expected) or time.time()-int(ts)>86400:raise HTTPException(403,"Link público inválido ou expirado")
@app.get("/health")
async def health():return {"status":"ok"}
@app.post("/api/auth/login")
async def login(data:LoginIn,request:Request,db:AsyncSession=Depends(get_db)):
    public_limit(request);tenant=(await db.execute(select(Tenant).where(Tenant.public_slug==data.tenant_slug,Tenant.active.is_(True)))).scalar_one_or_none()
    if not tenant:raise HTTPException(401,"Credenciais inválidas")
    await set_tenant_context(db,str(tenant.id));user=(await db.execute(select(User).where(User.tenant_id==tenant.id,User.email==data.email.lower(),User.active.is_(True)))).scalar_one_or_none()
    if not user or not verify_password(data.password,user.password_hash):raise HTTPException(401,"Credenciais inválidas")
    principal=Principal(user_id=str(user.id),tenant_id=str(tenant.id),role=user.role.value);return {"access_token":create_access_token(principal),"token_type":"bearer"}
@app.get("/api/public/{slug}",dependencies=[Depends(public_limit)])
async def public_info(slug:str,db:AsyncSession=Depends(get_db)):
    tenant=(await db.execute(select(Tenant).where(Tenant.public_slug==slug,Tenant.active.is_(True)))).scalar_one_or_none()
    if not tenant:raise HTTPException(404,"Portal não encontrado")
    from .security import sign_public_context
    return {"company":tenant.name,"public_context":sign_public_context(slug)}
@app.post("/api/public/{slug}/tickets",dependencies=[Depends(public_limit)],status_code=201)
async def create_ticket(slug:str,data:PublicTicketIn,db:AsyncSession=Depends(get_db)):
    verify_context(slug,data.public_context);tenant=(await db.execute(select(Tenant).where(Tenant.public_slug==slug,Tenant.active.is_(True)))).scalar_one_or_none()
    if not tenant:raise HTTPException(404,"Portal não encontrado")
    await set_tenant_context(db,str(tenant.id));raw,digest=new_public_token();protocol=(await db.scalar(select(func.coalesce(func.max(Ticket.protocol),0))))+1
    ticket=Ticket(tenant_id=tenant.id,protocol=protocol,requester_name=data.requester_name,department=data.department,contact=data.contact,title=data.description[:120],summary=data.description,product=data.product,public_token_hash=digest)
    db.add(ticket);await db.commit();return {"protocol":protocol,"access_token":raw}
@app.get("/api/tickets")
async def get_tickets(p:Principal=Depends(current_principal),db:AsyncSession=Depends(get_db)):
    await set_tenant_context(db,p.tenant_id);rows=(await db.execute(select(Ticket).where(Ticket.tenant_id==uuid.UUID(p.tenant_id)).order_by(Ticket.created_at.desc()))).scalars().all();return [{"id":str(x.id),"protocol":x.protocol,"title":x.title,"status":x.status,"priority":x.priority} for x in rows]
@app.post("/api/tickets/{ticket_id}/resolution")
async def resolve(ticket_id:uuid.UUID,data:ResolutionIn,p:Principal=Depends(current_principal),db:AsyncSession=Depends(get_db)):
    await set_tenant_context(db,p.tenant_id);ticket=(await db.execute(select(Ticket).where(Ticket.id==ticket_id,Ticket.tenant_id==uuid.UUID(p.tenant_id)))).scalar_one_or_none()
    if not ticket:raise HTTPException(404,"Chamado não encontrado")
    document={"problem":data.confirmed_problem,"cause":data.root_cause,"solution":data.solution,"validation":data.validation} if data.reusable else None
    db.add(Resolution(tenant_id=ticket.tenant_id,ticket_id=ticket.id,confirmed_problem=data.confirmed_problem,root_cause=data.root_cause,solution=data.solution,validation=data.validation,reusable=data.reusable,sanitized_document=document));ticket.status=TicketStatus.resolved;await db.commit();return {"status":"resolved"}
@app.get("/api/admin/ai/models")
async def models(_:Principal=Depends(require_admin)):return {"models":await list_models()}
@app.put("/api/admin/ai")
async def save_ai(data:AIConfigIn,p:Principal=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    available=await list_models()
    if data.model not in available or data.embedding_model not in available:raise HTTPException(400,"Modelo não instalado no Ollama")
    await set_tenant_context(db,p.tenant_id);config=await db.get(AIConfig,uuid.UUID(p.tenant_id))
    if not config:config=AIConfig(tenant_id=uuid.UUID(p.tenant_id),model=data.model,embedding_model=data.embedding_model);db.add(config)
    config.model=data.model;config.embedding_model=data.embedding_model;config.context_size=data.context_size;config.max_tokens=data.max_tokens;config.temperature=str(data.temperature);await db.commit();return {"saved":True}
