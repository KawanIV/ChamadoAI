import asyncio, json, re, time, unicodedata
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
def question_shape_error(message:str)->str|None:
    value=message.strip()
    if len(value)>700:return "pergunta longa demais"
    if value.count("?")!=1:return "a resposta deve conter exatamente uma pergunta"
    if re.search(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+",value):return "a resposta não pode usar lista de perguntas"
    normalized="".join(character for character in unicodedata.normalize("NFKD",value.lower()) if not unicodedata.combining(character))
    identity_patterns=(r"\bquem e o usuario\b",r"\bqual (?:e )?o seu nome\b",r"\binforme (?:o )?seu nome\b",r"\bqual (?:e )?o seu setor\b",r"\binforme (?:o )?seu setor\b",r"\bnome e setor\b")
    if any(re.search(pattern,normalized) for pattern in identity_patterns):return "nome e setor já são coletados nos campos fixos"
    sensitive_patterns=(r"\bqual (?:e )?a sua senha\b",r"\binforme (?:a )?senha\b",r"\benvie (?:o )?token\b",r"\bcodigo de autenticacao\b",r"\bchave de api\b")
    if any(re.search(pattern,normalized) for pattern in sensitive_patterns):return "a pergunta solicita informação sensível"
    advice_patterns=(r"\btente (?:reiniciar|limpar|reinstalar|alterar|trocar)\b",r"\breinicie\b",r"\blimpe (?:o )?cache\b",r"\bredefina (?:a )?senha\b",r"\bprovavelmente (?:e|a causa)\b")
    if any(re.search(pattern,normalized) for pattern in advice_patterns):return "a triagem não deve diagnosticar nem sugerir solução"
    return None

def contract_error(payload:object,contract:str,forbidden_questions:list[str]|None=None,context_messages:list[str]|None=None,rules:dict|None=None)->str|None:
    applied={**DEFAULT_RULES,**(rules or {})}
    if not isinstance(payload,dict):return "formato JSON inválido"
    action=payload.get("action");message=payload.get("message")
    if not isinstance(message,str) or not message.strip():return "mensagem vazia"
    if contract=="support":return None if action in {"answer","offer_ticket"} else "ação de suporte inválida"
    if contract=="summary":
        summary=payload.get("summary")
        if action!="summary" or not isinstance(summary,dict):return "resumo fora do contrato"
        if applied["require_summary_fields"]:
            missing=[field for field in ("title","description","product","priority") if not str(summary.get(field,"")).strip()]
            if missing:return "resumo sem os campos obrigatórios: "+", ".join(missing)
        return None
    if contract in {"question","intake"}:
        if action=="summary" and contract=="intake" and isinstance(payload.get("summary"),dict):return None
        if action!="question":return "ação de pergunta inválida"
        shape_error=question_shape_error(message)
        if shape_error:return shape_error
        if applied["reject_repeated_questions"] and question_is_repeated(message,forbidden_questions or []):return "pergunta repetida"
        if applied["require_context_reference"] and not question_has_context(message,context_messages or []):return "pergunta sem referência ao contexto"
        return None
    return "contrato desconhecido"

def valid_json_contract(payload:object,contract:str,forbidden_questions:list[str]|None=None,context_messages:list[str]|None=None,rules:dict|None=None)->bool:
    return contract_error(payload,contract,forbidden_questions,context_messages,rules) is None

_REASONING_BLOCK=re.compile(r"<(think|thinking|reasoning|analysis)\b[^>]*>.*?</\1\s*>",re.IGNORECASE|re.DOTALL)
_REASONING_OPEN=re.compile(r"<(think|thinking|reasoning|analysis)\b[^>]*>",re.IGNORECASE)
_REASONING_CLOSE=re.compile(r"</(think|thinking|reasoning|analysis)\s*>",re.IGNORECASE)

def visible_model_content(content:object)->str:
    """Return only user-visible model output, excluding chain-of-thought blocks."""
    if isinstance(content,list):
        parts=[]
        for item in content:
            if isinstance(item,dict):
                item_type=str(item.get("type","")).lower()
                if any(marker in item_type for marker in ("reasoning","thinking","analysis")):continue
                value=item.get("text","")
                if isinstance(value,dict):value=value.get("value","")
                if isinstance(value,str):parts.append(value)
            elif isinstance(item,str):parts.append(item)
        content="".join(parts)
    if not isinstance(content,str):raise ValueError("Conteúdo do modelo inválido")
    value=content
    while _REASONING_BLOCK.search(value):value=_REASONING_BLOCK.sub("",value)
    closing=list(_REASONING_CLOSE.finditer(value))
    if closing and not _REASONING_OPEN.search(value):value=value[closing[-1].end():]
    opening=_REASONING_OPEN.search(value)
    if opening:value=value[:opening.start()]
    return value.strip()

def sanitize_model_payload(payload:object)->object:
    if not isinstance(payload,dict):return payload
    cleaned=dict(payload)
    if isinstance(cleaned.get("message"),str):cleaned["message"]=visible_model_content(cleaned["message"])
    summary=cleaned.get("summary")
    if isinstance(summary,dict):cleaned["summary"]={key:visible_model_content(value) if isinstance(value,str) else value for key,value in summary.items()}
    cleaned.pop("think",None);cleaned.pop("thinking",None);cleaned.pop("reasoning",None);cleaned.pop("reasoning_content",None)
    return cleaned

def parse_json_content(content:object)->object:
    value=visible_model_content(content)
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

def parse_labeled_summary(content:object)->dict:
    value=visible_model_content(content)
    labels={"titulo":"title","descricao":"description","produto":"product","prioridade":"priority","contato":"contact"};fields={key:"" for key in labels.values()}
    matches=list(re.finditer(r"(?im)^\s*(?:[-*]\s*)?(Título|Descrição|Produto|Prioridade|Contato)\s*:\s*",value))
    for index,match in enumerate(matches):
        normalized="".join(character for character in unicodedata.normalize("NFKD",match.group(1).lower()) if not unicodedata.combining(character));end=matches[index+1].start() if index+1<len(matches) else len(value);fields[labels[normalized]]=value[match.end():end].strip()
    if not fields["description"]:fields["description"]=value[:5000]
    priority=fields["priority"].lower();fields["priority"]="high" if priority in {"alta","high"} else "low" if priority in {"baixa","low"} else "normal"
    return {"action":"summary","message":"Revise o resumo antes de enviar.","summary":fields}

def parse_model_response(content:object,contract:str,allow_plain_text:bool=True)->object:
    try:return sanitize_model_payload(parse_json_content(content))
    except (ValueError,json.JSONDecodeError):
        if not allow_plain_text:raise
        value=visible_model_content(content)
        if not value:raise ValueError("Resposta final vazia")
        if contract=="summary":return parse_labeled_summary(value)
        if contract in {"question","intake"}:return {"action":"question","message":value}
        if contract=="support":
            action="offer_ticket" if re.search(r"(?i)\b(?:abrir|encaminhar|registrar)\s+(?:um\s+)?chamado\b",value) else "answer"
            return {"action":action,"message":value}
        raise

def first_valid_question(value:object,forbidden_questions:list[str]|None=None,context_messages:list[str]|None=None,rules:dict|None=None)->str|None:
    """Salvage one usable question from verbose output produced by small models."""
    try:visible=visible_model_content(value)
    except ValueError:return None
    applied={**DEFAULT_RULES,**(rules or {})}
    for match in re.finditer(r"(?:^|[\n.!])\s*(?:[-*•]|\d+[.)])?\s*([^?\n]{3,500}\?)",visible):
        candidate=re.sub(r"\s+"," ",match.group(1)).strip()
        payload={"action":"question","message":candidate}
        if contract_error(payload,"question",forbidden_questions,context_messages,applied) is None:return candidate
    return None

def repair_question_payload(payload:object,raw_content:object,forbidden_questions:list[str]|None=None,context_messages:list[str]|None=None,rules:dict|None=None)->object:
    if isinstance(payload,dict) and contract_error(payload,"question",forbidden_questions,context_messages,rules) is None:return payload
    candidate=first_valid_question(raw_content,forbidden_questions,context_messages,rules)
    return {"action":"question","message":candidate} if candidate else payload

def response_usage(body:dict,content:object,external:bool)->dict:
    usage=body.get("usage",{}) if external else body
    response_tokens=usage.get("completion_tokens") if external else usage.get("eval_count")
    prompt_tokens=usage.get("prompt_tokens") if external else usage.get("prompt_eval_count")
    estimated=False
    if not isinstance(response_tokens,int):
        visible=visible_model_content(content)
        response_tokens=max(1,round(len(visible)/4)) if visible else 0
        estimated=True
    return {"response_tokens":response_tokens,"prompt_tokens":prompt_tokens if isinstance(prompt_tokens,int) else None,"tokens_estimated":estimated}

def _stream_piece(value:object)->str:
    if isinstance(value,str):return value
    if isinstance(value,list):
        return "".join(str(item.get("text",item.get("content",""))) for item in value if isinstance(item,dict) and str(item.get("type","text")).lower() not in {"reasoning","thinking","analysis"})
    return ""

async def _notify_progress(callback,generated_text:str,exact_tokens:int|None=None)->None:
    if callback is None:return
    estimated=not isinstance(exact_tokens,int)
    tokens=exact_tokens if not estimated else (max(1,round(len(generated_text)/4)) if generated_text else 0)
    await callback({"response_tokens":tokens,"tokens_estimated":estimated})

def _check_stream_status(response)->None:
    if 400<=response.status_code<500 and response.status_code not in {408,429}:raise HTTPException(502,"O provedor de IA recusou a requisição")
    if response.status_code>=500 or response.status_code in {408,429}:raise httpx.HTTPStatusError("Falha temporária",request=response.request,response=response)

async def _stream_ollama(client:httpx.AsyncClient,url:str,request_body:dict,request_timeout:float,progress_callback)->tuple[dict,str]:
    content_parts=[];generated_parts=[];final_body={}
    async with client.stream("POST",url,timeout=request_timeout,json={**request_body,"stream":True}) as response:
        _check_stream_status(response)
        async for line in response.aiter_lines():
            if not line.strip():continue
            chunk=json.loads(line);final_body.update(chunk)
            message=chunk.get("message",{}) if isinstance(chunk,dict) else {}
            piece=_stream_piece(message.get("content",""));thinking=_stream_piece(message.get("thinking",""))
            if piece:content_parts.append(piece)
            if piece or thinking:generated_parts.extend([thinking,piece])
            await _notify_progress(progress_callback,"".join(generated_parts),chunk.get("eval_count"))
    return final_body,"".join(content_parts)

async def _stream_external(client:httpx.AsyncClient,url:str,headers:dict,variants:list[dict],request_timeout:float,progress_callback)->tuple[dict,str]:
    for variant in variants:
        content_parts=[];generated_parts=[];usage={}
        async with client.stream("POST",url,timeout=request_timeout,headers=headers,json={**variant,"stream":True}) as response:
            if response.status_code==400:
                await response.aread();continue
            _check_stream_status(response)
            async for line in response.aiter_lines():
                value=line.strip()
                if not value:continue
                if value.startswith("data:"):value=value[5:].strip()
                if value=="[DONE]":break
                chunk=json.loads(value)
                if isinstance(chunk.get("usage"),dict):usage=chunk["usage"]
                choice=(chunk.get("choices") or [{}])[0]
                message=choice.get("delta") or choice.get("message") or {}
                piece=_stream_piece(message.get("content",""));thinking=_stream_piece(message.get("reasoning_content",message.get("reasoning","")))
                if piece:content_parts.append(piece)
                if piece or thinking:generated_parts.extend([thinking,piece])
                exact=usage.get("completion_tokens") if isinstance(usage.get("completion_tokens"),int) else None
                await _notify_progress(progress_callback,"".join(generated_parts),exact)
        return {"usage":usage},"".join(content_parts)
    raise HTTPException(502,"O provedor de IA recusou a requisição")

def _external_variants(model:str,prompt:list[dict],max_tokens:int,temperature:float,provider:str)->list[dict]:
    token_keys=["max_completion_tokens","max_tokens"] if provider=="openai" else ["max_tokens","max_completion_tokens"]
    variants=[]
    for token_key in token_keys:
        base={"model":model,"messages":prompt,"temperature":temperature,token_key:max_tokens}
        variants.append(base)
        variants.append({key:value for key,value in base.items() if key!="temperature"})
    return variants

async def ask_json(model:str,system:str,messages:list[dict],context_size:int=8192,max_tokens:int=512,temperature:float=.2,contract:str="intake",forbidden_questions:list[str]|None=None,context_messages:list[str]|None=None,provider:str="ollama",api_base_url:str|None=None,api_key:str|None=None,timeout_seconds:int=90,rules:dict|None=None,max_attempts:int|None=None,progress_callback=None)->dict:
    safe=[{"role":m["role"],"content":m["content"][:5000]} for m in messages[-16:]]
    external=provider!="ollama";base_url=None
    if external:
        if not api_base_url or not api_key:raise HTTPException(503,"A credencial do provedor externo não está configurada")
        base_url=validate_api_base_url(provider,api_base_url);await ensure_public_destination(base_url)
    applied={**DEFAULT_RULES,**(rules or {})};deadline=time.monotonic()+max(15,min(timeout_seconds,300));attempt=0;last_reason="tempo de resposta excedido"
    async with httpx.AsyncClient() as client:
        while time.monotonic()<deadline:
            attempt+=1;remaining=max(1,deadline-time.monotonic());request_timeout=min(remaining,max(15,min(120,timeout_seconds if max_attempts==1 else timeout_seconds*.7)))
            if attempt==1:correction=""
            elif contract in {"question","intake"}:correction=f"\nA resposta anterior foi rejeitada por: {last_reason}. Entregue somente a pergunta final em texto simples. Faça exatamente uma pergunta curta e autocontida sobre o problema concreto descrito pelo usuário, sem listas, sem repetir assuntos e sem perguntar nome ou setor."
            elif contract=="summary":correction=f"\nA resposta anterior foi rejeitada por: {last_reason}. Entregue o resumo final em texto simples, usando uma linha para cada campo: Título, Descrição, Produto, Prioridade e Contato."
            else:correction=f"\nA resposta anterior foi rejeitada por: {last_reason}. Entregue somente a resposta final em texto simples, sem raciocínio, JSON ou Markdown."
            try:
                prompt=[{"role":"system","content":system+correction},*safe]
                if external:
                    variants=_external_variants(model,prompt,max_tokens,temperature,provider);headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"};url=f"{base_url}/chat/completions"
                    if progress_callback is not None:body,content=await _stream_external(client,url,headers,variants,request_timeout,progress_callback)
                    else:
                        response=None
                        for request_body in variants:
                            response=await client.post(url,timeout=request_timeout,headers=headers,json=request_body)
                            if response.status_code!=400:break
                        if response is None:raise ValueError("Sem resposta do provedor")
                        _check_stream_status(response);body=response.json();content=body.get("choices",[{}])[0].get("message",{}).get("content","")
                else:
                    request_body={"model":model,"stream":False,"messages":prompt,"options":{"temperature":temperature,"num_ctx":context_size,"num_predict":max_tokens}}
                    url=f"{get_settings().ollama_url}/api/chat"
                    if progress_callback is not None:body,content=await _stream_ollama(client,url,request_body,request_timeout,progress_callback)
                    else:
                        response=await client.post(url,timeout=request_timeout,json=request_body);_check_stream_status(response);body=response.json();content=body.get("message",{}).get("content","")
                payload=parse_model_response(content,contract,applied["allow_plain_text_repair"])
                if contract in {"question","intake"}:payload=repair_question_payload(payload,content,forbidden_questions,context_messages,applied)
                last_reason=contract_error(payload,contract,forbidden_questions,context_messages,applied) or ""
                if not last_reason:
                    payload["_provider_usage"]={**response_usage(body,content,external),"attempts":attempt}
                    return payload
            except HTTPException:raise
            except httpx.TimeoutException:last_reason="tempo de geração excedido"
            except httpx.HTTPError:last_reason="falha temporária de comunicação com o provedor"
            except (ValueError,json.JSONDecodeError):last_reason="formato JSON inválido"
            except (AttributeError,KeyError,TypeError):last_reason="resposta incompleta do provedor"
            if max_attempts is not None and attempt>=max_attempts:break
            if time.monotonic()<deadline:await asyncio.sleep(min(1.5*attempt,5))
    raise HTTPException(504,f"O modelo não entregou uma resposta válida dentro do limite: {last_reason}")
