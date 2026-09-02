import pytest
from app import main, ollama
from app.ollama import ask_json, valid_json_contract
from app.security import Principal

@pytest.mark.asyncio
async def test_models_endpoint_returns_entire_ollama_catalog(monkeypatch):
    catalog=[{"name":"ternary-bonsai:8b","size":10},{"name":"rwkv7:7b","size":20},{"name":"nomic-embed-text:latest","size":30}]
    async def fake_models():return catalog
    monkeypatch.setattr(main,"list_models",fake_models)
    result=await main.models(Principal(user_id="u",tenant_id="t",role="admin"))
    assert result["models"]==catalog

def test_json_contract_rejects_wrong_shapes():
    assert valid_json_contract({"action":"question","message":"Qual módulo?"},"intake")
    assert not valid_json_contract({"action":"question","message":"Outra pergunta"},"summary")
    assert valid_json_contract({"action":"summary","message":"Revise","summary":{}},"summary")
    assert not valid_json_contract({"action":"answer","message":""},"support")
    assert not valid_json_contract({"action":"question","message":"Qual módulo apresenta erro?"},"question",["Qual módulo apresenta o erro?"])
    assert valid_json_contract({"action":"question","message":"Quando o erro começou?"},"question",["Qual módulo apresenta o erro?"])

@pytest.mark.asyncio
async def test_invalid_model_output_is_retried_silently(monkeypatch):
    replies=iter(["resposta fora do formato",'{"action":"summary","message":"Revise","summary":{}}'])
    calls=[]
    class FakeResponse:
        status_code=200
        def __init__(self,content):self.content=content
        def json(self):return {"message":{"content":self.content}}
    class FakeClient:
        async def __aenter__(self):return self
        async def __aexit__(self,*_):return None
        async def post(self,*args,**kwargs):calls.append(kwargs);return FakeResponse(next(replies))
    async def no_wait(_):return None
    monkeypatch.setattr(ollama.httpx,"AsyncClient",FakeClient)
    monkeypatch.setattr(ollama.asyncio,"sleep",no_wait)
    result=await ask_json("modelo","sistema",[{"role":"user","content":"gere"}],contract="summary")
    assert result["action"]=="summary"
    assert len(calls)==2
