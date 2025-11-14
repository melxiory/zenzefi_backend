from fastapi import APIRouter

from app.api.v1 import auth, users, tokens, currency, proxy, webhooks, admin

api_router = APIRouter()

# Include all routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(tokens.router, prefix="/tokens", tags=["Access Tokens"])
api_router.include_router(currency.router, prefix="/currency", tags=["Currency"])
api_router.include_router(proxy.router, prefix="/proxy", tags=["Proxy"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
