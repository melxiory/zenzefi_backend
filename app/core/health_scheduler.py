"""
Health Check Scheduler

APScheduler integration for periodic health checks.
"""

import asyncio
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from app.config import settings
from app.services.health_service import HealthCheckService
from app.core.session_cleanup import cleanup_inactive_sessions
from app.core.audit_cleanup import cleanup_old_audit_logs


class HealthCheckScheduler:
    """Scheduler for periodic health checks"""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self._initialized = False

    def start(self):
        """
        Start the health check scheduler

        Schedules periodic health checks every HEALTH_CHECK_INTERVAL seconds.
        Runs the first check immediately on startup.
        """
        if self._initialized:
            logger.warning("Health check scheduler already started")
            return

        logger.info("Starting health check scheduler...")

        # Create AsyncIOScheduler
        self.scheduler = AsyncIOScheduler()

        # Schedule periodic health checks
        self.scheduler.add_job(
            func=self._run_health_check,
            trigger=IntervalTrigger(seconds=settings.HEALTH_CHECK_INTERVAL),
            id="health_check",
            name="Periodic Health Check",
            replace_existing=True,
            max_instances=1,  # Only one check at a time
        )

        # Schedule session cleanup (every 2 minutes for 5-minute timeout)
        self.scheduler.add_job(
            func=cleanup_inactive_sessions,
            trigger=IntervalTrigger(minutes=2),
            id="session_cleanup",
            name="Session Cleanup (5min timeout)",
            replace_existing=True,
            max_instances=1,
        )

        # Schedule audit log cleanup (daily at 3 AM)
        self.scheduler.add_job(
            func=cleanup_old_audit_logs,
            trigger=CronTrigger(hour=3, minute=0),
            id="audit_cleanup",
            name="Old Audit Logs Cleanup (30 days retention)",
            replace_existing=True,
            max_instances=1,
        )

        # Start scheduler
        self.scheduler.start()

        self._initialized = True

        logger.info(
            f"Health check scheduler started (interval: {settings.HEALTH_CHECK_INTERVAL}s)"
        )
        logger.info("Session cleanup scheduler started (interval: 2min, timeout: 5min)")
        logger.info("Audit cleanup scheduler started (daily at 3 AM, 30 days retention)")

        # Run first check immediately (non-blocking)
        asyncio.create_task(self._run_health_check())

    def shutdown(self):
        """
        Stop the health check scheduler
        """
        if not self._initialized or not self.scheduler:
            logger.warning("Health check scheduler not started")
            return

        logger.info("Stopping health check scheduler...")

        # Shutdown scheduler
        self.scheduler.shutdown(wait=False)

        self._initialized = False

        logger.info("Health check scheduler stopped")

    @staticmethod
    async def _run_health_check():
        """
        Run health check and cache results

        This method is called by APScheduler periodically.
        """
        try:
            await HealthCheckService.perform_and_cache_health_check()
        except Exception as e:
            logger.error(f"Health check failed with error: {e}", exc_info=True)


# Global scheduler instance
_scheduler_instance: Optional[HealthCheckScheduler] = None


def get_health_scheduler() -> HealthCheckScheduler:
    """
    Get the global health check scheduler instance (singleton)

    Returns:
        HealthCheckScheduler instance
    """
    global _scheduler_instance

    if _scheduler_instance is None:
        _scheduler_instance = HealthCheckScheduler()

    return _scheduler_instance


def start_health_scheduler():
    """
    Start the global health check scheduler

    Called on application startup.
    """
    scheduler = get_health_scheduler()
    scheduler.start()


def shutdown_health_scheduler():
    """
    Shutdown the global health check scheduler

    Called on application shutdown.
    """
    scheduler = get_health_scheduler()
    scheduler.shutdown()
