"""
Health Check Schemas

Pydantic models for health check responses.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ServiceStatus(str, Enum):
    """Service status enumeration"""

    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


class OverallStatus(str, Enum):
    """Overall health status enumeration"""

    HEALTHY = "healthy"  # All services are up
    DEGRADED = "degraded"  # Some non-critical services are down
    UNHEALTHY = "unhealthy"  # Critical services are down


class ServiceCheck(BaseModel):
    """Individual service check result"""

    status: ServiceStatus = Field(..., description="Service status (up/down/unknown)")
    latency_ms: Optional[float] = Field(
        None, description="Response latency in milliseconds"
    )
    error: Optional[str] = Field(None, description="Error message if service is down")
    url: Optional[str] = Field(None, description="Service URL (for external services)")

    class Config:
        from_attributes = True


class HealthChecks(BaseModel):
    """All service checks"""

    database: ServiceCheck = Field(..., description="PostgreSQL database status")
    redis: ServiceCheck = Field(..., description="Redis cache status")
    zenzefi: ServiceCheck = Field(..., description="Zenzefi server status")

    class Config:
        from_attributes = True


class HealthOverall(BaseModel):
    """Overall health statistics"""

    healthy_count: int = Field(..., description="Number of healthy services")
    total_count: int = Field(..., description="Total number of services")

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    """Health check response"""

    status: OverallStatus = Field(..., description="Overall system status")
    timestamp: datetime = Field(..., description="Health check timestamp")
    checks: HealthChecks = Field(..., description="Individual service checks")
    overall: HealthOverall = Field(..., description="Overall statistics")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2025-11-05T20:30:45Z",
                "checks": {
                    "database": {
                        "status": "up",
                        "latency_ms": 10.5,
                        "error": None,
                        "url": None,
                    },
                    "redis": {
                        "status": "up",
                        "latency_ms": 1.2,
                        "error": None,
                        "url": None,
                    },
                    "zenzefi": {
                        "status": "up",
                        "latency_ms": 150.3,
                        "error": None,
                        "url": "https://zenzefi.melxiory.ru",
                    },
                },
                "overall": {"healthy_count": 3, "total_count": 3},
            }
        }


class SimpleHealthResponse(BaseModel):
    """Simple health check response - minimal information"""

    status: OverallStatus = Field(..., description="Overall system status")
    timestamp: datetime = Field(..., description="Health check timestamp")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2025-11-05T20:30:45Z",
            }
        }
