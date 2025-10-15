import sys
from loguru import logger

from app.config import settings


def setup_logging():
    """
    Configure Loguru logging.
    Should be called on application startup.
    """
    # Remove default handler
    logger.remove()

    # Add custom handler with format
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # Console handler
    logger.add(
        sys.stdout,
        format=log_format,
        level="DEBUG" if settings.DEBUG else "INFO",
        colorize=True,
    )

    # File handler for errors
    logger.add(
        "logs/error.log",
        format=log_format,
        level="ERROR",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
    )

    # File handler for all logs (in production)
    if not settings.DEBUG:
        logger.add(
            "logs/app.log",
            format=log_format,
            level="INFO",
            rotation="50 MB",
            retention="14 days",
            compression="zip",
        )

    logger.info("Logging configured successfully")
