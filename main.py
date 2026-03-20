from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import AuthConfig, FastApiMCP
from pydantic import BaseModel
import uvicorn
import logging
import os
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


# Import routers
from routes import send_router, receive_router, auth_router
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


BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

@app.get("/.well-known/oauth-authorization-server")
async def oauth_metadata():
    return JSONResponse({
        "issuer": BASE_URL,
        "authorization_endpoint": f"{BASE_URL}/auth/authorize",
        "token_endpoint": f"{BASE_URL}/auth/token",
        "registration_endpoint": f"{BASE_URL}/auth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["email.read", "email.send"]
    })

security = HTTPBearer(auto_error=False)

async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(security)
):
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return credentials.credentials

# Include routers
app.include_router(send_router,dependencies=[Depends(require_auth)])
app.include_router(receive_router,dependencies=[Depends(require_auth)])
app.include_router(auth_router)

# MCP Integration
mcp = FastApiMCP(
    fastapi=app,
    name="Email MCP Server",
    description="MCP Server for Email operations with SMTP and IMAP support",
    auth_config=AuthConfig(
        dependencies=[Depends(require_auth)]
    )
)
mcp.mount_http()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
