from typing import Literal
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
class LoginIn(BaseModel):
    tenant_slug:str=Field(pattern=r"^[a-z0-9-]{2,80}$");email:str=Field(max_length=254);password:str=Field(min_length=8,max_length=128)
class PublicTicketIn(BaseModel):
    requester_name:str=Field(min_length=2,max_length=120);department:str=Field(min_length=2,max_length=120);contact:str|None=Field(default=None,max_length=254);title:str|None=Field(default=None,max_length=180);description:str=Field(min_length=10,max_length=5000);product:str=Field(min_length=2,max_length=80);priority:str=Field(default="normal",pattern=r"^(low|normal|high)$");assistant_mode:Literal["intake","support"]="intake";public_context:str
    @field_validator("description")
    @classmethod
    def no_secrets(cls,v:str)->str:
        if any(x in v.lower() for x in ["senha:","password:","token:"]):raise ValueError("Não envie senhas ou tokens")
        return v.strip()
class ResolutionIn(BaseModel):
    confirmed_problem:str=Field(min_length=5,max_length=5000);root_cause:str=Field(min_length=5,max_length=5000);solution:str=Field(min_length=5,max_length=10000);validation:str=Field(min_length=3,max_length=3000);reusable:bool=False
class AIConfigIn(BaseModel):
    provider:Literal["ollama","openai","deepseek","groq","openrouter","custom"]="ollama";model:str=Field(pattern=r"^[a-zA-Z0-9._:/-]{1,120}$");embedding_model:str=Field(default="",pattern=r"^[a-zA-Z0-9._:/-]{0,120}$");api_base_url:str|None=Field(default=None,max_length=500);api_key:SecretStr|None=Field(default=None,min_length=8,max_length=512);context_size:int=Field(ge=1024,le=32768);max_tokens:int=Field(ge=64,le=8192);temperature:float=Field(ge=0,le=1)
    @model_validator(mode="after")
    def provider_fields(self):
        if self.provider!="ollama" and not (self.api_base_url or "").strip():raise ValueError("Informe a URL base da API")
        if self.provider=="ollama" and not self.embedding_model:raise ValueError("Selecione o modelo de embeddings do Ollama")
        return self
class UserCreateIn(BaseModel):
    name:str=Field(min_length=2,max_length=120);email:str=Field(max_length=254);password:str=Field(min_length=12,max_length=128);role:Literal["agent"]="agent"
class PublicChatIn(BaseModel):
    public_context:str;assistant:Literal["intake","support"]="intake";action:Literal["message","summarize"]="message";conversation_state:str|None=None;requester_name:str=Field(default="",max_length=120);department:str=Field(default="",max_length=120);messages:list[dict[str,str]]=Field(min_length=1,max_length=16)
class TicketStatusIn(BaseModel):
    status:Literal["new","analysis","working","waiting","validation","resolved","closed","cancelled"]
