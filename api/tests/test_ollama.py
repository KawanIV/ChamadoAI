import json
import uuid
import pytest
from app import main, ollama
from app.ollama import ask_json, contract_error, first_valid_question, model_supports_chat, parse_json_content, parse_labeled_summary, parse_model_response, response_usage, sanitize_model_payload, valid_json_contract, visible_model_content
from app.ai_provider import validate_api_base_url
from app.schemas import AIConfigIn, PublicChatIn
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
    assert valid_json_contract({"action":"summary","message":"Revise","summary":{"title":"Falha ao salvar no Zoho CRM","description":"O Zoho CRM não salva a proposta após o envio. A operação permanece pendente para o solicitante.","product":"Zoho CRM","priority":"normal"}},"summary")
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
    assert contract_error({"action":"question","message":"Qual é a sua senha?"},"question")=="a pergunta solicita informação sensível"
    assert contract_error({"action":"question","message":"Tente limpar o cache e me diga se funcionou?"},"question")=="a triagem não deve diagnosticar nem sugerir solução"

def test_backend_formats_plain_model_question_and_labeled_summary():
    question=parse_model_response("Quando você tenta acessar o Zoho Sign, aparece algum erro?","question")
    assert question=={"action":"question","message":"Quando você tenta acessar o Zoho Sign, aparece algum erro?"}
    summary=parse_labeled_summary("Título: Sem acesso ao Sign\nDescrição: Usuário não acessa o Zoho Sign\nProduto: Zoho Sign\nPrioridade: Alta\nContato:")
    assert summary["summary"]["title"]=="Sem acesso ao Sign"
    assert summary["summary"]["priority"]=="high"

def test_backend_salvages_first_valid_question_from_verbose_small_model_output():
    raw="<think>análise privada</think>Entendi o problema no Zoho Sign. Qual mensagem aparece ao tentar abrir o Zoho Sign? Quando começou?"
    result=first_valid_question(raw,context_messages=["Estou sem acesso ao Zoho Sign"],rules={"require_context_reference":True})
    assert result=="Entendi o problema no Zoho Sign. Qual mensagem aparece ao tentar abrir o Zoho Sign?"
    assert result.count("?")==1

def test_provider_usage_prefers_exact_token_counts_and_marks_estimates():
    exact=response_usage({"eval_count":37,"prompt_eval_count":112},"Resposta",False)
    assert exact=={"response_tokens":37,"prompt_tokens":112,"tokens_estimated":False}
    estimated=response_usage({},"Resposta curta",False)
    assert estimated["response_tokens"]>0
    assert estimated["tokens_estimated"] is True

def test_chat_schema_tolerates_display_metrics_from_cached_clients():
    payload=PublicChatIn(public_context="contexto",messages=[{"role":"assistant","content":"Pergunta 1: Qual erro aparece?","duration_ms":1200,"response_tokens":8,"tokens_estimated":False}])
    assert payload.messages[0]["content"].startswith("Pergunta 1")

@pytest.mark.asyncio
async def test_ollama_stream_reports_live_token_progress():
    events=[]
    class FakeResponse:
        status_code=200
        request=None
        async def __aenter__(self):return self
        async def __aexit__(self,*_):return None
        async def aiter_lines(self):
            for chunk in [
                {"message":{"thinking":"análise interna"}},
                {"message":{"content":"Pergunta final"}},
                {"message":{"content":"?"},"eval_count":9,"done":True},
            ]:yield json.dumps(chunk)
    class FakeClient:
        def stream(self,*args,**kwargs):return FakeResponse()
    async def progress(event):events.append(event)
    body,content=await ollama._stream_ollama(FakeClient(),"http://ollama/api/chat",{"model":"teste"},30,progress)
    assert content=="Pergunta final?"
    assert body["eval_count"]==9
    assert any(event["tokens_estimated"] for event in events[:-1])
    assert events[-1]=={"response_tokens":9,"tokens_estimated":False}

@pytest.mark.asyncio
async def test_delivered_response_persists_time_and_token_usage(monkeypatch):
    class FakeDb:
        def __init__(self):self.added=[];self.commits=0
        def add(self,item):self.added.append(item)
        async def commit(self):self.commits+=1
    async def fake_ask(*args,**kwargs):
        return {"action":"question","message":"Qual erro aparece?","_provider_usage":{"prompt_tokens":41,"response_tokens":9,"tokens_estimated":False,"attempts":1}}
    monkeypatch.setattr(main,"ask_json",fake_ask)
    db=FakeDb();result=await main.tracked_ask(db,uuid.uuid4(),"modelo","sistema",[])
    llm_event=next(item for item in db.added if item.event_type=="llm_request")
    assert llm_event.duration_ms>=0
    assert llm_event.prompt_tokens==41
    assert llm_event.response_tokens==9
    assert llm_event.tokens_estimated is False
    assert result["_metrics"]["response_tokens"]==9
    assert db.commits==1

@pytest.mark.asyncio
async def test_compact_question_uses_only_one_model_attempt(monkeypatch):
    calls=[]
    class FakeResponse:
        status_code=200
        def json(self):return {"message":{"content":"Qual erro aparece? Quando começou?"}}
    class FakeClient:
        async def __aenter__(self):return self
        async def __aexit__(self,*_):return None
        async def post(self,*args,**kwargs):calls.append(kwargs);return FakeResponse()
    monkeypatch.setattr(ollama.httpx,"AsyncClient",FakeClient)
    result=await ask_json("modelo","sistema",[{"role":"user","content":"Zoho Sign sem acesso"}],contract="question",max_attempts=1)
    assert result["message"]=="Qual erro aparece?"
    assert result["_provider_usage"]["response_tokens"]>0
    assert len(calls)==1

def test_embedding_only_model_cannot_be_used_as_chat_model():
    assert not model_supports_chat({"embedding"})
    assert model_supports_chat({"completion","tools"})
    assert model_supports_chat(set())

@pytest.mark.asyncio
async def test_invalid_model_output_is_retried_silently(monkeypatch):
    replies=iter(["<think>somente raciocínio, sem resposta final</think>","Título: Falha no CRM\nDescrição: O CRM não salva a proposta\nProduto: Zoho CRM\nPrioridade: Normal\nContato:"])
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
async def test_ollama_model_without_native_json_mode_uses_plain_text(monkeypatch):
    calls=[]
    class FakeResponse:
        def __init__(self,status_code,content):self.status_code=status_code;self.content=content
        def json(self):return {"message":{"content":self.content}}
    class FakeClient:
        async def __aenter__(self):return self
        async def __aexit__(self,*_):return None
        async def post(self,*args,**kwargs):calls.append(kwargs["json"]);return FakeResponse(200,"Orientação compatível")
    monkeypatch.setattr(ollama.httpx,"AsyncClient",FakeClient)
    result=await ask_json("modelo-sem-json","sistema",[{"role":"user","content":"ajuda"}],contract="support")
    assert result["message"]=="Orientação compatível"
    assert len(calls)==1
    assert "format" not in calls[0]

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
    assert "response_format" not in calls[0][1]["json"]
