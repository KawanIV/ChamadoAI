import hashlib, hmac, re, time, uuid
from datetime import datetime, timedelta, timezone
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from .config import get_settings
from .database import get_db, set_tenant_context
from .assistant import INTAKE_PROMPT, MAX_QUESTIONS, SUPPORT_PROMPT, chunk_document, extract_document, normalize_summary, read_conversation_state, sign_conversation_state
from .models import AIConfig, KnowledgeChunk, KnowledgeDocument, Resolution, Role, Tenant, Ticket, TicketStatus, TicketStatusHistory, UsageEvent, User
from .ollama import ask_json, list_models
from .schemas import AIConfigIn, LoginIn, PublicChatIn, PublicTicketIn, ResolutionIn, TicketStatusIn, UserCreateIn
from .security import Principal, create_access_token, current_principal, new_public_token, require_admin, require_agent, verify_password

settings=get_settings();app=FastAPI(title="Chamados API",docs_url=None if settings.environment=="production" else "/docs")
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.cors_origins.split(",")],allow_credentials=True,allow_methods=["GET","POST","PUT","PATCH","DELETE"],allow_headers=["Authorization","Content-Type"])
_hits:dict[str,list[float]]={}
ALLOWED_TRANSITIONS={
    TicketStatus.new:{TicketStatus.analysis,TicketStatus.cancelled},
    TicketStatus.analysis:{TicketStatus.new,TicketStatus.working,TicketStatus.waiting,TicketStatus.cancelled},
    TicketStatus.working:{TicketStatus.analysis,TicketStatus.waiting,TicketStatus.validation,TicketStatus.cancelled},
    TicketStatus.waiting:{TicketStatus.analysis,TicketStatus.working,TicketStatus.validation,TicketStatus.cancelled},
    TicketStatus.validation:{TicketStatus.working,TicketStatus.resolved,TicketStatus.cancelled},
    TicketStatus.resolved:{TicketStatus.working,TicketStatus.closed},
    TicketStatus.cancelled:{TicketStatus.new,TicketStatus.closed},
    TicketStatus.closed:set(),
}
@app.middleware("http")
async def security_headers(request:Request,call_next):
    response=await call_next(request);response.headers.update({"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"no-referrer","Permissions-Policy":"camera=(), microphone=(), geolocation=()","Content-Security-Policy":"default-src 'none'; frame-ancestors 'none'"});return response
def public_limit(request:Request):
    host=request.client.host if request.client else "unknown";scope="login" if request.url.path.endswith("/auth/login") else "public";key=f"{scope}:{host}";limit=10 if scope=="login" else 30;now=time.time();recent=[x for x in _hits.get(key,[]) if now-x<60]
    if len(recent)>=limit:raise HTTPException(429,"Muitas tentativas. Aguarde um minuto.")
    _hits[key]=recent+[now]
def verify_context(slug:str,token:str):
    try:token_slug,ts,sig=token.rsplit(".",2);timestamp=int(ts);payload=f"{token_slug}.{ts}";expected=hmac.new(settings.public_link_secret.encode(),payload.encode(),hashlib.sha256).hexdigest()
    except (ValueError,TypeError):raise HTTPException(403,"Link público inválido")
    if token_slug!=slug or not hmac.compare_digest(sig,expected) or time.time()-timestamp>86400:raise HTTPException(403,"Link público inválido ou expirado")
@app.get("/health")
async def health():return {"status":"ok"}
@app.post("/api/auth/login")
async def login(data:LoginIn,request:Request,db:AsyncSession=Depends(get_db)):
    public_limit(request);tenant=(await db.execute(select(Tenant).where(Tenant.public_slug==data.tenant_slug,Tenant.active.is_(True)))).scalar_one_or_none()
    if not tenant:raise HTTPException(401,"Credenciais inválidas")
    await set_tenant_context(db,str(tenant.id));user=(await db.execute(select(User).where(User.tenant_id==tenant.id,User.email==data.email.lower(),User.active.is_(True)))).scalar_one_or_none()
    if not user or not verify_password(data.password,user.password_hash):raise HTTPException(401,"Credenciais inválidas")
    principal=Principal(user_id=str(user.id),tenant_id=str(tenant.id),role=user.role.value);token=create_access_token(principal)
    response=JSONResponse({"user":{"id":str(user.id),"name":user.name,"email":user.email,"role":user.role.value}});response.set_cookie("chamados_session",token,httponly=True,secure=settings.cookie_secure,samesite="strict",max_age=1800,path="/");return response
@app.get("/api/auth/me")
async def me(p:Principal=Depends(current_principal),db:AsyncSession=Depends(get_db)):
    await set_tenant_context(db,p.tenant_id);user=(await db.execute(select(User).where(User.id==uuid.UUID(p.user_id),User.tenant_id==uuid.UUID(p.tenant_id),User.active.is_(True)))).scalar_one_or_none()
    if not user:raise HTTPException(401,"Sessão inválida")
    return {"id":str(user.id),"name":user.name,"email":user.email,"role":user.role.value}
@app.post("/api/auth/logout",status_code=204)
async def logout(response:Response):response.delete_cookie("chamados_session",path="/",samesite="strict",secure=settings.cookie_secure)
@app.get("/api/public/{slug}",dependencies=[Depends(public_limit)])
async def public_info(slug:str,db:AsyncSession=Depends(get_db)):
    tenant=(await db.execute(select(Tenant).where(Tenant.public_slug==slug,Tenant.active.is_(True)))).scalar_one_or_none()
    if not tenant:raise HTTPException(404,"Portal não encontrado")
    await set_tenant_context(db,str(tenant.id));config=await db.get(AIConfig,tenant.id)
    from .security import sign_public_context
    return {"company":tenant.name,"public_context":sign_public_context(slug),"model":config.model if config else settings.default_model}
@app.post("/api/public/{slug}/tickets",dependencies=[Depends(public_limit)],status_code=201)
async def create_ticket(slug:str,data:PublicTicketIn,db:AsyncSession=Depends(get_db)):
    verify_context(slug,data.public_context);tenant=(await db.execute(select(Tenant).where(Tenant.public_slug==slug,Tenant.active.is_(True)))).scalar_one_or_none()
    if not tenant:raise HTTPException(404,"Portal não encontrado")
    await set_tenant_context(db,str(tenant.id));raw,digest=new_public_token();protocol=(await db.scalar(select(func.coalesce(func.max(Ticket.protocol),0))))+1
    ticket=Ticket(tenant_id=tenant.id,protocol=protocol,requester_name=data.requester_name.strip(),department=data.department.strip(),contact=data.contact,title=(data.title or data.description[:120]).strip(),summary=data.description.strip(),product=data.product.strip(),priority=data.priority,public_token_hash=digest)
    db.add(ticket);await db.flush();db.add(TicketStatusHistory(tenant_id=tenant.id,ticket_id=ticket.id,status=TicketStatus.new));db.add(UsageEvent(tenant_id=tenant.id,event_type="ticket_created",success=True));await db.commit();return {"protocol":protocol,"access_token":raw}

def retrieval_terms(value:str)->list[str]:
    blocked={"para","como","isso","essa","esse","uma","com","não","que","por","mais","está","tenho","zoho"}
    return [x for x in dict.fromkeys(re.findall(r"[a-zA-ZÀ-ÿ0-9_-]{4,}",value.lower())) if x not in blocked][:8]

async def retrieve_knowledge(db:AsyncSession,tenant_id:uuid.UUID,query:str)->str:
    terms=retrieval_terms(query)
    if not terms:return ""
    escaped=[x.replace("\\","\\\\").replace("%","\\%").replace("_","\\_") for x in terms]
    chunk_conditions=[KnowledgeChunk.content.ilike(f"%{term}%",escape="\\") for term in escaped]
    document_rows=(await db.execute(select(KnowledgeDocument.title,KnowledgeChunk.content).join(KnowledgeChunk,KnowledgeChunk.document_id==KnowledgeDocument.id).where(KnowledgeDocument.tenant_id==tenant_id,KnowledgeChunk.tenant_id==tenant_id,KnowledgeDocument.status=="active",or_(*chunk_conditions)).limit(6))).all()
    resolution_conditions=[]
    for term in escaped:resolution_conditions.extend([Resolution.confirmed_problem.ilike(f"%{term}%",escape="\\"),Resolution.root_cause.ilike(f"%{term}%",escape="\\"),Resolution.solution.ilike(f"%{term}%",escape="\\")])
    resolution_rows=(await db.execute(select(Resolution).where(Resolution.tenant_id==tenant_id,Resolution.reusable.is_(True),or_(*resolution_conditions)).limit(3))).scalars().all()
    sources=[]
    for title,content in document_rows:sources.append(f"DOCUMENTO: {title}\n{content[:1800]}")
    for item in resolution_rows:sources.append(f"RESOLUÇÃO APROVADA\nProblema: {item.confirmed_problem}\nCausa: {item.root_cause}\nSolução: {item.solution}\nValidação: {item.validation}")
    return "\n\n---\n\n".join(sources)[:12000]

async def find_related_ticket(db:AsyncSession,tenant_id:uuid.UUID,query:str)->Ticket|None:
    terms=retrieval_terms(query)
    if not terms:return None
    rows=(await db.execute(select(Ticket).where(Ticket.tenant_id==tenant_id,Ticket.status.notin_([TicketStatus.cancelled])).order_by(Ticket.created_at.desc()).limit(80))).scalars().all()
    query_terms=set(terms);best=None;best_score=0
    for ticket in rows:
        ticket_terms=set(retrieval_terms(f"{ticket.title} {ticket.summary} {ticket.product}"));score=len(query_terms&ticket_terms)
        if score>best_score:best,best_score=ticket,score
    return best if best_score>=2 else None

async def tracked_ask(db:AsyncSession,tenant_id:uuid.UUID,model:str,*args,**kwargs)->dict:
    started=time.monotonic()
    try:
        result=await ask_json(model,*args,**kwargs);success=True
    except Exception:
        success=False;result=None
    duration=int((time.monotonic()-started)*1000)
    db.add(UsageEvent(tenant_id=tenant_id,event_type="assistant_request",model=model,success=success,duration_ms=duration))
    db.add(UsageEvent(tenant_id=tenant_id,event_type="llm_request",model=model,success=success,duration_ms=duration))
    await db.commit()
    if not success:raise HTTPException(504,"O modelo demorou mais que o esperado para gerar uma resposta válida")
    return result

@app.post("/api/public/{slug}/chat",dependencies=[Depends(public_limit)])
async def public_chat(slug:str,data:PublicChatIn,db:AsyncSession=Depends(get_db)):
    verify_context(slug,data.public_context);tenant=(await db.execute(select(Tenant).where(Tenant.public_slug==slug,Tenant.active.is_(True)))).scalar_one_or_none()
    if not tenant:raise HTTPException(404,"Portal não encontrado")
    await set_tenant_context(db,str(tenant.id));config=await db.get(AIConfig,tenant.id);model=config.model if config else settings.default_model
    clean=[]
    for message in data.messages[-12:]:
        role=message.get("role");content=message.get("content","")
        if role not in {"user","assistant"} or not isinstance(content,str):raise HTTPException(422,"Conversa inválida")
        clean.append({"role":role,"content":content[:5000]})
    context_size=config.context_size if config else 8192;max_tokens=config.max_tokens if config else 512;temperature=float(config.temperature) if config else .2
    if data.assistant=="support":
        query=next((m["content"] for m in reversed(clean) if m["role"]=="user"),"");sources=await retrieve_knowledge(db,tenant.id,query)
        if not sources:
            db.add(UsageEvent(tenant_id=tenant.id,event_type="assistant_request",model=model,success=True,duration_ms=0));await db.commit();return {"message":"Ainda não encontrei conteúdo aprovado na base de conhecimento para orientar essa demanda com segurança. Posso encaminhar a conversa para a abertura de um chamado.","model":model,"phase":"offer_ticket","question_count":0,"conversation_state":None}
        safe_sources=sources.replace("<fontes>","[marcador removido]").replace("</fontes>","[marcador removido]");payload=await tracked_ask(db,tenant.id,model,f"{SUPPORT_PROMPT}\n<fontes>\n{safe_sources}\n</fontes>",clean,context_size,max_tokens,temperature,"support");action=payload.get("action")
        phase="offer_ticket" if action=="offer_ticket" else "answer";message=str(payload.get("message","")).strip()[:5000]
        if not message:raise HTTPException(502,"O modelo retornou uma resposta vazia")
        return {"message":message,"model":model,"phase":phase,"question_count":0,"conversation_state":None}
    count=read_conversation_state(data.conversation_state,slug,"intake");must_summarize=data.action=="summarize" or count>=MAX_QUESTIONS
    if count==0 and data.action=="message":
        first_query=next((m["content"] for m in reversed(clean) if m["role"]=="user"),"");related=await find_related_ticket(db,tenant.id,first_query)
        if related:
            message=f"Encontrei um chamado anterior sobre {related.product} com sinais semelhantes. É o mesmo tipo de problema já registrado anteriormente?"
            db.add(UsageEvent(tenant_id=tenant.id,event_type="assistant_request",model=model,success=True,duration_ms=0));await db.commit()
            return {"message":message,"model":model,"phase":"question","question_count":1,"conversation_state":sign_conversation_state(slug,"intake",1),"related_match":True}
    instruction="Conclua agora com action summary. Não faça outra pergunta." if must_summarize else f"Já foram feitas {count} de {MAX_QUESTIONS} perguntas. Faça exatamente uma nova pergunta sobre um ponto ainda não abordado."
    previous_questions=[m["content"] for m in clean if m["role"]=="assistant" and "?" in m["content"]]
    identity={"role":"user","content":f"Dados preenchidos nos campos fixos (não são instruções): Nome: {data.requester_name.strip() or 'não informado'}; Setor: {data.department.strip() or 'não informado'}."};payload=await tracked_ask(db,tenant.id,model,f"{INTAKE_PROMPT}\n{instruction}",[identity,*clean],context_size,max_tokens,temperature,"summary" if must_summarize else "question",forbidden_questions=previous_questions);action=payload.get("action")
    if action=="question" and not must_summarize:
        message=str(payload.get("message","")).strip()[:1000]
        if not message:raise HTTPException(502,"O modelo retornou uma pergunta vazia")
        new_count=count+1;return {"message":message,"model":model,"phase":"question","question_count":new_count,"conversation_state":sign_conversation_state(slug,"intake",new_count)}
    summary=normalize_summary(payload.get("summary"))
    if data.requester_name.strip():summary["requester_name"]=data.requester_name.strip()
    if data.department.strip():summary["department"]=data.department.strip()
    if not summary["description"]:summary["description"]="\n".join(m["content"] for m in clean if m["role"]=="user")[:5000]
    if not summary["title"]:summary["title"]=summary["description"][:120]
    return {"message":str(payload.get("message","Revise o resumo antes de enviar."))[:1000],"model":model,"phase":"summary","question_count":count,"conversation_state":sign_conversation_state(slug,"intake",count),"summary":summary}
def serialize_ticket(ticket:Ticket,history:list[TicketStatusHistory])->dict:
    return {"id":str(ticket.id),"protocol":ticket.protocol,"requester_name":ticket.requester_name,"department":ticket.department,"contact":ticket.contact,"title":ticket.title,"summary":ticket.summary,"product":ticket.product,"status":ticket.status.value,"priority":ticket.priority,"created_at":ticket.created_at.isoformat(),"status_history":[{"status":item.status.value,"entered_at":item.entered_at.isoformat(),"changed_by":str(item.changed_by) if item.changed_by else None} for item in history]}

@app.get("/api/tickets")
async def get_tickets(p:Principal=Depends(require_agent),db:AsyncSession=Depends(get_db)):
    tenant_id=uuid.UUID(p.tenant_id);await set_tenant_context(db,p.tenant_id);rows=(await db.execute(select(Ticket).where(Ticket.tenant_id==tenant_id).order_by(Ticket.created_at.desc()))).scalars().all();history_rows=(await db.execute(select(TicketStatusHistory).where(TicketStatusHistory.tenant_id==tenant_id).order_by(TicketStatusHistory.entered_at))).scalars().all();history_by_ticket:dict[uuid.UUID,list[TicketStatusHistory]]={}
    for item in history_rows:history_by_ticket.setdefault(item.ticket_id,[]).append(item)
    return [serialize_ticket(ticket,history_by_ticket.get(ticket.id,[])) for ticket in rows]

@app.patch("/api/tickets/{ticket_id}/status")
async def change_ticket_status(ticket_id:uuid.UUID,data:TicketStatusIn,p:Principal=Depends(require_agent),db:AsyncSession=Depends(get_db)):
    tenant_id=uuid.UUID(p.tenant_id);await set_tenant_context(db,p.tenant_id);ticket=(await db.execute(select(Ticket).where(Ticket.id==ticket_id,Ticket.tenant_id==tenant_id))).scalar_one_or_none()
    if not ticket:raise HTTPException(404,"Chamado não encontrado")
    target=TicketStatus(data.status)
    if target==ticket.status:return {"status":target.value}
    if target not in ALLOWED_TRANSITIONS[ticket.status]:raise HTTPException(409,"Transição de status não permitida")
    ticket.status=target;db.add(TicketStatusHistory(tenant_id=tenant_id,ticket_id=ticket.id,status=target,changed_by=uuid.UUID(p.user_id)));await db.commit();return {"status":target.value}
@app.post("/api/tickets/{ticket_id}/resolution")
async def resolve(ticket_id:uuid.UUID,data:ResolutionIn,p:Principal=Depends(require_agent),db:AsyncSession=Depends(get_db)):
    await set_tenant_context(db,p.tenant_id);ticket=(await db.execute(select(Ticket).where(Ticket.id==ticket_id,Ticket.tenant_id==uuid.UUID(p.tenant_id)))).scalar_one_or_none()
    if not ticket:raise HTTPException(404,"Chamado não encontrado")
    document={"problem":data.confirmed_problem,"cause":data.root_cause,"solution":data.solution,"validation":data.validation} if data.reusable else None
    if ticket.status==TicketStatus.closed:raise HTTPException(409,"Chamados encerrados não podem ser alterados")
    db.add(Resolution(tenant_id=ticket.tenant_id,ticket_id=ticket.id,confirmed_problem=data.confirmed_problem,root_cause=data.root_cause,solution=data.solution,validation=data.validation,reusable=data.reusable,sanitized_document=document));ticket.status=TicketStatus.resolved;db.add(TicketStatusHistory(tenant_id=ticket.tenant_id,ticket_id=ticket.id,status=TicketStatus.resolved,changed_by=uuid.UUID(p.user_id)));await db.commit();return {"status":"resolved"}

@app.get("/api/admin/metrics")
async def admin_metrics(days:int=Query(default=30,ge=1,le=90),p:Principal=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    tenant_id=uuid.UUID(p.tenant_id);await set_tenant_context(db,p.tenant_id);since=datetime.now(timezone.utc)-timedelta(days=days)
    providers=await db.scalar(select(func.count()).select_from(User).where(User.tenant_id==tenant_id,User.role==Role.agent,User.active.is_(True))) or 0
    tickets_created=await db.scalar(select(func.count()).select_from(Ticket).where(Ticket.tenant_id==tenant_id,Ticket.created_at>=since)) or 0
    documents=await db.scalar(select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.tenant_id==tenant_id,KnowledgeDocument.created_at>=since)) or 0
    stage_rows=(await db.execute(select(TicketStatusHistory.status,TicketStatusHistory.entered_at).where(TicketStatusHistory.tenant_id==tenant_id,TicketStatusHistory.entered_at>=since))).all()
    event_rows=(await db.execute(select(UsageEvent.event_type,UsageEvent.success,UsageEvent.duration_ms,UsageEvent.created_at).where(UsageEvent.tenant_id==tenant_id,UsageEvent.created_at>=since))).all()
    llm=[row for row in event_rows if row.event_type=="llm_request"];assistant=[row for row in event_rows if row.event_type=="assistant_request"]
    daily={}
    for offset in range(days):
        key=(since.date()+timedelta(days=offset+1)).isoformat();daily[key]={"date":key,"conversations":0,"tickets":0}
    for row in assistant:
        key=row.created_at.date().isoformat()
        if key in daily:daily[key]["conversations"]+=1
    ticket_dates=(await db.execute(select(Ticket.created_at).where(Ticket.tenant_id==tenant_id,Ticket.created_at>=since))).scalars().all()
    for created_at in ticket_dates:
        key=created_at.date().isoformat()
        if key in daily:daily[key]["tickets"]+=1
    durations=[row.duration_ms for row in llm if row.duration_ms is not None]
    return {"period_days":days,"active_providers":providers,"conversations":len(assistant),"tickets_created":tickets_created,"tickets_resolved":sum(1 for status,_ in stage_rows if status==TicketStatus.resolved),"tickets_closed":sum(1 for status,_ in stage_rows if status==TicketStatus.closed),"documents_indexed":documents,"llm_requests":len(llm),"llm_failures":sum(1 for row in llm if not row.success),"average_llm_latency_ms":round(sum(durations)/len(durations)) if durations else 0,"daily":list(daily.values())}
@app.get("/api/admin/ai/models")
async def models(_:Principal=Depends(require_admin)):
    try:return {"models":await list_models()}
    except Exception:raise HTTPException(502,"Não foi possível consultar o Ollama")
@app.get("/api/admin/ai")
async def get_ai(p:Principal=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    await set_tenant_context(db,p.tenant_id);config=await db.get(AIConfig,uuid.UUID(p.tenant_id))
    return {"model":config.model if config else settings.default_model,"embedding_model":config.embedding_model if config else "nomic-embed-text","context_size":config.context_size if config else 8192,"max_tokens":config.max_tokens if config else 512,"temperature":float(config.temperature) if config else .2}
@app.put("/api/admin/ai")
async def save_ai(data:AIConfigIn,p:Principal=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    available=[m.get("name") for m in await list_models()]
    if data.model not in available or data.embedding_model not in available:raise HTTPException(400,"Modelo não instalado no Ollama")
    await set_tenant_context(db,p.tenant_id);config=await db.get(AIConfig,uuid.UUID(p.tenant_id))
    if not config:config=AIConfig(tenant_id=uuid.UUID(p.tenant_id),model=data.model,embedding_model=data.embedding_model);db.add(config)
    config.model=data.model;config.embedding_model=data.embedding_model;config.context_size=data.context_size;config.max_tokens=data.max_tokens;config.temperature=str(data.temperature);await db.commit();return {"saved":True}

@app.get("/api/admin/knowledge/documents")
async def knowledge_documents(p:Principal=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    tenant_id=uuid.UUID(p.tenant_id);await set_tenant_context(db,p.tenant_id)
    rows=(await db.execute(select(KnowledgeDocument,func.count(KnowledgeChunk.id)).outerjoin(KnowledgeChunk,KnowledgeChunk.document_id==KnowledgeDocument.id).where(KnowledgeDocument.tenant_id==tenant_id).group_by(KnowledgeDocument.id).order_by(KnowledgeDocument.created_at.desc()))).all()
    return [{"id":str(item.id),"title":item.title,"filename":item.filename,"status":item.status,"chunks":count,"created_at":item.created_at.isoformat()} for item,count in rows]

@app.post("/api/admin/knowledge/documents",status_code=201)
async def upload_knowledge_document(file:UploadFile=File(...),title:str=Form(""),p:Principal=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    tenant_id=uuid.UUID(p.tenant_id);await set_tenant_context(db,p.tenant_id)
    filename=re.split(r"[/\\\\]",file.filename or "documento")[-1].strip()[:255];data=await file.read(10*1024*1024+1);content=extract_document(filename,file.content_type or "application/octet-stream",data);digest=hashlib.sha256(data).hexdigest()
    if (await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.tenant_id==tenant_id,KnowledgeDocument.sha256==digest))).scalar_one_or_none():raise HTTPException(409,"Este documento já está na base de conhecimento")
    document_title=(title.strip() or filename)[:180];document=KnowledgeDocument(tenant_id=tenant_id,title=document_title,filename=filename,content_type=file.content_type or "application/octet-stream",sha256=digest,status="active",uploaded_by=uuid.UUID(p.user_id));db.add(document);await db.flush()
    chunks=chunk_document(content)
    for index,chunk in enumerate(chunks):db.add(KnowledgeChunk(tenant_id=tenant_id,document_id=document.id,chunk_index=index,content=chunk))
    await db.commit();return {"id":str(document.id),"title":document.title,"chunks":len(chunks)}
@app.get("/api/admin/users")
async def users(p:Principal=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    await set_tenant_context(db,p.tenant_id);rows=(await db.execute(select(User).where(User.tenant_id==uuid.UUID(p.tenant_id),User.role==Role.agent).order_by(User.name))).scalars().all();return [{"id":str(u.id),"name":u.name,"email":u.email,"role":u.role.value,"active":u.active} for u in rows]
@app.post("/api/admin/users",status_code=201)
async def create_user(data:UserCreateIn,p:Principal=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    from .security import hash_password
    await set_tenant_context(db,p.tenant_id);email=data.email.strip().lower()
    if (await db.execute(select(User).where(User.tenant_id==uuid.UUID(p.tenant_id),User.email==email))).scalar_one_or_none():raise HTTPException(409,"E-mail já cadastrado")
    user=User(tenant_id=uuid.UUID(p.tenant_id),name=data.name.strip(),email=email,password_hash=hash_password(data.password),role=Role.agent);db.add(user);await db.commit();return {"id":str(user.id),"name":user.name,"email":user.email,"role":user.role.value}
