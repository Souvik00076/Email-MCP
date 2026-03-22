
from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel


class OAuthUserInfo(BaseModel):
    id: str
    email: str
    name: str
    picture: Optional[str] = None
    email_verified: bool


class OAuthStrategy(ABC):
    @abstractmethod
    def get_auth_url(self, state: str) -> str:
        pass

    @abstractmethod
    async def exchange_code_for_token(self, code: str) -> str:
        """Returns access_token"""
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        pass

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> str:
        """Refresh access token using refresh token. Returns new access_token."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass
