from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import settings
from app.core.logging import setup_logging
from app.core.redis import get_redis_client, close_redis_client
from app.api.v1 import api_router

# Setup logging
setup_logging()

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS middleware - UPDATED FOR COOKIE SUPPORT
app.add_middleware(
    CORSMiddleware,
    # IMPORTANT: For cookies, specific origins required (not "*")
    allow_origins=[
        "http://localhost:61000",
        "https://localhost:61000",
        "http://127.0.0.1:61000",
        "https://127.0.0.1:61000",
        # Add other origins as needed
    ],
    allow_credentials=True,  # CRITICAL for cookie support
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# Startup event
@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    logger.info(f"Debug mode: {settings.DEBUG}")

    # Test Redis connection
    try:
        redis = get_redis_client()
        redis.ping()
        logger.info("Redis connection established")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")

    logger.info("Application startup complete")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("Shutting down application")

    # Close Redis connection
    close_redis_client()
    logger.info("Redis connection closed")

    logger.info("Application shutdown complete")


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint

    Returns:
        Status of the application
    """
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint

    Returns:
        Welcome message
    """
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "version": settings.VERSION,
        "docs": "/docs",
    }


# Include API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

logger.info(f"{settings.PROJECT_NAME} initialized")
