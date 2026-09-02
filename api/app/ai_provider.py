import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit
from fastapi import HTTPException

PROVIDER_PRESETS={
    "openai":"https://api.openai.com/v1",
    "deepseek":"https://api.deepseek.com",
    "groq":"https://api.groq.com/openai/v1",
    "openrouter":"https://openrouter.ai/api/v1",
}

def _is_public_address(value:str)->bool:
    address=ipaddress.ip_address(value)
    return not (address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified)

def validate_api_base_url(provider:str,value:str)->str:
    raw=value.strip().rstrip("/")
    try:parsed=urlsplit(raw)
    except ValueError:raise HTTPException(422,"URL da API inválida")
    if parsed.scheme!="https" or not parsed.hostname:raise HTTPException(422,"A API externa deve usar HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:raise HTTPException(422,"A URL da API não pode conter credenciais, parâmetros ou fragmentos")
    hostname=parsed.hostname.rstrip(".").lower()
    if provider in PROVIDER_PRESETS and hostname!=urlsplit(PROVIDER_PRESETS[provider]).hostname:raise HTTPException(422,"Use o provedor Personalizado para informar outro domínio")
    try:
        if not _is_public_address(hostname):raise HTTPException(422,"A URL da API não pode apontar para uma rede privada")
    except ValueError:pass
    return urlunsplit(("https",parsed.netloc,parsed.path.rstrip("/"),"",""))

async def ensure_public_destination(value:str)->None:
    parsed=urlsplit(value);host=parsed.hostname
    if not host:raise HTTPException(422,"URL da API inválida")
    try:
        addresses=await asyncio.to_thread(socket.getaddrinfo,host,parsed.port or 443,type=socket.SOCK_STREAM)
    except socket.gaierror:raise HTTPException(502,"Não foi possível localizar o servidor do provedor")
    resolved={item[4][0] for item in addresses}
    if not resolved or any(not _is_public_address(address) for address in resolved):raise HTTPException(422,"O provedor resolveu para uma rede não permitida")

def credentials_key()->str:
    from .config import get_settings
    configured=get_settings().ai_credentials_key
    if configured is None or len(configured.get_secret_value())<32:raise HTTPException(503,"Configure AI_CREDENTIALS_KEY com pelo menos 32 caracteres no servidor")
    return configured.get_secret_value()
