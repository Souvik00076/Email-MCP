"""
RedisClient - Singleton Redis connection manager.

Manages a single Redis connection pool for the entire application.
"""

import os
import logging
from typing import Optional
import redis
from redis.connection import ConnectionPool

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Singleton Redis client with connection pooling.
    
    Usage:
        client = RedisClient.get_instance()
        client.ping()  # Health check
        redis_conn = client.get_connection()
    """
    
    _instance: Optional['RedisClient'] = None
    _connection_pool: Optional[ConnectionPool] = None
    _redis_client: Optional[redis.Redis] = None
    
    def __new__(cls):
        """Ensure only one instance exists (Singleton pattern)."""
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize Redis connection pool from environment variables."""
        try:
            host = os.getenv('REDIS_HOST', 'localhost')
            port = int(os.getenv('REDIS_PORT', '6379'))
            db = int(os.getenv('REDIS_DB', '0'))
            password = os.getenv('REDIS_PASSWORD', None)
            max_connections = int(os.getenv('REDIS_MAX_CONNECTIONS', '10'))
            
            # Create connection pool
            self._connection_pool = ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password if password else None,
                max_connections=max_connections,
                decode_responses=True,  # Automatically decode bytes to strings
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True
            )
            
            # Create Redis client
            self._redis_client = redis.Redis(connection_pool=self._connection_pool)
            
            # Test connection
            self._redis_client.ping()
            
            logger.info(f"Redis connection established: {host}:{port}/{db}")
            
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            raise ConnectionError(f"Redis connection failed: {str(e)}")
        except Exception as e:
            logger.error(f"Redis initialization error: {str(e)}")
            raise
    
    @classmethod
    def get_instance(cls) -> 'RedisClient':
        """
        Get the singleton instance of RedisClient.
        
        Returns:
            RedisClient: The singleton instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def get_connection(self) -> redis.Redis:
        """
        Get the Redis connection.
        
        Returns:
            redis.Redis: Redis client instance
            
        Raises:
            ConnectionError: If Redis is not connected
        """
        if self._redis_client is None:
            raise ConnectionError("Redis client is not initialized")
        return self._redis_client
    
    def ping(self) -> bool:
        """
        Health check - ping Redis server.
        
        Returns:
            bool: True if Redis is responsive, False otherwise
        """
        try:
            return self._redis_client.ping()
        except redis.ConnectionError as e:
            logger.error(f"Redis ping failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Redis ping error: {str(e)}")
            return False
    
    def close(self):
        """Close the Redis connection pool."""
        if self._connection_pool:
            self._connection_pool.disconnect()
            logger.info("Redis connection pool closed")
    
    def get_info(self) -> dict:
        """
        Get Redis server information.
        
        Returns:
            dict: Redis server info
        """
        try:
            return self._redis_client.info()
        except Exception as e:
            logger.error(f"Failed to get Redis info: {str(e)}")
            return {}
    
    def flush_db(self):
        """
        Flush all keys in the current database.
        WARNING: This deletes all data!
        """
        try:
            self._redis_client.flushdb()
            logger.warning("Redis database flushed (all keys deleted)")
        except Exception as e:
            logger.error(f"Failed to flush Redis database: {str(e)}")
            raise
    
    def get_stats(self) -> dict:
        """
        Get basic statistics about Redis connection.
        
        Returns:
            dict: Connection statistics
        """
        try:
            info = self._redis_client.info()
            return {
                "connected": self.ping(),
                "host": os.getenv('REDIS_HOST', 'localhost'),
                "port": int(os.getenv('REDIS_PORT', '6379')),
                "db": int(os.getenv('REDIS_DB', '0')),
                "used_memory_human": info.get('used_memory_human', 'N/A'),
                "connected_clients": info.get('connected_clients', 0),
                "total_keys": self._redis_client.dbsize()
            }
        except Exception as e:
            logger.error(f"Failed to get Redis stats: {str(e)}")
            return {
                "connected": False,
                "error": str(e)
            }
