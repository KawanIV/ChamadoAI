import asyncio, json, time
import httpx
from fastapi import HTTPException
from .config import get_settings
from .assistant import question_has_context, question_is_repeated
from .ai_provider import ensure_public_destination, validate_api_base_url

async def list_models()->list[dict]:
    async with httpx.AsyncClient(timeout=8) as client:
        response=await client.get(f"{get_settings().ollama_url}/api/tags");response.raise_for_status();return response.json().get("models",[])

async def model_capabilities(model:str)->set[str]:
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response=await client.post(f"{get_settings().ollama_url}/api/show",json={"model":model});response.raise_for_status();details=response.json()
    except (httpx.HTTPError,AttributeError,TypeError,ValueError):
        return set()
    capabilities=details.get("capabilities",[])
    return {str(value) for value in capabilities} if isinstance(capabilities,list) else set()

def model_supports_chat(capabilities:set[str])->bool:
    return not capabilities or "completion" in capabilities
DEFAULT_RULES={"allow_plain_text_repair":True,"reject_repeated_questions":True,"require_context_reference":False,"require_summary_fields":True}
def contract_error(payload:object,contract:str,forbidden_questions:list[str]|None=None,context_messages:list[str]|None=None,rules:dict|None=None)->str|None:
    applied={**DEFAULT_RULES,**(rules or {})}
    if not isinstance(payload,dict):return "formato JSON inválido"
    action=payload.get("action");message=payload.get("message")
    if not isinstance(message,str) or not message.strip():return "mensagem vazia"
    if contract=="support":return None if action in {"answer","offer_ticket"} else "ação de suporte inválida"
    if contract=="summary":
        summary=payload.get("summary")
        if action!="summary" or not isinstance(summary,dict):return "resumo fora do contrato"
        if applied["require_summary_fields"] and not str(summary.get("description","")).strip():return "resumo sem descrição"
        return None
    if contract in {"question","intake"}:
        if action=="summary" and contract=="intake" and isinstance(payload.get("summary"),dict):return None
        if action!="question":return "ação de pergunta inválida"
        if applied["reject_repeated_questions"] and question_is_repeated(message,forbidden_questions or []):return "pergunta repetida"
        if applied["require_context_reference"] and not question_has_context(message,context_messages or []):return "pergunta sem referência ao contexto"
        return None
    return "contrato desconhecido"

def valid_json_contract(payload:object,contract:str,forbidden_questions:list[str]|None=None,context_messages:list[str]|None=None,rules:dict|None=None)->bool:
    return contract_error(payload,contract,forbidden_questions,context_messages,rules) is None

def parse_json_content(content:object)->object:
    if isinstance(content,list):content="".join(str(item.get("text", "")) if isinstance(item,dict) else str(item) for item in content)
    if not isinstance(content,str):raise ValueError("Conteúdo do modelo inválido")
    value=content.strip()
    if value.startswith("```"):
        value=value.split("\n",1)[1] if "\n" in value else value[3:]
        if value.rstrip().endswith("```"):value=value.rstrip()[:-3]
        value=value.strip()
    try:return json.loads(value)
    except json.JSONDecodeError:
        start=value.find("{")
        if start<0:raise
        payload,_=json.JSONDecoder().raw_decode(value[start:])
        return payload

def _external_variants(model:str,prompt:list[dict],max_tokens:int,temperature:float,provider:str)->list[dict]:
    token_keys=["max_completion_tokens","max_tokens"] if provider=="openai" else ["max_tokens","max_completion_tokens"]
    variants=[]
    for token_key in token_keys:
        base={"model":model,"messages":prompt,"temperature":temperature,token_key:max_tokens}
        variants.append({**base,"response_format":{"type":"json_object"}})
        variants.append(base)
        variants.append({key:value for key,value in base.items() if key!="temperature"})
    return variants

async def ask_json(model:str,system:str,messages:list[dict],context_size:int=8192,max_tokens:int=512,temperature:float=.2,contract:str="intake",forbidden_questions:list[str]|None=None,context_messages:list[str]|None=None,provider:str="ollama",api_base_url:str|None=None,api_key:str|None=None,timeout_seconds:int=90,rules:dict|None=None)->dict:
    safe=[{"role":m["role"],"content":m["content"][:5000]} for m in messages[-16:]]
    external=provider!="ollama";base_url=None
    if external:
        if not api_base_url or not api_key:raise HTTPException(503,"A credencial do provedor externo não está configurada")
        base_url=validate_api_base_url(provider,api_base_url);await ensure_public_destination(base_url)
    applied={**DEFAULT_RULES,**(rules or {})};deadline=time.monotonic()+max(15,min(timeout_seconds,300));attempt=0;last_reason="tempo de resposta excedido"
    async with httpx.AsyncClient() as client:
        while time.monotonic()<deadline:
            attempt+=1;remaining=max(1,deadline-time.monotonic());request_timeout=min(remaining,max(15,min(120,timeout_seconds*.7)));correction="" if attempt==1 else "\nA resposta anterior não respeitou o contrato. Responda somente com JSON válido e, se for uma pergunta, identifique nela o assunto concreto descrito pelo usuário, sem usar referências vagas."
            try:
                prompt=[{"role":"system","content":system+correction},*safe]
                if external:
                    response=None
                    for request_body in _external_variants(model,prompt,max_tokens,temperature,provider):
                        response=await client.post(f"{base_url}/chat/completions",timeout=request_timeout,headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},json=request_body)
                        if response.status_code!=400:break
                    if response is None:raise ValueError("Sem resposta do provedor")
                else:
                    request_body={"model":model,"stream":False,"format":"json","messages":prompt,"options":{"temperature":temperature,"num_ctx":context_size,"num_predict":max_tokens}}
                    response=await client.post(f"{get_settings().ollama_url}/api/chat",timeout=request_timeout,json=request_body)
                    if response.status_code==400:
                        fallback_body={key:value for key,value in request_body.items() if key!="format"};response=await client.post(f"{get_settings().ollama_url}/api/chat",timeout=request_timeout,json=fallback_body)
                if 400<=response.status_code<500 and response.status_code not in {408,429}:raise HTTPException(502,"O provedor de IA recusou a requisição")
                if response.status_code>=500 or response.status_code in {408,429}:raise httpx.HTTPStatusError("Falha temporária",request=response.request,response=response)
                body=response.json();content=body.get("choices",[{}])[0].get("message",{}).get("content","") if external else body.get("message",{}).get("content","")
                try:payload=parse_json_content(content)
                except (ValueError,json.JSONDecodeError):
                    if applied["allow_plain_text_repair"] and isinstance(content,str) and content.strip() and contract in {"support","question","intake"}:payload={"action":"answer" if contract=="support" else "question","message":content.strip()}
                    else:raise
                last_reason=contract_error(payload,contract,forbidden_questions,context_messages,applied) or ""
                if not last_reason:return payload
            except HTTPException:raise
            except httpx.TimeoutException:last_reason="tempo de geração excedido"
            except httpx.HTTPError:last_reason="falha temporária de comunicação com o provedor"
            except (ValueError,json.JSONDecodeError):last_reason="formato JSON inválido"
            except (AttributeError,KeyError,TypeError):last_reason="resposta incompleta do provedor"
            if time.monotonic()<deadline:await asyncio.sleep(min(1.5*attempt,5))
    raise HTTPException(504,f"O modelo não entregou uma resposta válida dentro do limite: {last_reason}")
