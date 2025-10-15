from fastapi import APIRouter

from app.api.v1 import auth, users, tokens, proxy

api_router = APIRouter()

# Include all routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(tokens.router, prefix="/tokens", tags=["Access Tokens"])
api_router.include_router(proxy.router, prefix="/proxy", tags=["Proxy"])
