from typing import Optional
from decimal import Decimal
from pydantic import field_validator, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    PROJECT_NAME: str = "Zenzefi Backend"
    VERSION: str = "0.7.0-beta"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Security
    SECRET_KEY: str  # Required in .env
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Database
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    SQLALCHEMY_DATABASE_URI: Optional[str] = None

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info) -> str:
        if isinstance(v, str) and v:
            return v
        values = info.data
        return (
            f"postgresql+psycopg2://{values.get('POSTGRES_USER')}:"
            f"{values.get('POSTGRES_PASSWORD')}@{values.get('POSTGRES_SERVER')}/"
            f"{values.get('POSTGRES_DB')}"
        )

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_URL: Optional[str] = None

    @field_validator("REDIS_URL", mode="before")
    @classmethod
    def assemble_redis_connection(cls, v: Optional[str], info) -> str:
        if isinstance(v, str) and v:
            return v
        values = info.data
        password = values.get("REDIS_PASSWORD")
        auth = f":{password}@" if password else ""
        return (
            f"redis://{auth}{values.get('REDIS_HOST')}:"
            f"{values.get('REDIS_PORT')}/{values.get('REDIS_DB')}"
        )

    # Zenzefi Target (via VPN)
    ZENZEFI_TARGET_URL: str = "https://zenzefi-win11-server"

    # Backend URL (for referral links, webhooks, etc.)
    BACKEND_URL: str = "http://localhost:8000"

    # Health Check Settings
    HEALTH_CHECK_INTERVAL: int = 50  # Health check interval in seconds (40-60s recommended)
    HEALTH_CHECK_TIMEOUT: float = 10.0  # Timeout for each individual check in seconds

    # Token Pricing (ZNC credits)
    TOKEN_PRICE_1H: Decimal = Field(default_factory=lambda: Decimal("1.00"))
    TOKEN_PRICE_12H: Decimal = Field(default_factory=lambda: Decimal("10.00"))
    TOKEN_PRICE_24H: Decimal = Field(default_factory=lambda: Decimal("18.00"))
    TOKEN_PRICE_7D: Decimal = Field(default_factory=lambda: Decimal("100.00"))   # 168 hours
    TOKEN_PRICE_30D: Decimal = Field(default_factory=lambda: Decimal("300.00"))  # 720 hours

    # Payment Gateway (Mock)
    ZNC_TO_RUB_RATE: Decimal = Field(default_factory=lambda: Decimal("10.00"))  # Conversion rate: 1 ZNC = 10 RUB
    MOCK_PAYMENT_URL: str = "http://localhost:8000/api/v1/webhooks/mock-payment"

    def get_token_price(self, duration_hours: int) -> Optional[Decimal]:
        """Get token price by duration in ZNC credits"""
        price_map = {
            1: self.TOKEN_PRICE_1H,
            12: self.TOKEN_PRICE_12H,
            24: self.TOKEN_PRICE_24H,
            168: self.TOKEN_PRICE_7D,
            720: self.TOKEN_PRICE_30D,
        }
        return price_map.get(duration_hours)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
