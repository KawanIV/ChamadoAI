import asyncio, os
from sqlalchemy import select
from .config import get_settings
from .database import SessionLocal, set_platform_context
from .models import AIConfig, Role, Skill, Tenant, User
from .security import hash_password

TENANT_TABLES=("users","tickets","resolutions","ai_configs","knowledge_documents","knowledge_chunks","ticket_status_history","usage_events","skills")
POLICY_TABLES=(*TENANT_TABLES,"areas")

async def ensure_runtime_schema(db):
    statements=[
        *[f"ALTER TABLE IF EXISTS {table} DISABLE ROW LEVEL SECURITY" for table in TENANT_TABLES],
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check",
        "ALTER TABLE users ADD CONSTRAINT users_role_check CHECK(role IN('admin','platform_admin','company_admin','agent')) NOT VALID",
        "ALTER TABLE users VALIDATE CONSTRAINT users_role_check",
        "CREATE TABLE IF NOT EXISTS areas(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenants(id),name varchar(120) NOT NULL,active boolean NOT NULL DEFAULT true,created_at timestamptz NOT NULL DEFAULT now())",
        "CREATE UNIQUE INDEX IF NOT EXISTS areas_tenant_name_idx ON areas(tenant_id,lower(name))",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS area_id uuid REFERENCES areas(id)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_data bytea",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_content_type varchar(40)",
        "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS area_id uuid REFERENCES areas(id)",
        "CREATE TABLE IF NOT EXISTS knowledge_documents(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenants(id),area_id uuid REFERENCES areas(id),title varchar(180) NOT NULL,filename varchar(255) NOT NULL,content_type varchar(100) NOT NULL,sha256 varchar(64) NOT NULL,status varchar(20) NOT NULL DEFAULT 'active',uploaded_by uuid NOT NULL REFERENCES users(id),created_at timestamptz NOT NULL DEFAULT now())",
        "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS area_id uuid REFERENCES areas(id)",
        "INSERT INTO areas(tenant_id,name) SELECT t.id,'Geral' FROM tenants t WHERE t.public_slug<>'plataforma' AND NOT EXISTS(SELECT 1 FROM areas a WHERE a.tenant_id=t.id AND lower(a.name)='geral')",
        "UPDATE users u SET area_id=a.id FROM areas a WHERE u.tenant_id=a.tenant_id AND lower(a.name)='geral' AND u.role='agent' AND u.area_id IS NULL",
        "UPDATE tickets t SET area_id=a.id FROM areas a WHERE t.tenant_id=a.tenant_id AND lower(a.name)='geral' AND t.area_id IS NULL",
        "UPDATE knowledge_documents d SET area_id=a.id FROM areas a WHERE d.tenant_id=a.tenant_id AND lower(a.name)='geral' AND d.area_id IS NULL",
        "ALTER TABLE tickets ALTER COLUMN area_id SET NOT NULL",
        "ALTER TABLE knowledge_documents ALTER COLUMN area_id SET NOT NULL",
        "ALTER TABLE knowledge_documents DROP CONSTRAINT IF EXISTS knowledge_documents_tenant_id_sha256_key",
        "CREATE UNIQUE INDEX IF NOT EXISTS knowledge_documents_tenant_area_sha_idx ON knowledge_documents(tenant_id,area_id,sha256)",
        "CREATE TABLE IF NOT EXISTS knowledge_chunks(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenants(id),document_id uuid NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,chunk_index integer NOT NULL,content text NOT NULL,UNIQUE(document_id,chunk_index))",
        "CREATE TABLE IF NOT EXISTS ticket_status_history(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenants(id),ticket_id uuid NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,status varchar(30) NOT NULL,changed_by uuid REFERENCES users(id),entered_at timestamptz NOT NULL DEFAULT now())",
        "CREATE TABLE IF NOT EXISTS usage_events(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenants(id),event_type varchar(40) NOT NULL,model varchar(120),success boolean NOT NULL DEFAULT true,duration_ms integer,prompt_tokens integer,response_tokens integer,tokens_estimated boolean NOT NULL DEFAULT false,created_at timestamptz NOT NULL DEFAULT now())",
        "ALTER TABLE ai_configs ADD COLUMN IF NOT EXISTS api_base_url varchar(500)",
        "ALTER TABLE ai_configs ADD COLUMN IF NOT EXISTS api_key_encrypted bytea",
        "DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='ai_configs' AND column_name='conversation_source') THEN ALTER TABLE ai_configs ADD COLUMN conversation_source varchar(20) NOT NULL DEFAULT 'ollama'; UPDATE ai_configs SET conversation_source='external' WHERE provider<>'ollama'; END IF; END $$",
        "ALTER TABLE ai_configs ADD COLUMN IF NOT EXISTS embedding_source varchar(20) NOT NULL DEFAULT 'ollama'",
        "ALTER TABLE ai_configs ADD COLUMN IF NOT EXISTS response_timeout_seconds integer NOT NULL DEFAULT 90",
        "ALTER TABLE ai_configs ADD COLUMN IF NOT EXISTS valid_response_rules jsonb NOT NULL DEFAULT '{\"allow_plain_text_repair\":true,\"reject_repeated_questions\":true,\"require_context_reference\":false,\"require_summary_fields\":true}'::jsonb",
        "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS prompt_tokens integer",
        "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS response_tokens integer",
        "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS tokens_estimated boolean NOT NULL DEFAULT false",
        "CREATE TABLE IF NOT EXISTS skills(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenants(id),name varchar(160) NOT NULL,source_url varchar(1000) NOT NULL,content text NOT NULL,sha256 varchar(64) NOT NULL,scope varchar(20) NOT NULL DEFAULT 'all',active boolean NOT NULL DEFAULT false,created_by uuid NOT NULL REFERENCES users(id),last_test_model varchar(120),last_test_success boolean,last_test_ms integer,last_test_at timestamptz,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant_id,sha256))",
        "CREATE INDEX IF NOT EXISTS users_tenant_area_idx ON users(tenant_id,area_id)",
        "CREATE INDEX IF NOT EXISTS tickets_tenant_area_idx ON tickets(tenant_id,area_id,created_at DESC)",
        "CREATE INDEX IF NOT EXISTS knowledge_documents_tenant_idx ON knowledge_documents(tenant_id,area_id,created_at DESC)",
        "CREATE INDEX IF NOT EXISTS knowledge_chunks_tenant_idx ON knowledge_chunks(tenant_id,document_id)",
        "CREATE INDEX IF NOT EXISTS ticket_status_history_tenant_idx ON ticket_status_history(tenant_id,ticket_id,entered_at)",
        "CREATE INDEX IF NOT EXISTS usage_events_tenant_idx ON usage_events(tenant_id,created_at DESC)",
        "CREATE INDEX IF NOT EXISTS skills_tenant_idx ON skills(tenant_id,created_at DESC)",
        *[f"DROP POLICY IF EXISTS {table}_tenant ON {table}" for table in POLICY_TABLES],
        *[f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" for table in POLICY_TABLES],
        *[f"CREATE POLICY {table}_tenant ON {table} USING(current_setting('app.platform_admin',true)='true' OR tenant_id=current_setting('app.tenant_id',true)::uuid) WITH CHECK(current_setting('app.platform_admin',true)='true' OR tenant_id=current_setting('app.tenant_id',true)::uuid)" for table in POLICY_TABLES],
        *[f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" for table in POLICY_TABLES],
    ]
    connection=await db.connection()
    for statement in statements:await connection.exec_driver_sql(statement)

async def main():
    settings=get_settings()
    async with SessionLocal() as db:
        await ensure_runtime_schema(db);await set_platform_context(db)
        platform=(await db.execute(select(Tenant).where(Tenant.public_slug=="plataforma"))).scalar_one_or_none()
        if not platform:
            platform=Tenant(name="Administração da plataforma",public_slug="plataforma");db.add(platform);await db.flush()
        email=os.getenv("BOOTSTRAP_ADMIN_EMAIL","admin@example.local").strip().lower()
        user=(await db.execute(select(User).where(User.email==email,User.role.in_([Role.admin,Role.platform_admin])))).scalars().first()
        if user:
            manager_copy=None
            if user.role==Role.admin and user.tenant_id!=platform.id:
                original_tenant=user.tenant_id
                if not (await db.execute(select(User).where(User.tenant_id==original_tenant,User.role==Role.company_admin))).scalars().first():
                    manager_copy=(original_tenant,user.email,user.password_hash)
            user.tenant_id=platform.id;user.area_id=None;user.role=Role.platform_admin
            await db.flush()
            if manager_copy:
                db.add(User(tenant_id=manager_copy[0],area_id=None,email=manager_copy[1],name="Administrador da empresa",password_hash=manager_copy[2],role=Role.company_admin))
        else:
            password=os.environ["BOOTSTRAP_ADMIN_PASSWORD"]
            user=User(tenant_id=platform.id,area_id=None,email=email,name="Administrador da plataforma",password_hash=hash_password(password),role=Role.platform_admin);db.add(user)
        await db.flush()
        if not await db.get(AIConfig,platform.id):
            source=(await db.execute(select(AIConfig).join(Tenant,Tenant.id==AIConfig.tenant_id).where(Tenant.public_slug!="plataforma"))).scalars().first()
            if source:db.add(AIConfig(tenant_id=platform.id,provider=source.provider,model=source.model,embedding_model=source.embedding_model,conversation_source=source.conversation_source,embedding_source=source.embedding_source,api_base_url=source.api_base_url,api_key_encrypted=source.api_key_encrypted,context_size=source.context_size,max_tokens=source.max_tokens,temperature=source.temperature,response_timeout_seconds=source.response_timeout_seconds,valid_response_rules=source.valid_response_rules))
            else:db.add(AIConfig(tenant_id=platform.id,provider="ollama",model=settings.default_model,embedding_model="nomic-embed-text",conversation_source="ollama",embedding_source="ollama",context_size=8192,max_tokens=512,temperature="0.2",response_timeout_seconds=90,valid_response_rules={"allow_plain_text_repair":True,"reject_repeated_questions":True,"require_context_reference":False,"require_summary_fields":True}))
        existing_digests=set((await db.execute(select(Skill.sha256).where(Skill.tenant_id==platform.id))).scalars().all())
        legacy_skills=(await db.execute(select(Skill).where(Skill.tenant_id!=platform.id).order_by(Skill.created_at))).scalars().all()
        for source in legacy_skills:
            if source.sha256 not in existing_digests:
                db.add(Skill(tenant_id=platform.id,name=source.name,source_url=source.source_url,content=source.content,sha256=source.sha256,scope=source.scope,active=source.active,created_by=user.id));existing_digests.add(source.sha256)
        await db.commit()

if __name__=="__main__":asyncio.run(main())
