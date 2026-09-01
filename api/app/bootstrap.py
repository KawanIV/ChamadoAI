import asyncio, os
from sqlalchemy import select
from .database import SessionLocal, set_tenant_context
from .models import Tenant, User, Role
from .security import hash_password

async def main():
    async with SessionLocal() as db:
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
