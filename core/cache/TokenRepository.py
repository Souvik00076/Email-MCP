"""
TokenRepository - Repository for managing token-to-user-data mappings in Redis.

Implements look-aside caching for OAuth tokens with SHA-256 hashed keys.
"""

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from .BaseRepository import BaseRepository

logger = logging.getLogger(__name__)


class TokenRepository(BaseRepository):

    def __init__(self):
        super().__init__(prefix="token")
        self.default_ttl = int(os.getenv('REDIS_TOKEN_TTL', '600'))

    def _hash_token(self, token: str) -> str:

        return hashlib.sha256(token.encode()).hexdigest()

    def get_user_by_token(self, token: str) -> Optional[dict]:
        try:
            token_hash = self._hash_token(token)
            user_data = self.get(token_hash)
            return user_data
        except Exception as e:
            logger.error(f"Error retrieving user by token: {str(e)}")
            raise

    def set_user_for_token(
        self,
        token: str,
        email: str,
        metadata: Optional[dict] = None,
        ttl: Optional[int] = None
    ) -> bool:

        try:
            token_hash = self._hash_token(token)
            # Build user data object
            user_data = {
                "email": email,
                "cached_at": datetime.now(timezone.utc).isoformat()
            }

            # Merge additional metadata if provided
            if metadata:
                user_data.update(metadata)

            # Use default TTL if not specified
            cache_ttl = ttl if ttl is not None else self.default_ttl

            # Store in Redis
            self.set(token_hash, user_data, ttl=cache_ttl)

            logger.info(f"Cached user data for {email} with TTL {cache_ttl}s")
            return True

        except Exception as e:
            logger.error(f"Error caching user for token: {str(e)}")
            raise

    def get_email_by_token(self, token: str) -> Optional[str]:
        user_data = self.get_user_by_token(token)
        return user_data.get("email") if user_data else None

    def get_metadata_by_token(self, token: str) -> Optional[dict]:

        user_data = self.get_user_by_token(token)
        if not user_data:
            return None

        # Return everything except email
        metadata = {k: v for k, v in user_data.items() if k != "email"}
        return metadata

    def invalidate_token(self, token: str) -> bool:

        try:
            token_hash = self._hash_token(token)
            result = self.delete(token_hash)

            if result:
                logger.info("Token invalidated from cache")
            else:
                logger.info("Token not found in cache for invalidation")

            return result

        except Exception as e:
            logger.error(f"Error invalidating token: {str(e)}")
            raise

    def refresh_ttl(self, token: str, ttl: Optional[int] = None) -> bool:

        try:
            token_hash = self._hash_token(token)
            cache_ttl = ttl if ttl is not None else self.default_ttl

            result = self.set_ttl(token_hash, cache_ttl)

            if result:
                logger.info(f"Refreshed token TTL to {cache_ttl}s")
            else:
                logger.info("Token not found in cache for TTL refresh")

            return result

        except Exception as e:
            logger.error(f"Error refreshing token TTL: {str(e)}")
            raise

    def token_exists(self, token: str) -> bool:

        try:
            token_hash = self._hash_token(token)
            return self.exists(token_hash)

        except Exception as e:
            logger.error(f"Error checking token existence: {str(e)}")
            raise

    def get_token_ttl(self, token: str) -> int:

        try:
            token_hash = self._hash_token(token)
            return self.get_ttl(token_hash)

        except Exception as e:
            logger.error(f"Error getting token TTL: {str(e)}")
            raise
