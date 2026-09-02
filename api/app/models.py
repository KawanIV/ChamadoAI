import enum, uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase): pass
class Role(str, enum.Enum): admin="admin"; agent="agent"
class TicketStatus(str, enum.Enum): new="new"; analysis="analysis"; working="working"; waiting="waiting"; validation="validation"; resolved="resolved"; cancelled="cancelled"
role_column_type = Enum(Role, native_enum=False, validate_strings=True, length=20)
ticket_status_column_type = Enum(TicketStatus, native_enum=False, validate_strings=True, length=30)
class Tenant(Base):
    __tablename__="tenants"; id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); name:Mapped[str]=mapped_column(String(120)); public_slug:Mapped[str]=mapped_column(String(80),unique=True,index=True); active:Mapped[bool]=mapped_column(Boolean,default=True)
class User(Base):
    __tablename__="users"; id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); tenant_id:Mapped[uuid.UUID]=mapped_column(ForeignKey("tenants.id"),index=True); email:Mapped[str]=mapped_column(String(254)); name:Mapped[str]=mapped_column(String(120)); password_hash:Mapped[str]=mapped_column(Text); role:Mapped[Role]=mapped_column(role_column_type); active:Mapped[bool]=mapped_column(Boolean,default=True)
class Ticket(Base):
    __tablename__="tickets"; id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); tenant_id:Mapped[uuid.UUID]=mapped_column(ForeignKey("tenants.id"),index=True); protocol:Mapped[int]=mapped_column(index=True); requester_name:Mapped[str]=mapped_column(String(120)); department:Mapped[str]=mapped_column(String(120)); contact:Mapped[str|None]=mapped_column(String(254),nullable=True); title:Mapped[str]=mapped_column(String(180)); summary:Mapped[str]=mapped_column(Text); product:Mapped[str]=mapped_column(String(80)); priority:Mapped[str]=mapped_column(String(20),default="normal"); status:Mapped[TicketStatus]=mapped_column(ticket_status_column_type,default=TicketStatus.new); public_token_hash:Mapped[str]=mapped_column(String(64)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class Resolution(Base):
    __tablename__="resolutions"; id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); tenant_id:Mapped[uuid.UUID]=mapped_column(ForeignKey("tenants.id"),index=True); ticket_id:Mapped[uuid.UUID]=mapped_column(ForeignKey("tickets.id"),unique=True); confirmed_problem:Mapped[str]=mapped_column(Text); root_cause:Mapped[str]=mapped_column(Text); solution:Mapped[str]=mapped_column(Text); validation:Mapped[str]=mapped_column(Text); reusable:Mapped[bool]=mapped_column(Boolean,default=False); sanitized_document:Mapped[dict|None]=mapped_column(JSONB,nullable=True)
class AIConfig(Base):
    __tablename__="ai_configs"; tenant_id:Mapped[uuid.UUID]=mapped_column(ForeignKey("tenants.id"),primary_key=True); provider:Mapped[str]=mapped_column(String(30),default="ollama"); model:Mapped[str]=mapped_column(String(120)); embedding_model:Mapped[str]=mapped_column(String(120)); context_size:Mapped[int]=mapped_column(default=8192); max_tokens:Mapped[int]=mapped_column(default=512); temperature:Mapped[str]=mapped_column(String(8),default="0.2")
