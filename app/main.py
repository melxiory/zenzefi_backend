from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import settings
from app.core.logging import setup_logging
from app.core.redis import get_redis_client, close_redis_client
from app.core.health_scheduler import start_health_scheduler, shutdown_health_scheduler
from app.api.v1 import api_router
from app.services.health_service import HealthCheckService
from app.schemas.health import HealthResponse, SimpleHealthResponse

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

    # Start health check scheduler
    try:
        start_health_scheduler()
        logger.info("Health check scheduler started")
    except Exception as e:
        logger.error(f"Failed to start health check scheduler: {e}")

    logger.info("Application startup complete")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("Shutting down application")

    # Shutdown health check scheduler
    try:
        shutdown_health_scheduler()
        logger.info("Health check scheduler stopped")
    except Exception as e:
        logger.error(f"Failed to stop health check scheduler: {e}")

    # Close Redis connection
    close_redis_client()
    logger.info("Redis connection closed")

    logger.info("Application shutdown complete")


# Health check endpoint - Simple version
@app.get("/health", tags=["Health"], response_model=SimpleHealthResponse)
async def health_check():
    """
    Simple health check endpoint

    Returns minimal health status (status + timestamp only).
    Lightweight endpoint for monitoring systems and load balancers.

    The health status is updated every 50 seconds by a background scheduler.

    Returns:
        SimpleHealthResponse: Basic health status
            - status: Overall system status (healthy/degraded/unhealthy)
            - timestamp: Time of last health check

    For detailed information, use GET /health/detailed
    """
    # Try to get cached health status from Redis
    cached_health = HealthCheckService.get_health_from_redis()

    if cached_health:
        # Return only status and timestamp
        return SimpleHealthResponse(
            status=cached_health.status, timestamp=cached_health.timestamp
        )

    # If no cached data, perform a fresh check
    logger.warning("No cached health status found, performing fresh check")
    health = await HealthCheckService.perform_and_cache_health_check()

    return SimpleHealthResponse(status=health.status, timestamp=health.timestamp)


# Detailed health check endpoint
@app.get("/health/detailed", tags=["Health"], response_model=HealthResponse)
async def health_check_detailed():
    """
    Detailed health check endpoint

    Returns comprehensive health status with all service details.
    Use this endpoint for debugging and internal monitoring.

    The health status is updated every 50 seconds by a background scheduler.

    Returns:
        HealthResponse: Detailed health status of all system components
            - status: Overall system status (healthy/degraded/unhealthy)
            - timestamp: Time of last health check
            - checks: Individual service statuses (database, redis, zenzefi)
                * status: up/down/unknown
                * latency_ms: Response time in milliseconds
                * error: Error message if service is down
                * url: Service URL (for external services)
            - overall: Statistics (healthy_count, total_count)
    """
    # Try to get cached health status from Redis
    cached_health = HealthCheckService.get_health_from_redis()

    if cached_health:
        return cached_health

    # If no cached data, perform a fresh check
    logger.warning("No cached health status found, performing fresh check")
    health = await HealthCheckService.perform_and_cache_health_check()

    return health


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
