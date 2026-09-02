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
def valid_json_contract(payload:object,contract:str,forbidden_questions:list[str]|None=None,context_messages:list[str]|None=None)->bool:
    if not isinstance(payload,dict):return False
    action=payload.get("action");message=payload.get("message")
    if not isinstance(message,str) or not message.strip():return False
    if contract=="support":return action in {"answer","offer_ticket"}
    if contract=="summary":return action=="summary" and isinstance(payload.get("summary"),dict)
    if contract=="question":return action=="question" and not question_is_repeated(message,forbidden_questions or []) and question_has_context(message,context_messages or [])
    if contract=="intake":return (action=="question" and not question_is_repeated(message,forbidden_questions or []) and question_has_context(message,context_messages or [])) or (action=="summary" and isinstance(payload.get("summary"),dict))
    return False

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

async def ask_json(model:str,system:str,messages:list[dict],context_size:int=8192,max_tokens:int=512,temperature:float=.2,contract:str="intake",forbidden_questions:list[str]|None=None,context_messages:list[str]|None=None,provider:str="ollama",api_base_url:str|None=None,api_key:str|None=None)->dict:
    safe=[{"role":m["role"],"content":m["content"][:5000]} for m in messages[-16:]]
    external=provider!="ollama";base_url=None
    if external:
        if not api_base_url or not api_key:raise HTTPException(503,"A credencial do provedor externo não está configurada")
        base_url=validate_api_base_url(provider,api_base_url);await ensure_public_destination(base_url)
    deadline=time.monotonic()+90;attempt=0
    async with httpx.AsyncClient() as client:
        while time.monotonic()<deadline:
            attempt+=1;remaining=max(1,deadline-time.monotonic());correction="" if attempt==1 else "\nA resposta anterior não respeitou o contrato. Responda somente com JSON válido e, se for uma pergunta, identifique nela o assunto concreto descrito pelo usuário, sem usar referências vagas."
            try:
                prompt=[{"role":"system","content":system+correction},*safe]
                if external:
                    response=None
                    for request_body in _external_variants(model,prompt,max_tokens,temperature,provider):
                        response=await client.post(f"{base_url}/chat/completions",timeout=min(45,remaining),headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},json=request_body)
                        if response.status_code!=400:break
                    if response is None:raise ValueError("Sem resposta do provedor")
                else:
                    request_body={"model":model,"stream":False,"format":"json","messages":prompt,"options":{"temperature":temperature,"num_ctx":context_size,"num_predict":max_tokens}}
                    response=await client.post(f"{get_settings().ollama_url}/api/chat",timeout=min(45,remaining),json=request_body)
                    if response.status_code==400:
                        fallback_body={key:value for key,value in request_body.items() if key!="format"};response=await client.post(f"{get_settings().ollama_url}/api/chat",timeout=min(45,remaining),json=fallback_body)
                if 400<=response.status_code<500 and response.status_code not in {408,429}:raise HTTPException(502,"O provedor de IA recusou a requisição")
                if response.status_code>=500 or response.status_code in {408,429}:raise httpx.HTTPStatusError("Falha temporária",request=response.request,response=response)
                body=response.json();content=body.get("choices",[{}])[0].get("message",{}).get("content","") if external else body.get("message",{}).get("content","");payload=parse_json_content(content)
                if valid_json_contract(payload,contract,forbidden_questions,context_messages):return payload
            except HTTPException:raise
            except (httpx.HTTPError,AttributeError,KeyError,TypeError,ValueError,json.JSONDecodeError):pass
            if time.monotonic()<deadline:await asyncio.sleep(min(1.5*attempt,5))
    raise HTTPException(504,"O modelo demorou mais que o esperado para gerar uma resposta válida")
