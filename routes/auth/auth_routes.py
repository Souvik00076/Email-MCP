from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, status
from fastapi.responses import RedirectResponse
from typing import DefaultDict
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


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication and Authorization"])

STATE_COOKIE = 'oauth_state'


@router.post('/register', response_model=AuthRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_client(request: AuthRegisterRequest):
    client_id = uuid.uuid4()
    return AuthRegisterResponse(
        **request.model_dump(),
        client_id=str(client_id)
    )


@router.get('/authorize', status_code=status.HTTP_302_FOUND)
async def authorize_client(request: AuthAuthorizeRequest = Depends()):
    auth_strategy: OAuthStrategy = GoogleOAuthStrategy()
    encryption_strategy: EncryptionStrategy = FernetEncryption()
    client_state: dict[str, str] = DefaultDict(str)
    client_state['uri'] = request.redirect_uri
    client_state['state'] = request.state
    client_state['code_challenge'] = request.code_challenge
    client_state['code_challenge_method'] = request.code_challenge_method
    state = encryption_strategy.encrypt(client_state)
    url = auth_strategy.get_auth_url(state)
    response = RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=STATE_COOKIE,
        value=request.state,
        httponly=True,
        secure=True,
        samesite='lax',
        max_age=300,
        path='/auth'
    )
    return response


@router.get('/callback', status_code=status.HTTP_302_FOUND)
async def oauth_provider_callback(request: AuthCallbackRequest = Depends(), oauth_state: str | None = Cookie(default=None, alias=STATE_COOKIE)):
    if not oauth_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing state cookie"
        )
    auth_strategy: OAuthStrategy = GoogleOAuthStrategy()
    encryption_strategy: EncryptionStrategy = FernetEncryption()
    client_state = DefaultDict(str)
    token = await auth_strategy.exchange_code_for_token(request.code)
    decrypted_state = encryption_strategy.decrypt(request.state)
    redirect_uri = decrypted_state['uri']
    code_challenge = decrypted_state['code_challenge']
    code_challenge_method = decrypted_state['code_challenge_method']
    if redirect_uri is None or code_challenge is None or code_challenge_method is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Code")

    client_state['code_challenge'] = code_challenge
    client_state['code_challenge_method'] = code_challenge_method
    client_state['token'] = token
    client_state['redirect_uri'] = redirect_uri
    code = encryption_strategy.encrypt(client_state)
    params = urlencode({"code": code, "state": oauth_state})
    return RedirectResponse(
        f"{redirect_uri}?{params}",
        status_code=status.HTTP_302_FOUND
    )


@router.post('/token', status_code=status.HTTP_200_OK)
async def oauth_token(
    grant_type: str = Form(...),
    code: str = Form(None),
    code_verifier: str = Form(None),
    redirect_uri: str = Form(None),
    refresh_token: str = Form(None)
):
    encryption_strategy: EncryptionStrategy = FernetEncryption()
    auth_strategy: OAuthStrategy = GoogleOAuthStrategy()
    if grant_type == "authorization_code":
        if not code or not code_verifier or not redirect_uri:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required fields: code, code_verifier, and redirect_uri are required"
            )
        try:
            data = encryption_strategy.decrypt(code)
        except Exception as e:
            logger.error(f"Failed to decrypt code: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid code"
            )
        digest = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = data['code_challenge']
        computed = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
        if computed != code_challenge:
            logger.warning(
                "PKCE verification failed: code_verifier does not match code_challenge")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid code_verifier"
            )
        if data['redirect_uri'] is None or redirect_uri != data['redirect_uri']:
            logger.warning(f"Redirect URI mismatch: expected {
                           data['redirect_uri']}, got {redirect_uri}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Redirect URI must match"
            )
        try:
            token = json.loads(data['token'])
            logger.info("Successfully exchanged authorization code for token")
            return token
        except Exception as e:
            logger.error(f"Failed to parse token data: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process token"
            )
    elif grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required field: refresh_token is required"
            )
        try:
            new_token = await auth_strategy.refresh_token(refresh_token)
            token_data = json.loads(new_token)
            logger.info("Successfully refreshed access token")
            return token_data
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to refresh token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to refresh token"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported grant_type: {
                grant_type}. Supported types are 'authorization_code' and 'refresh_token'"
        )
