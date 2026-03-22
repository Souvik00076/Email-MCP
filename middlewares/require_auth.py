"""
Authentication middleware with Redis look-aside caching.

Implements the following flow:
1. Extract bearer token
2. Check TokenRepository cache
3. If cache hit: return UserInfo with cached data
4. If cache miss: fetch from Google OAuth API, cache, and return UserInfo
5. If Redis fails: raise 503 (fail-fast)
"""

import logging
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.cache import TokenRepository
from .user_info import UserInfo

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(security)
) -> UserInfo:
    """
    Authenticate request using bearer token with Redis caching.

    Look-aside cache strategy:
    - Cache hit: return UserInfo with cached data immediately
    - Cache miss: fetch user info from Google OAuth, cache it, return UserInfo

    Args:
        credentials: HTTP bearer token credentials

    Returns:
        UserInfo: User information object containing token and user metadata

    Raises:
        HTTPException 401: If not authenticated or invalid token
        HTTPException 503: If Redis is unavailable (fail-fast)
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials

    try:
        # Initialize TokenRepository
        token_repo = TokenRepository()

        # Check cache first (look-aside strategy)
        cached_user = token_repo.get_user_by_token(token)

        if cached_user:
            # Cache hit - return UserInfo with cached data
            logger.info(f"Cache hit for user: {cached_user.get('email')}")
            return UserInfo(
                token=token,
                email=cached_user.get('email'),
                name=cached_user.get('name'),
                picture=cached_user.get('picture'),
                email_verified=cached_user.get('email_verified'),
                provider_id=cached_user.get('provider_id'),
                cached_at=cached_user.get('cached_at')
            )

        # Cache miss - fetch from Google OAuth API
        logger.info("Cache miss - fetching user info from Google OAuth")

        try:
            # Lazy import to avoid circular dependency
            from routes.auth.google_oauth_strategy import GoogleOAuthStrategy
            
            oauth_strategy = GoogleOAuthStrategy()
            user_info = await oauth_strategy.get_user_info(token)

            # Cache the user data
            token_repo.set_user_for_token(
                token=token,
                email=user_info.email,
                metadata={
                    "name": user_info.name,
                    "picture": user_info.picture,
                    "email_verified": user_info.email_verified,
                    "provider_id": user_info.id
                }
            )

            logger.info(f"Cached user info for: {user_info.email}")

            # Return UserInfo object
            return UserInfo(
                token=token,
                email=user_info.email,
                name=user_info.name,
                picture=user_info.picture,
                email_verified=user_info.email_verified,
                provider_id=user_info.id
            )

        except HTTPException:
            # Re-raise HTTP exceptions (invalid token, etc.)
            raise
        except Exception as e:
            logger.error(f"Failed to fetch user info from OAuth: {str(e)}")
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token"
            )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Redis connection error or other infrastructure issues
        logger.error(f"Cache service error: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail="Cache service unavailable"
        )
