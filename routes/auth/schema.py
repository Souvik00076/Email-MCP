from typing import List, Optional

from pydantic import BaseModel



class AuthRegisterRequest(BaseModel):
    clien_name:str
    redirect_uris:List[str]=[]
    grant_types:List[str]=[]
    response_types:List[str]=[]
    token_input_method:str="none"

class AuthRegisterResponse(AuthRegisterRequest):
    client_id:str

class AuthAuthorizeRequest(BaseModel):
    response_type:str
    client_id:str
    redirect_uri:str
    state:str
    code_challenge:str
    code_challenge_method:str
    scopes:str

class AuthCallbackRequest(BaseModel):
    code:str
    state:str

class AuthTokenRequest(BaseModel):
    grant_type:str
    code:Optional[str]
    code_verifier:Optional[str]
    redirect_uri:Optional[str]
    refresh_token:Optional[str]
