import pytest
from app import main
from app.security import Principal

@pytest.mark.asyncio
async def test_models_endpoint_returns_entire_ollama_catalog(monkeypatch):
    catalog=[{"name":"ternary-bonsai:8b","size":10},{"name":"rwkv7:7b","size":20},{"name":"nomic-embed-text:latest","size":30}]
    async def fake_models():return catalog
    monkeypatch.setattr(main,"list_models",fake_models)
    result=await main.models(Principal(user_id="u",tenant_id="t",role="admin"))
    assert result["models"]==catalog
