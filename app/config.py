from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    PROJECT_NAME: str = "Zenzefi Backend"
    VERSION: str = "1.0.0"
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

    # Zenzefi Target
    ZENZEFI_TARGET_URL: str = "https://zenzefi-win11-server"
    ZENZEFI_BASIC_AUTH_USER: Optional[str] = None  # Optional: user for HTTP Basic Auth
    ZENZEFI_BASIC_AUTH_PASSWORD: Optional[str] = None  # Optional: password for HTTP Basic Auth

    # Backend URL (для ContentRewriter)
    # Это URL где доступен ваш backend для клиентов
    # Например: https://api.zenzefi.com или http://localhost:8000
    BACKEND_URL: str = "http://localhost:8000"  # Измените на реальный URL в production

    # Token Pricing (ZNC credits) - для MVP будут бесплатными
    TOKEN_PRICE_1H: float = 0.0      # Бесплатно для MVP
    TOKEN_PRICE_12H: float = 0.0     # Бесплатно для MVP
    TOKEN_PRICE_24H: float = 0.0     # Бесплатно для MVP
    TOKEN_PRICE_7D: float = 0.0      # Бесплатно для MVP (168 hours)
    TOKEN_PRICE_30D: float = 0.0     # Бесплатно для MVP (720 hours)

    def get_token_price(self, duration_hours: int) -> float:
        """Get token price by duration"""
        price_map = {
            1: self.TOKEN_PRICE_1H,
            12: self.TOKEN_PRICE_12H,
            24: self.TOKEN_PRICE_24H,
            168: self.TOKEN_PRICE_7D,
            720: self.TOKEN_PRICE_30D,
        }
        return price_map.get(duration_hours, 0.0)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
