"""
UserInfo model for authenticated user data.
"""

from typing import Optional
from pydantic import BaseModel, EmailStr


class UserInfo(BaseModel):
    """
    User information returned by authentication middleware.
    
    Contains the OAuth token and cached user metadata.
    """
    token: str
    email: EmailStr
    name: Optional[str] = None
    picture: Optional[str] = None
    email_verified: Optional[bool] = None
    provider_id: Optional[str] = None
    cached_at: Optional[str] = None
    
    class Config:
        """Pydantic config."""
        from_attributes = True
