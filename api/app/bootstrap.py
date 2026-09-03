import asyncio, os
from sqlalchemy import select
from .database import SessionLocal, set_tenant_context
from .models import Tenant, User, Role
from .security import hash_password

async def ensure_runtime_schema(db):
    statements=[
        """CREATE TABLE IF NOT EXISTS knowledge_documents(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenants(id),title varchar(180) NOT NULL,filename varchar(255) NOT NULL,content_type varchar(100) NOT NULL,sha256 varchar(64) NOT NULL,status varchar(20) NOT NULL DEFAULT 'active',uploaded_by uuid NOT NULL REFERENCES users(id),created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant_id,sha256))""",
        """CREATE TABLE IF NOT EXISTS knowledge_chunks(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenants(id),document_id uuid NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,chunk_index integer NOT NULL,content text NOT NULL,UNIQUE(document_id,chunk_index))""",
        """CREATE TABLE IF NOT EXISTS ticket_status_history(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenants(id),ticket_id uuid NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,status varchar(30) NOT NULL,changed_by uuid REFERENCES users(id),entered_at timestamptz NOT NULL DEFAULT now())""",
        """CREATE TABLE IF NOT EXISTS usage_events(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenants(id),event_type varchar(40) NOT NULL,model varchar(120),success boolean NOT NULL DEFAULT true,duration_ms integer,prompt_tokens integer,response_tokens integer,tokens_estimated boolean NOT NULL DEFAULT false,created_at timestamptz NOT NULL DEFAULT now())""",
        "ALTER TABLE ai_configs ADD COLUMN IF NOT EXISTS api_base_url varchar(500)",
        "ALTER TABLE ai_configs ADD COLUMN IF NOT EXISTS api_key_encrypted bytea",
        """DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='ai_configs' AND column_name='conversation_source') THEN ALTER TABLE ai_configs ADD COLUMN conversation_source varchar(20) NOT NULL DEFAULT 'ollama'; UPDATE ai_configs SET conversation_source='external' WHERE provider<>'ollama'; END IF; END $$""",
        "ALTER TABLE ai_configs ADD COLUMN IF NOT EXISTS embedding_source varchar(20) NOT NULL DEFAULT 'ollama'",
        "ALTER TABLE ai_configs ADD COLUMN IF NOT EXISTS response_timeout_seconds integer NOT NULL DEFAULT 90",
        """ALTER TABLE ai_configs ADD COLUMN IF NOT EXISTS valid_response_rules jsonb NOT NULL DEFAULT '{"allow_plain_text_repair":true,"reject_repeated_questions":true,"require_context_reference":false,"require_summary_fields":true}'::jsonb""",
        "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS prompt_tokens integer",
        "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS response_tokens integer",
        "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS tokens_estimated boolean NOT NULL DEFAULT false",
        """CREATE TABLE IF NOT EXISTS skills(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenants(id),name varchar(160) NOT NULL,source_url varchar(1000) NOT NULL,content text NOT NULL,sha256 varchar(64) NOT NULL,scope varchar(20) NOT NULL DEFAULT 'all',active boolean NOT NULL DEFAULT false,created_by uuid NOT NULL REFERENCES users(id),last_test_model varchar(120),last_test_success boolean,last_test_ms integer,last_test_at timestamptz,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant_id,sha256))""",
        "CREATE INDEX IF NOT EXISTS knowledge_documents_tenant_idx ON knowledge_documents(tenant_id,created_at DESC)",
        "CREATE INDEX IF NOT EXISTS knowledge_chunks_tenant_idx ON knowledge_chunks(tenant_id,document_id)",
        "CREATE INDEX IF NOT EXISTS ticket_status_history_tenant_idx ON ticket_status_history(tenant_id,ticket_id,entered_at)",
        "CREATE INDEX IF NOT EXISTS usage_events_tenant_idx ON usage_events(tenant_id,created_at DESC)",
        "CREATE INDEX IF NOT EXISTS skills_tenant_idx ON skills(tenant_id,created_at DESC)",
        "ALTER TABLE knowledge_documents ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE knowledge_documents FORCE ROW LEVEL SECURITY",
        "ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE knowledge_chunks FORCE ROW LEVEL SECURITY",
        "ALTER TABLE ticket_status_history ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE ticket_status_history FORCE ROW LEVEL SECURITY",
        "ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE usage_events FORCE ROW LEVEL SECURITY",
        "ALTER TABLE skills ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE skills FORCE ROW LEVEL SECURITY",
        """DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='knowledge_documents' AND policyname='knowledge_documents_tenant') THEN CREATE POLICY knowledge_documents_tenant ON knowledge_documents USING(tenant_id=current_setting('app.tenant_id',true)::uuid) WITH CHECK(tenant_id=current_setting('app.tenant_id',true)::uuid); END IF; END $$""",
        """DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='knowledge_chunks' AND policyname='knowledge_chunks_tenant') THEN CREATE POLICY knowledge_chunks_tenant ON knowledge_chunks USING(tenant_id=current_setting('app.tenant_id',true)::uuid) WITH CHECK(tenant_id=current_setting('app.tenant_id',true)::uuid); END IF; END $$""",
        """DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='ticket_status_history' AND policyname='ticket_status_history_tenant') THEN CREATE POLICY ticket_status_history_tenant ON ticket_status_history USING(tenant_id=current_setting('app.tenant_id',true)::uuid) WITH CHECK(tenant_id=current_setting('app.tenant_id',true)::uuid); END IF; END $$""",
        """DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='usage_events' AND policyname='usage_events_tenant') THEN CREATE POLICY usage_events_tenant ON usage_events USING(tenant_id=current_setting('app.tenant_id',true)::uuid) WITH CHECK(tenant_id=current_setting('app.tenant_id',true)::uuid); END IF; END $$""",
        """DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='skills' AND policyname='skills_tenant') THEN CREATE POLICY skills_tenant ON skills USING(tenant_id=current_setting('app.tenant_id',true)::uuid) WITH CHECK(tenant_id=current_setting('app.tenant_id',true)::uuid); END IF; END $$""",
    ]
    connection=await db.connection()
    for statement in statements:await connection.exec_driver_sql(statement)

async def main():
    async with SessionLocal() as db:
        await ensure_runtime_schema(db)
        tenant=(await db.execute(select(Tenant).where(Tenant.public_slug=="zoho-suporte"))).scalar_one_or_none()
        if not tenant:
            tenant=Tenant(name="Suporte Zoho",public_slug="zoho-suporte");db.add(tenant);await db.flush()
        await set_tenant_context(db,str(tenant.id))
        email=os.getenv("BOOTSTRAP_ADMIN_EMAIL","admin@example.local").lower();user=(await db.execute(select(User).where(User.tenant_id==tenant.id,User.email==email))).scalar_one_or_none()
        if not user:
            password=os.environ["BOOTSTRAP_ADMIN_PASSWORD"]
            db.add(User(tenant_id=tenant.id,email=email,name="Administrador",password_hash=hash_password(password),role=Role.admin))
        await db.commit()
if __name__=="__main__":asyncio.run(main())
