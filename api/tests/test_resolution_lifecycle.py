import uuid
from datetime import datetime, timezone

from app.main import serialize_ticket
from app.models import Resolution, Ticket, TicketStatus


def test_closed_ticket_serialization_preserves_approved_resolution():
    tenant_id=uuid.uuid4();ticket_id=uuid.uuid4()
    ticket=Ticket(id=ticket_id,tenant_id=tenant_id,protocol=42,requester_name="Valdir",department="Operações",contact=None,title="Acesso ao Zoho Sign",summary="Usuário sem acesso",product="Zoho Sign",priority="high",status=TicketStatus.closed,public_token_hash="a"*64,created_at=datetime(2026,9,2,tzinfo=timezone.utc))
    resolution=Resolution(id=uuid.uuid4(),tenant_id=tenant_id,ticket_id=ticket_id,confirmed_problem="Conta sem acesso ao Zoho Sign",root_cause="Perfil sem permissão",solution="Permissão adicionada ao perfil",validation="Acesso confirmado pelo solicitante",reusable=True,sanitized_document={"solution":"Permissão adicionada ao perfil"})

    payload=serialize_ticket(ticket,[],resolution)

    assert payload["status"]=="closed"
    assert payload["resolution"]["solution"]=="Permissão adicionada ao perfil"
    assert payload["resolution"]["reusable"] is True
