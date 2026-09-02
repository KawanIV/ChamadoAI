from pydantic import BaseModel, Field, field_validator
class LoginIn(BaseModel):
    tenant_slug:str=Field(pattern=r"^[a-z0-9-]{2,80}$");email:str=Field(max_length=254);password:str=Field(min_length=8,max_length=128)
class PublicTicketIn(BaseModel):
    requester_name:str=Field(min_length=2,max_length=120);department:str=Field(min_length=2,max_length=120);contact:str|None=Field(default=None,max_length=254);description:str=Field(min_length=10,max_length=5000);product:str=Field(max_length=80);public_context:str
    @field_validator("description")
    @classmethod
    def no_secrets(cls,v:str)->str:
        if any(x in v.lower() for x in ["senha:","password:","token:"]):raise ValueError("Não envie senhas ou tokens")
        return v.strip()
class ResolutionIn(BaseModel):
    confirmed_problem:str=Field(min_length=5,max_length=5000);root_cause:str=Field(min_length=5,max_length=5000);solution:str=Field(min_length=5,max_length=10000);validation:str=Field(min_length=3,max_length=3000);reusable:bool=False
class AIConfigIn(BaseModel):
    model:str=Field(pattern=r"^[a-zA-Z0-9._:/-]{1,120}$");embedding_model:str=Field(pattern=r"^[a-zA-Z0-9._:/-]{1,120}$");context_size:int=Field(ge=1024,le=32768);max_tokens:int=Field(ge=64,le=2048);temperature:float=Field(ge=0,le=1)
class UserCreateIn(BaseModel):
    name:str=Field(min_length=2,max_length=120);email:str=Field(max_length=254);password:str=Field(min_length=12,max_length=128);role:str=Field(pattern=r"^(admin|agent)$")
class PublicChatIn(BaseModel):
    public_context:str;messages:list[dict[str,str]]=Field(min_length=1,max_length=12)
