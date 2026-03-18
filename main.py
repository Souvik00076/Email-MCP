from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import FastApiMCP
from pydantic import BaseModel
import uvicorn
import logging

# Import routers
from routes import send_router, receive_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Email MCP Server",
    description="MCP Server for Email operations - Send via SMTP, Receive via IMAP",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Models for Health endpoints
class HealthResponse(BaseModel):
    status: str
    service: str


# Health Routes
@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint with health status"""
    return HealthResponse(status="healthy", service="Email MCP Server")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(status="healthy", service="Email MCP Server")


# Include routers
app.include_router(send_router)
app.include_router(receive_router)


# MCP Integration
mcp = FastApiMCP(
    fastapi=app,
    name="Email MCP Server",
    description="MCP Server for Email operations with SMTP and IMAP support"
)
mcp.mount()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
