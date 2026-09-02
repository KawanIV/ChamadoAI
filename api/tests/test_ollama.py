import pytest
from app import main, ollama
from app.ollama import ask_json, contract_error, model_supports_chat, parse_json_content, sanitize_model_payload, valid_json_contract, visible_model_content
from app.ai_provider import validate_api_base_url
from app.schemas import AIConfigIn
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
    assert valid_json_contract({"action":"summary","message":"Revise","summary":{"description":"CRM não salva a proposta"}},"summary")
    assert not valid_json_contract({"action":"answer","message":""},"support")
    assert not valid_json_contract({"action":"question","message":"Qual módulo apresenta erro?"},"question",["Qual módulo apresenta o erro?"])
    assert valid_json_contract({"action":"question","message":"Quando o erro começou?"},"question",["Qual módulo apresenta o erro?"])
    strict={"require_context_reference":True}
    assert not valid_json_contract({"action":"question","message":"Quando isso acontece?"},"question",context_messages=["O CRM não salva a proposta"],rules=strict)
    assert valid_json_contract({"action":"question","message":"Quando o CRM deixa de salvar a proposta?"},"question",context_messages=["O CRM não salva a proposta"],rules=strict)

def test_json_parser_accepts_code_fences_and_explanatory_prefixes():
    assert parse_json_content('```json\n{"action":"answer","message":"Ok"}\n```')["action"]=="answer"
    assert parse_json_content('Resposta: {"action":"answer","message":"Ok"}')["message"]=="Ok"

def test_reasoning_tags_never_reach_the_visible_model_response():
    result=parse_json_content('<think>raciocínio privado</think>{"action":"answer","message":"Resposta final"}')
    assert result["message"]=="Resposta final"
    encoded=sanitize_model_payload({"action":"answer","message":"<thinking>não exibir</thinking>Ação recomendada","reasoning_content":"segredo"})
    assert encoded=={"action":"answer","message":"Ação recomendada"}

def test_structured_reasoning_blocks_are_ignored():
    content=[{"type":"reasoning","text":"cadeia interna"},{"type":"text","text":'{"action":"answer","message":"Somente resposta"}'}]
    assert parse_json_content(content)["message"]=="Somente resposta"
    assert visible_model_content('</think>Resposta após marcador incompleto')=="Resposta após marcador incompleto"

def test_conversation_sample_strips_unclosed_reasoning_and_rejects_question_lists():
    raw='O usuário está sem acesso e devo analisar opções internas. </think> Olá Valdir. Por favor, descreva:\n- Quem é o usuário?\n- O que está tentando fazer?\n- Quando isso acontece?'
    visible=visible_model_content(raw)
    assert "devo analisar" not in visible
    assert visible.startswith("Olá Valdir")
    error=contract_error({"action":"question","message":visible},"question",context_messages=["Estou sem acesso ao Zoho Sign"])
    assert error=="a resposta deve conter exatamente uma pergunta"

def test_question_contract_accepts_one_contextual_question_and_blocks_fixed_identity():
    valid="Quando você tenta acessar o Zoho Sign, aparece alguma mensagem de erro ou a tela não carrega?"
    assert contract_error({"action":"question","message":valid},"question",context_messages=["Estou sem acesso ao Zoho Sign"]) is None
    assert contract_error({"action":"question","message":"Qual é o seu nome?"},"question")=="nome e setor já são coletados nos campos fixos"

def test_embedding_only_model_cannot_be_used_as_chat_model():
    assert not model_supports_chat({"embedding"})
    assert model_supports_chat({"completion","tools"})
    assert model_supports_chat(set())

@pytest.mark.asyncio
async def test_invalid_model_output_is_retried_silently(monkeypatch):
    replies=iter(["resposta fora do formato",'{"action":"summary","message":"Revise","summary":{"description":"Falha ao salvar no CRM"}}'])
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

@pytest.mark.asyncio
async def test_ollama_model_without_native_json_mode_uses_compatible_fallback(monkeypatch):
    calls=[]
    class FakeResponse:
        def __init__(self,status_code,content):self.status_code=status_code;self.content=content
        def json(self):return {"message":{"content":self.content}}
    class FakeClient:
        async def __aenter__(self):return self
        async def __aexit__(self,*_):return None
        async def post(self,*args,**kwargs):
            calls.append(kwargs["json"])
            return FakeResponse(400,"") if len(calls)==1 else FakeResponse(200,'```json\n{"action":"answer","message":"Compatível"}\n```')
    monkeypatch.setattr(ollama.httpx,"AsyncClient",FakeClient)
    result=await ask_json("modelo-sem-json","sistema",[{"role":"user","content":"ajuda"}],contract="support")
    assert result["message"]=="Compatível"
    assert calls[0]["format"]=="json"
    assert "format" not in calls[1]

def test_external_provider_urls_block_ssrf_and_embedded_credentials():
    assert validate_api_base_url("openai","https://api.openai.com/v1/")=="https://api.openai.com/v1"
    assert validate_api_base_url("custom","https://llm.example.com/openai/v1")=="https://llm.example.com/openai/v1"
    for provider,url in [("custom","http://llm.example.com/v1"),("custom","https://127.0.0.1/v1"),("custom","https://user:secret@llm.example.com/v1"),("custom","https://llm.example.com/v1?token=secret"),("openai","https://proxy.example.com/v1")]:
        with pytest.raises(Exception):validate_api_base_url(provider,url)

def test_api_secret_uses_pydantic_secret_type():
    config=AIConfigIn(provider="openai",model="modelo",api_base_url="https://api.openai.com/v1",api_key="segredo-completo",context_size=8192,max_tokens=512,temperature=.2)
    assert "segredo-completo" not in repr(config)
    assert config.api_key.get_secret_value()=="segredo-completo"

@pytest.mark.asyncio
async def test_external_provider_uses_bearer_secret_without_ollama_payload(monkeypatch):
    calls=[]
    class FakeResponse:
        status_code=200
        def json(self):return {"choices":[{"message":{"content":'{"action":"answer","message":"Orientação segura"}'}}]}
    class FakeClient:
        async def __aenter__(self):return self
        async def __aexit__(self,*_):return None
        async def post(self,url,**kwargs):calls.append((url,kwargs));return FakeResponse()
    async def public_destination(_):return None
    monkeypatch.setattr(ollama.httpx,"AsyncClient",FakeClient)
    monkeypatch.setattr(ollama,"ensure_public_destination",public_destination)
    result=await ask_json("modelo-api","sistema",[{"role":"user","content":"ajuda"}],contract="support",provider="custom",api_base_url="https://llm.example.com/v1",api_key="segredo-api")
    assert result["message"]=="Orientação segura"
    assert calls[0][0]=="https://llm.example.com/v1/chat/completions"
    assert calls[0][1]["headers"]["Authorization"]=="Bearer segredo-api"
    assert "options" not in calls[0][1]["json"]
