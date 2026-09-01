from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from .config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with SessionLocal() as session:
        yield session

async def set_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    # SET LOCAL is transaction scoped; RLS reads this value in every query.
    await session.execute(__import__("sqlalchemy").text("select set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_id})
