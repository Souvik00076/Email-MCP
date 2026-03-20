from fastapi import APIRouter, Depends, Form, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import DefaultDict, Optional, List
from datetime import datetime
import logging
import uuid
import hashlib
import base64
import json
from urllib.parse import urlencode

from core.encryption import EncryptionStrategy
from core.encryption.FernetEncryptionStrategy import FernetEncryption
from routes.auth.google_oauth_strategy import GoogleOAuthStrategy
from routes.auth.oauth_strategy import OAuthStrategy
from routes.auth.schema import AuthAuthorizeRequest, AuthCallbackRequest, AuthRegisterRequest, AuthRegisterResponse


logger=logging.getLogger(__name__)

router=APIRouter(prefix="/auth",tags=["Authentication and Authorization"])


@router.post('/register',response_model=AuthRegisterResponse,status_code=status.HTTP_201_CREATED)
async def register_client(request:AuthRegisterRequest):
    client_id=uuid.uuid4()
    return AuthRegisterResponse(
        **request.model_dump(),
        client_id=str(client_id)
    )


@router.get('/authorize',status_code=status.HTTP_302_FOUND)
async def authorize_client(request:AuthAuthorizeRequest=Depends()):
    auth_strategy:OAuthStrategy=GoogleOAuthStrategy()
    encryption_strategy:EncryptionStrategy=FernetEncryption()
    client_state:dict[str,str]=DefaultDict(str)
    client_state['uri']=request.redirect_uri
    client_state['state']=request.state
    client_state['code_challenge']=request.code_challenge
    client_state['code_challenge_method']=request.code_challenge_method
    state=encryption_strategy.encrypt(client_state)
    print(f"Encrypted {state}")
    url=auth_strategy.get_auth_url(state,request.scopes)
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)

@router.get('/callback',status_code=status.HTTP_302_FOUND)
async def oauth_provider_callback(request:AuthCallbackRequest=Depends()):
    auth_strategy:OAuthStrategy=GoogleOAuthStrategy()
    encryption_strategy:EncryptionStrategy=FernetEncryption()
    client_state=DefaultDict(str)
    print("hwhakjsfhk")
    token=await auth_strategy.exchange_code_for_token(request.code)
    decrypted_state=encryption_strategy.decrypt(request.state)
    redirect_uri=decrypted_state['uri']
    code_challenge=decrypted_state['code_challenge']
    code_challenge_method=decrypted_state['code_challenge_method']
    state=decrypted_state['state']
    print("helo fucker")
    if redirect_uri is None or code_challenge is None or state is None or code_challenge_method is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Invalid Code")

    client_state['code_challenge']=code_challenge
    client_state['code_challenge_method']=code_challenge_method
    client_state['token']=token
    client_state['redirect_uri']=redirect_uri
    code=encryption_strategy.encrypt(client_state)
    print(code)
    params=urlencode({"code": code, "state": state})
    return RedirectResponse(
        f"{redirect_uri}?{params}",
        status_code=status.HTTP_302_FOUND
    )

@router.post('/token',status_code=status.HTTP_200_OK)
async def oauth_token(
    grant_type: str = Form(...),
    code: str = Form(None),
    code_verifier: str = Form(None),
    redirect_uri: str = Form(None),
    refresh_token: str = Form(None)
):
    encryption_strategy:EncryptionStrategy=FernetEncryption()
    if grant_type=="authorization_code":
        if not code or not code_verifier or not redirect_uri:
            raise HTTPException(400, "Missing required fields")
        try:
            data = encryption_strategy.decrypt(code)
        except Exception as e:
            raise HTTPException(400, "Invalid code")
        digest = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge=data['code_challenge']
        computed = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
        if computed != code_challenge:
            raise HTTPException(400, "Invalid code_verifier")
        if data['redirect_uri'] is None or redirect_uri !=data['redirect_uri']:
            raise HTTPException(400, "Redirect Uri must match")
        try:
            token=json.loads(data['token'])
        except:
            raise HTTPException(400,"Something went wrong")

        return token
