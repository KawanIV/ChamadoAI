import asyncio, json, time
import httpx
from fastapi import HTTPException
from .config import get_settings

async def list_models()->list[dict]:
    async with httpx.AsyncClient(timeout=8) as client:
        response=await client.get(f"{get_settings().ollama_url}/api/tags");response.raise_for_status();return response.json().get("models",[])
def valid_json_contract(payload:object,contract:str)->bool:
    if not isinstance(payload,dict):return False
    action=payload.get("action");message=payload.get("message")
    if not isinstance(message,str) or not message.strip():return False
    if contract=="support":return action in {"answer","offer_ticket"}
    if contract=="summary":return action=="summary" and isinstance(payload.get("summary"),dict)
    if contract=="intake":return (action=="question") or (action=="summary" and isinstance(payload.get("summary"),dict))
    return False

async def ask_json(model:str,system:str,messages:list[dict],context_size:int=8192,max_tokens:int=512,temperature:float=.2,contract:str="intake")->dict:
    safe=[{"role":m["role"],"content":m["content"][:5000]} for m in messages[-16:]]
    deadline=time.monotonic()+90;attempt=0
    async with httpx.AsyncClient() as client:
        while time.monotonic()<deadline:
            attempt+=1;remaining=max(1,deadline-time.monotonic());correction="" if attempt==1 else "\nA resposta anterior não respeitou o JSON exigido. Corrija a estrutura e responda novamente somente com JSON válido."
            try:
                response=await client.post(f"{get_settings().ollama_url}/api/chat",timeout=min(45,remaining),json={"model":model,"stream":False,"format":"json","messages":[{"role":"system","content":system+correction},*safe],"options":{"temperature":temperature,"num_ctx":context_size,"num_predict":max_tokens}})
                if 400<=response.status_code<500 and response.status_code not in {408,429}:raise HTTPException(502,"Modelo local indisponível")
                if response.status_code>=500 or response.status_code in {408,429}:raise httpx.HTTPStatusError("Falha temporária",request=response.request,response=response)
                content=response.json().get("message",{}).get("content","");payload=json.loads(content)
                if valid_json_contract(payload,contract):return payload
            except HTTPException:raise
            except (httpx.HTTPError,AttributeError,KeyError,TypeError,ValueError,json.JSONDecodeError):pass
            if time.monotonic()<deadline:await asyncio.sleep(min(1.5*attempt,5))
    raise HTTPException(504,"O modelo demorou mais que o esperado para gerar uma resposta válida")
