

Вот полный файл BACKEND.md, готовый для копирования:
<artifact identifier="backend-md" type="application/vnd.ant.code" language="markdown" title="BACKEND.md"> # BACKEND.md

Этот файл предоставляет руководство для Claude Code при работе с Backend частью проекта Zenzefi.
Обзор проекта

Zenzefi Backend - сервер аутентификации и проксирования, контролирующий доступ клиентов к Zenzefi (Windows 11) по временным токенам. Сервер выступает посредником между десктопным клиентом и целевым сервером, обеспечивая монетизацию доступа.
Технологический стек

    FastAPI 0.104+ - async web framework
    PostgreSQL 15+ - основная БД
    Redis 7+ - кэш, сессии, rate limiting
    SQLAlchemy 2.0+ - ORM
    Alembic - миграции БД
    Pydantic v2 - валидация данных
    PyJWT - JWT токены
    Loguru - структурированное логирование
    Uvicorn - ASGI сервер
    Nginx - reverse proxy, SSL termination
    Docker + Docker Compose - контейнеризация

Архитектура системы

[Desktop Client] ──► [Nginx:443] ──► [FastAPI Backend] ──► [Zenzefi Server]
   (PySide6)          SSL/TLS          Token Auth            (Win11, VPN)
                                            │
                                            ├──► [PostgreSQL]
                                            └──► [Redis]
```

**Поток работы:**
1. Пользователь регистрируется через веб-сайт
2. Покупает внутреннюю валюту (ZNC - Zenzefi Credits)
3. За валюту покупает токен доступа на N часов
4. Вводит токен в Desktop Client
5. Client отправляет запросы с заголовком `X-Access-Token`
6. Backend валидирует токен и проксирует к Zenzefi Server
7. По истечении времени доступ закрывается

---

## Структура проекта
```
zenzefi-backend/
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI application entry point
│   ├── config.py                    # Settings (Pydantic BaseSettings)
│   ├── dependencies.py              # Global dependencies
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── security.py             # JWT, password hashing
│   │   ├── database.py             # SQLAlchemy engine, session factory
│   │   ├── redis.py                # Redis client singleton
│   │   └── logging.py              # Loguru configuration
│   │
│   ├── models/                     # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── user.py                 # User model
│   │   ├── token.py                # AccessToken model
│   │   ├── transaction.py          # Transaction model (currency)
│   │   └── proxy_session.py        # ProxySession model (monitoring)
│   │
│   ├── schemas/                    # Pydantic schemas (validation)
│   │   ├── __init__.py
│   │   ├── user.py                 # UserCreate, UserResponse, UserUpdate
│   │   ├── token.py                # TokenCreate, TokenResponse, TokenValidate
│   │   ├── auth.py                 # LoginRequest, TokenData
│   │   └── currency.py             # CurrencyBalance, TransactionResponse
│   │
│   ├── api/                        # API routes
│   │   ├── __init__.py
│   │   ├── deps.py                 # Route dependencies (get_db, get_current_user)
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── auth.py             # POST /auth/register, /auth/login
│   │       ├── users.py            # GET/PATCH /users/me
│   │       ├── tokens.py           # POST/GET /tokens/purchase, /tokens/validate
│   │       ├── currency.py         # GET/POST /currency/balance, /currency/purchase
│   │       └── proxy.py            # ALL /proxy/{path:path}
│   │
│   ├── services/                   # Business logic layer
│   │   ├── __init__.py
│   │   ├── auth_service.py         # Registration, login logic
│   │   ├── token_service.py        # Token generation, validation
│   │   ├── currency_service.py     # Currency management, transactions
│   │   └── proxy_service.py        # HTTP proxying to Zenzefi
│   │
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── rate_limit.py           # Redis-based rate limiting
│   │   └── logging.py              # Request/response logging
│   │
│   └── utils/
│       ├── __init__.py
│       ├── validators.py           # Custom Pydantic validators
│       └── exceptions.py           # Custom exception classes
│
├── alembic/                        # Database migrations
│   ├── versions/
│   ├── env.py
│   ├── script.py.mako
│   └── README
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Pytest fixtures
│   ├── test_auth.py
│   ├── test_tokens.py
│   ├── test_currency.py
│   └── test_proxy.py
│
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.nginx
│   └── nginx.conf
│
├── scripts/
│   ├── init_db.py                  # Database initialization
│   └── create_superuser.py         # Create admin user
│
├── .env.example
├── .dockerignore
├── .gitignore
├── docker-compose.yml              # Production
├── docker-compose.dev.yml          # Development
├── alembic.ini
├── pyproject.toml                  # Poetry dependencies
├── README.md
└── BACKEND.md                      # This file

Модели данных (PostgreSQL)
User
python

# app/models/user.py
from sqlalchemy import Column, String, Boolean, Numeric, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    currency_balance = Column(Numeric(10, 2), default=0.00, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    tokens = relationship("AccessToken", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    proxy_sessions = relationship("ProxySession", back_populates="user")

AccessToken
python

# app/models/token.py
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime

class AccessToken(Base):
    __tablename__ = "access_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)  # Random string or JWT
    duration_hours = Column(Integer, nullable=False)  # 1, 12, 24, 168, 720
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    activated_at = Column(DateTime, nullable=True)  # When first used
    is_active = Column(Boolean, default=True, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="tokens")
    proxy_sessions = relationship("ProxySession", back_populates="token")

Transaction
python

# app/models/transaction.py
from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import enum
from datetime import datetime

class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    PURCHASE = "purchase"
    REFUND = "refund"

class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    description = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="transactions")

ProxySession
python

# app/models/proxy_session.py
from sqlalchemy import Column, String, Boolean, DateTime, BigInteger, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime

class ProxySession(Base):
    __tablename__ = "proxy_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token_id = Column(UUID(as_uuid=True), ForeignKey("access_tokens.id"), nullable=False)
    ip_address = Column(String, nullable=False)
    user_agent = Column(String, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    bytes_transferred = Column(BigInteger, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="proxy_sessions")
    token = relationship("AccessToken", back_populates="proxy_sessions")

Redis структура
python

# Активные токены (быстрая валидация)
# Key: active_token:{sha256(token)}
# Value: JSON = {
#     "user_id": "uuid",
#     "token_id": "uuid",
#     "expires_at": "ISO timestamp",
#     "duration_hours": int
# }
# TTL: До истечения токена

# Активные proxy сессии
# Key: proxy_session:{session_id}
# Value: JSON = {
#     "user_id": "uuid",
#     "token_id": "uuid",
#     "started_at": "ISO timestamp",
#     "last_activity": "ISO timestamp"
# }
# TTL: 1 час (обновляется при активности)

# Rate limiting - аутентификация
# Key: rate_limit:auth:{ip}
# Value: int (количество попыток)
# TTL: 1 час

# Rate limiting - proxy запросы
# Key: rate_limit:proxy:{user_id}
# Value: int (количество запросов)
# TTL: 1 минута

API Endpoints
Authentication (/api/v1/auth)
Регистрация пользователя
http

POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "username": "johndoe",
  "password": "SecurePass123!",
  "full_name": "John Doe"  // optional
}

Response 201:
{
  "id": "uuid",
  "email": "user@example.com",
  "username": "johndoe",
  "full_name": "John Doe",
  "currency_balance": 0.00,
  "is_active": true,
  "created_at": "2025-10-15T10:00:00Z"
}

Логин
http

POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123!"
}

Response 200:
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}

Обновление токена
http

POST /api/v1/auth/refresh
Authorization: Bearer {refresh_token}

Response 200:
{
  "access_token": "new_jwt_token",
  "token_type": "bearer",
  "expires_in": 3600
}

Users (/api/v1/users)
Получить профиль
http

GET /api/v1/users/me
Authorization: Bearer {jwt_token}

Response 200:
{
  "id": "uuid",
  "email": "user@example.com",
  "username": "johndoe",
  "full_name": "John Doe",
  "currency_balance": 150.00,
  "is_active": true,
  "created_at": "2025-10-15T10:00:00Z",
  "updated_at": "2025-10-15T10:00:00Z"
}

Обновить профиль
http

PATCH /api/v1/users/me
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "full_name": "John Smith",  // optional
  "password": "NewPass123!"    // optional
}

Response 200: User object

Currency (/api/v1/currency)
Получить баланс
http

GET /api/v1/currency/balance
Authorization: Bearer {jwt_token}

Response 200:
{
  "balance": 150.00,
  "currency": "ZNC"  // Zenzefi Credits
}

Пополнить баланс (заглушка для MVP)
http

POST /api/v1/currency/purchase
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "amount": 100.00,
  "payment_method": "card"  // placeholder
}

Response 200:
{
  "transaction_id": "uuid",
  "amount": 100.00,
  "new_balance": 250.00,
  "transaction_type": "deposit",
  "created_at": "2025-10-15T11:00:00Z"
}

История транзакций
http

GET /api/v1/currency/transactions?limit=20&offset=0
Authorization: Bearer {jwt_token}

Response 200:
{
  "items": [
    {
      "id": "uuid",
      "amount": 100.00,
      "transaction_type": "deposit",
      "description": "Balance top-up",
      "created_at": "2025-10-15T11:00:00Z"
    }
  ],
  "total": 50,
  "limit": 20,
  "offset": 0
}

Tokens (/api/v1/tokens)
Купить токен доступа
http

POST /api/v1/tokens/purchase
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "duration_hours": 24  // 1, 12, 24, 168 (week), 720 (month)
}

Response 200:
{
  "token_id": "uuid",
  "token": "abc123def456...",  // Access token string
  "duration_hours": 24,
  "cost": 18.00,  // Списано с баланса ZNC
  "expires_at": "2025-10-16T11:00:00Z",
  "created_at": "2025-10-15T11:00:00Z",
  "is_active": true
}

Response 402 (Insufficient funds):
{
  "detail": "Insufficient balance. Required: 18.00 ZNC, Available: 10.00 ZNC"
}

Получить свои токены
http

GET /api/v1/tokens/my-tokens?active_only=true
Authorization: Bearer {jwt_token}

Response 200:
{
  "items": [
    {
      "token_id": "uuid",
      "token": "abc123def456...",
      "duration_hours": 24,
      "created_at": "2025-10-15T11:00:00Z",
      "expires_at": "2025-10-16T11:00:00Z",
      "activated_at": "2025-10-15T11:05:00Z",
      "is_active": true
    }
  ]
}

Валидировать токен
http

POST /api/v1/tokens/validate
Content-Type: application/json

{
  "token": "abc123def456..."
}

Response 200:
{
  "valid": true,
  "user_id": "uuid",
  "token_id": "uuid",
  "expires_at": "2025-10-16T11:00:00Z",
  "time_remaining_seconds": 82800
}

Response 200 (invalid):
{
  "valid": false,
  "reason": "Token expired"
}

Отозвать токен (с возвратом)
http

DELETE /api/v1/tokens/{token_id}
Authorization: Bearer {jwt_token}

Response 200:
{
  "revoked": true,
  "refund_amount": 5.00,  // Частичный возврат за неиспользованное время
  "new_balance": 155.00
}

Proxy (/api/v1/proxy)
Проксирование запросов к Zenzefi
http

GET/POST/PUT/DELETE/PATCH /api/v1/proxy/{path:path}
X-Access-Token: abc123def456...
[All other headers are proxied]

// Request is proxied to: https://zenzefi-server/{path}
// Response is returned as-is

Статус подключения
http

GET /api/v1/proxy/status
X-Access-Token: abc123def456...

Response 200:
{
  "connected": true,
  "user_id": "uuid",
  "session_id": "uuid",
  "token_id": "uuid",
  "started_at": "2025-10-15T11:05:00Z",
  "time_remaining_seconds": 82800,
  "expires_at": "2025-10-16T11:00:00Z",
  "bytes_transferred": 1048576
}

Response 401:
{
  "detail": "Invalid or expired access token"
}

Ключевые компоненты кода
Configuration (app/config.py)
python

from pydantic_settings import BaseSettings
from pydantic import PostgresDsn, RedisDsn, validator

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
    SQLALCHEMY_DATABASE_URI: PostgresDsn | None = None
    
    @validator("SQLALCHEMY_DATABASE_URI", pre=True)
    def assemble_db_connection(cls, v, values):
        if isinstance(v, str):
            return v
        return PostgresDsn.build(
            scheme="postgresql+psycopg2",
            username=values.get("POSTGRES_USER"),
            password=values.get("POSTGRES_PASSWORD"),
            host=values.get("POSTGRES_SERVER"),
            path=f"/{values.get('POSTGRES_DB') or ''}",
        )
    
    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    REDIS_URL: RedisDsn | None = None
    
    @validator("REDIS_URL", pre=True)
    def assemble_redis_connection(cls, v, values):
        if isinstance(v, str):
            return v
        password = values.get("REDIS_PASSWORD")
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{values.get('REDIS_HOST')}:{values.get('REDIS_PORT')}/{values.get('REDIS_DB')}"
    
    # Zenzefi Target
    ZENZEFI_TARGET_URL: str = "https://zenzefi-win11-server"
    
    # Token Pricing (ZNC credits)
    TOKEN_PRICE_1H: float = 1.0
    TOKEN_PRICE_12H: float = 10.0
    TOKEN_PRICE_24H: float = 18.0
    TOKEN_PRICE_7D: float = 100.0   # 168 hours
    TOKEN_PRICE_30D: float = 300.0  # 720 hours
    
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

Security (app/core/security.py)
python

from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash password using bcrypt"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict | None:
    """Decode JWT access token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None

Token Service (app/services/token_service.py)
python

import secrets
import hashlib
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.token import AccessToken
from app.models.user import User
from app.models.transaction import Transaction, TransactionType
from app.core.redis import get_redis_client
from app.config import settings
import json

class TokenService:
    
    @staticmethod
    def generate_access_token(
        user_id: str, 
        duration_hours: int, 
        db: Session
    ) -> tuple[AccessToken, Decimal]:
        """
        Generate new access token and deduct cost from user balance
        
        Returns:
            tuple[AccessToken, Decimal]: (token, cost_deducted)
        
        Raises:
            ValueError: If insufficient balance
        """
        # Calculate cost
        cost = Decimal(str(settings.get_token_price(duration_hours)))
        
        # Get user and check balance
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        
        if user.currency_balance < cost:
            raise ValueError(
                f"Insufficient balance. Required: {cost} ZNC, Available: {user.currency_balance} ZNC"
            )
        
        # Generate random token (URL-safe, 48 bytes = 64 chars)
        token_string = secrets.token_urlsafe(48)
        
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=duration_hours)
        
        # Create token record
        db_token = AccessToken(
            user_id=user_id,
            token=token_string,
            duration_hours=duration_hours,
            created_at=now,
            expires_at=expires_at,
            is_active=True
        )
        
        # Deduct cost from user balance
        user.currency_balance -= cost
        
        # Create transaction record
        transaction = Transaction(
            user_id=user_id,
            amount=-cost,
            transaction_type=TransactionType.PURCHASE,
            description=f"Token purchase: {duration_hours}h access"
        )
        
        db.add(db_token)
        db.add(transaction)
        db.commit()
        db.refresh(db_token)
        
        # Cache token in Redis
        TokenService._cache_token(db_token)
        
        return db_token, cost
    
    @staticmethod
    def validate_token(token: str, db: Session) -> tuple[bool, dict | None]:
        """
        Validate access token
        
        Returns:
            tuple[bool, dict | None]: (is_valid, token_data)
        """
        # Check Redis cache first (fast path)
        redis_data = TokenService._get_cached_token(token)
        if redis_data:
            expires_at = datetime.fromisoformat(redis_data['expires_at'])
            if expires_at > datetime.utcnow():
                return True, redis_data
            else:
                # Expired token in cache, remove it
                TokenService._remove_cached_token(token)
        
        # Check database (slow path)
        db_token = db.query(AccessToken).filter(
            AccessToken.token == token,
            AccessToken.is_active == True,
            AccessToken.revoked_at == None,
            AccessToken.expires_at > datetime.utcnow()
        ).first()
        
        if db_token:
            # Activate token on first use
            if not db_token.activated_at:
                db_token.activated_at = datetime.utcnow()
                db.commit()
                db.refresh(db_token)
            
            # Update Redis cache
            TokenService._cache_token(db_token)
            
            token_data = {
                "user_id": str(db_token.user_id),
                "token_id": str(db_token.id),
                "expires_at": db_token.expires_at.isoformat(),
                "duration_hours": db_token.duration_hours
            }
            
            return True, token_data
        
        return False, None
    
    @staticmethod
    def revoke_token(token_id: str, user_id: str, db: Session) -> Decimal:
        """
        Revoke token and calculate refund
        
        Returns:
            Decimal: refund_amount
        """
        db_token = db.query(AccessToken).filter(
            AccessToken.id == token_id,
            AccessToken.user_id == user_id,
            AccessToken.is_active == True
        ).first()
        
        if not db_token:
            raise ValueError("Token not found or already revoked")
        
        # Calculate refund (proportional to unused time)
        now = datetime.utcnow()
        if db_token.activated_at:
            time_used = (now - db_token.activated_at).total_seconds() / 3600  # hours
        else:
            time_used = 0
        
        time_total = db_token.duration_hours
        time_unused = max(0, time_total - time_used)
        
        cost = Decimal(str(settings.get_token_price(db_token.duration_hours)))
        refund_amount = cost * Decimal(time_unused / time_total)
        refund_amount = refund_amount.quantize(Decimal('0.01'))  # Round to 2 decimals
        
        # Revoke token
        db_token.is_active = False
        db_token.revoked_at = now
        
        # Refund to user
        user = db.query(User).filter(User.id == user_id).first()
        user.currency_balance += refund_amount
        
        # Create refund transaction
        if refund_amount > 0:
            transaction = Transaction(
                user_id=user_id,
                amount=refund_amount,
                transaction_type=TransactionType.REFUND,
                description=f"Token refund: {time_unused:.1f}h unused"
            )
            db.add(transaction)
        
        db.commit()
        
        # Remove from Redis cache
        TokenService._remove_cached_token(db_token.token)
        
        return refund_amount
    
    @staticmethod
    def _cache_token(token: AccessToken):
        """Cache token in Redis"""
        redis = get_redis_client()
        token_hash = hashlib.sha256(token.token.encode()).hexdigest()
        key = f"active_token:{token_hash}"
        
        data = {
            "user_id": str(token.user_id),
            "token_id": str(token.id),
            "expires_at": token.expires_at.isoformat(),
            "duration_hours": token.duration_hours
        }
        
        ttl = int((token.expires_at - datetime.utcnow()).total_seconds())
        if ttl > 0:
            redis.setex(key, ttl, json.dumps(data))
    
    @staticmethod
    def _get_cached_token(token: str) -> dict | None:
        """Get token from Redis cache"""
        redis = get_redis_client()
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        key = f"active_token:{token_hash}"
        
        data = redis.get(key)
        if data:
            return json.loads(data)
        return None
    
    @staticmethod
    def _remove_cached_token(token: str):
        """Remove token from Redis cache"""
        redis = get_redis_client()
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        key = f"active_token:{token_hash}"
        redis.delete(key)

Proxy Service (app/services/proxy_service.py)
python

import httpx
from fastapi import Request, Response
from app.config import settings
from loguru import logger

class ProxyService:
    
    @staticmethod
    async def proxy_request(
        request: Request, 
        path: str,
        user_id: str,
        token_id: str
    ) -> Response:
        """
        Proxy HTTP request to Zenzefi server
        
        Args:
            request: FastAPI Request object
            path: URL path to proxy
            user_id: Authenticated user ID
            token_id: Access token ID (for logging)
        
        Returns:
            Response: Proxied response
        """
        # Build target URL
        target_url = f"{settings.ZENZEFI_TARGET_URL}/{path}"
        
        # Copy headers (exclude certain headers)
        headers = {}
        for key, value in request.headers.items():
            key_lower = key.lower()
            if key_lower not in ['host', 'x-access-token', 'content-length', 'transfer-encoding']:
                headers[key] = value
        
        # Add forwarding headers
        headers.update({
            'X-Forwarded-For': request.client.host,
            'X-Forwarded-Proto': 'https',
            'X-Forwarded-Host': request.headers.get('host', 'unknown'),
            'X-User-Id': user_id,  # For Zenzefi server logging
            'X-Token-Id': token_id
        })
        
        try:
            async with httpx.AsyncClient(
                verify=False,  # Skip SSL verification for internal VPN
                timeout=30.0,
                follow_redirects=False
            ) as client:
                
                # Read request body
                body = await request.body()
                
                # Log request
                logger.info(
                    f"Proxy: {request.method} {target_url} | "
                    f"User: {user_id} | Token: {token_id}"
                )
                
                # Execute proxied request
                response = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                    params=request.query_params
                )
                
                # Prepare response headers
                response_headers = {}
                for key, value in response.headers.items():
                    key_lower = key.lower()
                    # Skip hop-by-hop headers
                    if key_lower not in ['connection', 'keep-alive', 'transfer-encoding', 'content-length']:
                        response_headers[key] = value
                
                # Log response
                logger.info(
                    f"Proxy response: {response.status_code} | "
                    f"Size: {len(response.content)} bytes"
                )
                
                # Return proxied response
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=response_headers,
                    media_type=response.headers.get('content-type')
                )
                
        except httpx.TimeoutException:
            logger.error(f"Proxy timeout: {target_url}")
            return Response(
                content="Gateway Timeout: Zenzefi server did not respond",
                status_code=504
            )
        
        except httpx.RequestError as e:
            logger.error(f"Proxy error: {e}")
            return Response(
                content=f"Bad Gateway: Unable to reach Zenzefi server - {str(e)}",
                status_code=502
            )
        
        except Exception as e:
            logger.exception(f"Unexpected proxy error: {e}")
            return Response(
                content="Internal Server Error",
                status_code=500
            )

Proxy Router (app/api/v1/proxy.py)
python

from fastapi import APIRouter, Request, Response, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.services.token_service import TokenService
from app.services.proxy_service import ProxyService

router = APIRouter()

@router.api_route(
    "/{path:path}", 
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]
)
async def proxy_to_zenzefi(
    path: str,
    request: Request,
    x_access_token: str = Header(..., alias="X-Access-Token"),
    db: Session = Depends(get_db)
):
    """
    Proxy all requests to Zenzefi server with token validation
    
    Headers:
        X-Access-Token: Access token string (required)
    """
    
    # Validate token
    valid, token_data = TokenService.validate_token(x_access_token, db)
    
    if not valid:
        raise HTTPException(
            status_code=401, 
            detail="Invalid or expired access token"
        )
    
    # Extract user and token IDs
    user_id = token_data['user_id']
    token_id = token_data['token_id']
    
    # Proxy request to Zenzefi
    response = await ProxyService.proxy_request(
        request=request,
        path=path,
        user_id=user_id,
        token_id=token_id
    )
    
    return response


@router.get("/status")
async def proxy_status(
    x_access_token: str = Header(..., alias="X-Access-Token"),
    db: Session = Depends(get_db)
):
    """
    Check proxy connection status and token validity
    
    Headers:
        X-Access-Token: Access token string (required)
    """
    
    # Validate token
    valid, token_data = TokenService.validate_token(x_access_token, db)
    
    if not valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token"
        )
    
    from datetime import datetime
    expires_at = datetime.fromisoformat(token_data['expires_at'])
    time_remaining = int((expires_at - datetime.utcnow()).total_seconds())
    
    return {
        "connected": True,
        "user_id": token_data['user_id'],
        "token_id": token_data['token_id'],
        "time_remaining_seconds": max(0, time_remaining),
        "expires_at": token_data['expires_at'],
        "status": "active"
    }

Docker Compose
docker-compose.yml (Production)
yaml

version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    container_name: zenzefi-postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-zenzefi}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-zenzefi_db}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - backend
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-zenzefi}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: zenzefi-redis
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    networks:
      - backend
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: docker/Dockerfile.backend
    container_name: zenzefi-backend
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - backend
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    build:
      context: .
      dockerfile: docker/Dockerfile.nginx
    container_name: zenzefi-nginx
    ports:
      - "443:443"
      - "80:80"
    depends_on:
      - backend
    volumes:
      - ./docker/nginx.conf:/etc/nginx/nginx.conf:ro
      - certbot_data:/etc/letsencrypt:ro
      - certbot_www:/var/www/certbot:ro
    networks:
      - backend
    restart: unless-stopped

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
  certbot_data:
    driver: local
  certbot_www:
    driver: local

networks:
  backend:
    driver: bridge

docker-compose.dev.yml (Development)
yaml

version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: zenzefi
      POSTGRES_PASSWORD: devpassword
      POSTGRES_DB: zenzefi_dev
    volumes:
      - postgres_dev_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    volumes:
      - redis_dev_data:/data

  backend:
    build:
      context: .
      dockerfile: docker/Dockerfile.backend
    ports:
      - "8000:8000"
    env_file:
      - .env.dev
    volumes:
      - .:/app  # Mount source code for hot reload
    command: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    depends_on:
      - postgres
      - redis

volumes:
  postgres_dev_data:
  redis_dev_data:

Этапы реализации
Этап 1: MVP (Minimum Viable Product) ✅ ПРИОРИТЕТ

Цель: Создать минимальную работающую систему для тестирования концепции

Задачи:

    ✅ Инициализация проекта
        Создать структуру папок
        Настроить Poetry (pyproject.toml)
        Настроить Docker Compose для dev
    ✅ База данных
        Создать модели SQLAlchemy (User, AccessToken)
        Настроить Alembic
        Создать первые миграции
    ✅ Аутентификация
        Реализовать JWT токены
        POST /auth/register
        POST /auth/login
        GET /users/me
    ✅ Система токенов
        POST /tokens/purchase (без оплаты, бесплатная генерация)
        POST /tokens/validate
        GET /tokens/my-tokens
    ✅ Проксирование
        ALL /proxy/{path:path} с валидацией токена
        GET /proxy/status

Время: 2-3 дня
Этап 2: Система валюты

Цель: Реализовать внутреннюю валюту и монетизацию

Задачи:

    Модели данных
        Создать Transaction model
        Добавить currency_balance в User
    Currency endpoints
        GET /currency/balance
        POST /currency/purchase (заглушка)
        GET /currency/transactions
    Интеграция с токенами
        Списание баланса при покупке токена
        Проверка достаточности средств
    Refund система
        DELETE /tokens/{token_id} с возвратом

Время: 1-2 дня
Этап 3: Мониторинг

Цель: Добавить инструменты для мониторинга и управления

Задачи:

    ProxySession model
        Трекинг активных сессий
        Логирование активности
    Admin endpoints
        GET /admin/users
        GET /admin/tokens
        PATCH /admin/users/{id}
    Метрики
        Health check endpoint
        Prometheus metrics

Время: 2 дня
Этап 4: Production

Цель: Подготовить к production

Задачи:

    Security
        Nginx с SSL (Let's Encrypt)
        Rate limiting
        CORS configuration
    Инфраструктура
        Production Docker Compose
        CI/CD pipeline
        Backup стратегия
    Документация
        OpenAPI/Swagger
        Deployment guide
        API examples

Время: 3-4 дня
Команды разработки
bash

# === Установка зависимостей ===
poetry install

# === Запуск dev сервера ===
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# === Миграции базы данных ===
# Создать миграцию
poetry run alembic revision --autogenerate -m "Add users table"

# Применить миграции
poetry run alembic upgrade head

# Откатить последнюю миграцию
poetry run alembic downgrade -1

# Показать историю миграций
poetry run alembic history

# === Docker команды ===
# Dev environment
docker-compose -f docker-compose.dev.yml up -d --build
docker-compose -f docker-compose.dev.yml logs -f backend
docker-compose -f docker-compose.dev.yml down -v

# Production
docker-compose up -d --build
docker-compose logs -f
docker-compose down

# === Тестирование ===
poetry run pytest
poetry run pytest --cov=app tests/
poetry run pytest -v tests/test_auth.py

# === Форматирование и линтинг ===
poetry run black app/
poetry run isort app/
poetry run flake8 app/
poetry run mypy app/

# === Создание суперпользователя ===
poetry run python scripts/create_superuser.py

# === Инициализация БД ===
poetry run python scripts/init_db.py

Интеграция с Desktop Client
Изменения в существующем клиенте

    Добавить auth_manager.py

python

   # core/auth_manager.py
   import httpx
   from pathlib import Path
   from cryptography.fernet import Fernet
   
   class AuthManager:
       def __init__(self):
           self.backend_url = "https://zenzefi.backend/api/v1"
           self.token_file = Path("app_data/access_token.enc")
       
       def login(self, email: str, password: str) -> bool:
           """Login and save token"""
           response = httpx.post(
               f"{self.backend_url}/auth/login",
               json={"email": email, "password": password},
               timeout=10.0
           )
           if response.status_code == 200:
               token = response.json()['access_token']
               self._save_token(token)
               return True
           return False
       
       def get_access_token(self) -> str | None:
           """Get saved access token"""
           if self.token_file.exists():
               encrypted = self.token_file.read_bytes()
               return self.cipher.decrypt(encrypted).decode()
           return None

    Модифицировать proxy_manager.py
        Добавить X-Access-Token заголовок ко всем запросам
        Изменить upstream_url на Backend URL

python

   # В ZenzefiProxy.handle_http()
   headers.update({
       "X-Access-Token": auth_manager.get_access_token(),
       # ... другие заголовки
   })

    Создать UI для логина
        Новый экран входа/регистрации
        Хранение токена в encrypted виде

Критические замечания
Безопасность ⚠️

    НИКОГДА не логировать:
        Полные access tokens
        Пароли (даже хешированные)
        JWT в полном виде
    Всегда использовать:
        HTTPS везде (включая внутренние соединения)
        Environment variables для секретов
        Pydantic для валидации всех входных данных
    Rate limiting:
        Аутентификация: 5 попыток/час с IP
        API: 100 запросов/минуту на пользователя
        Proxy: мониторинг аномального использования

Производительность 🚀

    Redis кэширование:
        Валидация токенов (TTL = до истечения)
        Сессии (TTL = 1 час, обновляется)
    Database:
        Connection pooling (min=5, max=20)
        Индексы на: email, username, token, user_id, expires_at
    Proxy:
        Connection reuse для Zenzefi
        Streaming для больших файлов

Масштабируемость 📈

    Stateless backend:
        Все сессии в Redis
        JWT для аутентификации
        Горизонтальное масштабирование
    Database:
        Read replicas для аналитики
        Партицирование таблиц (transactions, proxy_sessions)
    Monitoring:
        Health checks на /health
        Prometheus metrics
        Centralized logging (ELK/Loki)

Начало работы
Шаг 1: Создание проекта
bash

# Создать папку проекта
mkdir zenzefi-backend
cd zenzefi-backend

# Инициализировать Poetry
poetry init

# Добавить зависимости
poetry add fastapi uvicorn sqlalchemy alembic pydantic pydantic-settings \
    psycopg2-binary python-jose passlib bcrypt python-multipart \
    redis httpx loguru

poetry add --group dev pytest pytest-cov black isort flake8 mypy

Шаг 2: Создать структуру
bash

# Создать папки
mkdir -p app/{api/v1,core,models,schemas,services,middleware,utils}
mkdir -p docker scripts tests alembic/versions

# Создать __init__.py файлы
touch app/__init__.py
touch app/api/__init__.py
touch app/api/v1/__init__.py
touch app/core/__init__.py
touch app/models/__init__.py
touch app/schemas/__init__.py
touch app/services/__init__.py
touch app/middleware/__init__.py
touch app/utils/__init__.py
touch tests/__init__.py

Шаг 3: Настроить .env
bash

# Создать .env файл
cat > .env << EOF
# Application
DEBUG=True
SECRET_KEY=your-secret-key-here-change-in-production

# Database
POSTGRES_SERVER=localhost
POSTGRES_USER=zenzefi
POSTGRES_PASSWORD=devpassword
POSTGRES_DB=zenzefi_dev

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# Zenzefi Target
ZENZEFI_TARGET_URL=https://zenzefi-win11-server
EOF

Шаг 4: Запустить разработку
bash

# Запустить БД и Redis
docker-compose -f docker-compose.dev.yml up -d postgres redis

# Применить миграции
poetry run alembic upgrade head

# Запустить сервер
poetry run uvicorn app.main:app --reload
```

Сервер доступен на: http://localhost:8000  
Документация API: http://localhost:8000/docs

---

## Полезные ссылки

- **FastAPI:** https://fastapi.tiangolo.com/
- **SQLAlchemy:** https://docs.sqlalchemy.org/
- **Alembic:** https://alembic.sqlalchemy.org/
- **Pydantic:** https://docs.pydantic.dev/
- **Redis:** https://redis.io/docs/

---

**Этот документ должен использоваться Claude Code как основное руководство при создании Backend части проекта Zenzefi.**
</artifact>

Готово! Теперь вы можете:

1. **Скопировать весь текст** из артефакта выше
2. **Создать файл `BACKEND.md`** в корне вашего нового backend проекта
3. **Открыть Claude Code** и сказать:
```
Привет! Читай файл BACKEND.md в корне проекта. 
Начнем с Этапа 1 (MVP). Создай базовую структуру проекта 
и настрой Poetry с нужными зависимостями.

Файл полностью готов к использованию и содержит все необходимые детали для создания Backend части проекта! 🚀


Backend architecture for Zenzefi access platform - Claude
