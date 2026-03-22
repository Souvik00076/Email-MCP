"""
Application lifespan management for Email MCP Server.

Handles startup and shutdown events including Redis connection initialization.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from core.cache import RedisClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    
    Startup:
    - Initialize Redis connection
    - Verify Redis is responsive
    - Fail fast if Redis is unavailable
    
    Shutdown:
    - Close Redis connection gracefully
    """
    # Startup: Initialize Redis connection
    logger.info("Starting Email MCP Server...")
    try:
        redis_client = RedisClient.get_instance()
        if redis_client.ping():
            stats = redis_client.get_stats()
            logger.info(f"✓ Redis connected: {stats['host']}:{stats['port']}/{stats['db']}")
            logger.info(f"✓ Redis stats: {stats['total_keys']} keys, {stats['used_memory_human']} memory")
        else:
            logger.error("✗ Redis ping failed - server not responding")
            raise ConnectionError("Redis server is not responding")
    except Exception as e:
        logger.error(f"✗ Failed to connect to Redis: {str(e)}")
        logger.error("Server startup aborted - Redis connection required")
        raise
    
    logger.info("✓ Email MCP Server startup complete")
    
    yield
    
    # Shutdown: Close Redis connection
    logger.info("Shutting down Email MCP Server...")
    try:
        redis_client.close()
        logger.info("✓ Redis connection closed")
    except Exception as e:
        logger.error(f"Error closing Redis connection: {str(e)}")
    logger.info("✓ Email MCP Server shutdown complete")
