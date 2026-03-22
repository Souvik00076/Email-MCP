"""
BaseRepository - Abstract base class for all Redis repositories.

Provides common operations for Redis data access with JSON serialization.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, Any
from redis import Redis

from .RedisClient import RedisClient

logger = logging.getLogger(__name__)


class BaseRepository(ABC):
    """
    Abstract base class for Redis repositories.

    All repositories should extend this class and implement their specific logic.
    Provides common operations: get, set, delete, exists, ttl management.
    """

    def __init__(self, prefix: str):
        """
        Initialize repository with a key prefix.

        Args:
            prefix: Key prefix for namespacing (e.g., "token", "email", "session")
        """
        self.prefix = prefix
        self._redis_client = RedisClient.get_instance()
        self._redis: Redis = self._redis_client.get_connection()

    def _build_key(self, key: str) -> str:
        """
        Build a namespaced Redis key with prefix.

        Args:
            key: The key identifier

        Returns:
            str: Prefixed key (e.g., "token:abc123")
        """
        return f"{self.prefix}:{key}"

    def get(self, key: str) -> Optional[dict]:
        """
        Get a value from Redis by key.

        Args:
            key: The key to lookup

        Returns:
            Optional[dict]: Deserialized JSON data or None if not found
        """
        try:
            full_key = self._build_key(key)
            value = self._redis.get(full_key)

            if value is None:
                logger.debug(f"Cache miss: {full_key}")
                return None

            logger.debug(f"Cache hit: {full_key}")
            return json.loads(value)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON for key {key}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Redis get error for key {key}: {str(e)}")
            raise

    def set(self, key: str, value: dict, ttl: Optional[int] = None) -> bool:
        """
        Set a value in Redis with optional TTL.

        Args:
            key: The key to set
            value: Dictionary to serialize and store
            ttl: Time-to-live in seconds (optional)

        Returns:
            bool: True if successful
        """
        try:
            full_key = self._build_key(key)
            serialized = json.dumps(value)

            if ttl:
                self._redis.setex(full_key, ttl, serialized)
                logger.debug(f"Set key {full_key} with TTL {ttl}s")
            else:
                self._redis.set(full_key, serialized)
                logger.debug(f"Set key {full_key} (no TTL)")

            return True

        except Exception as e:
            logger.error(f"Redis set error for key {key}: {str(e)}")
            raise

    def delete(self, key: str) -> bool:
        """
        Delete a key from Redis.

        Args:
            key: The key to delete

        Returns:
            bool: True if key was deleted, False if key didn't exist
        """
        try:
            full_key = self._build_key(key)
            result = self._redis.delete(full_key)

            if result > 0:
                logger.debug(f"Deleted key: {full_key}")
                return True
            else:
                logger.debug(f"Key not found for deletion: {full_key}")
                return False

        except Exception as e:
            logger.error(f"Redis delete error for key {key}: {str(e)}")
            raise

    def exists(self, key: str) -> bool:
        """
        Check if a key exists in Redis.

        Args:
            key: The key to check

        Returns:
            bool: True if key exists, False otherwise
        """
        try:
            full_key = self._build_key(key)
            return self._redis.exists(full_key) > 0

        except Exception as e:
            logger.error(f"Redis exists error for key {key}: {str(e)}")
            raise

    def get_ttl(self, key: str) -> int:
        """
        Get the remaining TTL for a key.

        Args:
            key: The key to check

        Returns:
            int: TTL in seconds, -1 if no expiry, -2 if key doesn't exist
        """
        try:
            full_key = self._build_key(key)
            return self._redis.ttl(full_key)

        except Exception as e:
            logger.error(f"Redis TTL error for key {key}: {str(e)}")
            raise

    def set_ttl(self, key: str, ttl: int) -> bool:
        """
        Set or update TTL for an existing key.

        Args:
            key: The key to update
            ttl: Time-to-live in seconds

        Returns:
            bool: True if successful, False if key doesn't exist
        """
        try:
            full_key = self._build_key(key)
            result = self._redis.expire(full_key, ttl)

            if result:
                logger.debug(f"Updated TTL for {full_key} to {ttl}s")
            else:
                logger.debug(f"Key not found for TTL update: {full_key}")

            return bool(result)

        except Exception as e:
            logger.error(f"Redis set TTL error for key {key}: {str(e)}")
            raise

    def get_all_keys(self) -> list[str]:
        """
        Get all keys with this repository's prefix.
        WARNING: Use with caution in production with large datasets.

        Returns:
            list[str]: List of keys (without prefix)
        """
        try:
            pattern = f"{self.prefix}:*"
            keys = self._redis.keys(pattern)

            # Remove prefix from keys
            prefix_len = len(self.prefix) + 1
            return [key[prefix_len:] for key in keys]

        except Exception as e:
            logger.error(f"Redis get_all_keys error: {str(e)}")
            raise
