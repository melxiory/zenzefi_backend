# Changelog

All notable changes to Zenzefi Backend will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0-beta] - 2025-01-06

### Fixed
- **Critical timezone-aware datetime comparison issue** across multiple modules
  - Fixed `TypeError: can't compare offset-naive and offset-aware datetimes` in token validation
  - Added timezone-awareness checks in `TokenService.check_token_status()` and `TokenService.validate_token()`
  - Fixed datetime comparison in `/api/v1/proxy/authenticate`, `/api/v1/proxy/status`, and proxy token handling
  - All `datetime.fromisoformat()` deserializations now properly handle timezone-naive datetime objects

### Changed
- Updated documentation (CLAUDE.md) with critical timezone handling guidelines
- Standardized on `datetime.now(timezone.utc)` instead of deprecated `datetime.utcnow()`

### Documentation
- Added comprehensive timezone handling section to CLAUDE.md files (root and backend)
- Documented timezone-awareness pattern: check `dt.tzinfo` before comparison with timezone-aware datetimes

## [0.1.0] - 2025-01-05

### Added
- Initial MVP release
- User authentication with JWT tokens
- Access token generation and management (1, 12, 24, 168, 720 hours duration)
- Two-tier token validation: Redis cache → PostgreSQL fallback
- Cookie-based authentication for desktop client integration
- HTTP and WebSocket proxy to Zenzefi server
- Content rewriting for local proxy URLs
- Health check system with background monitoring (PostgreSQL, Redis, Zenzefi)
- 85+ integration tests with real PostgreSQL and Redis (no mocks)
- Comprehensive API documentation (Swagger UI, ReDoc)
- Database migrations with Alembic
- Redis caching for active tokens
- Token activation on first use

### Security
- JWT tokens with HS256 algorithm (60 minutes expiration)
- bcrypt password hashing
- HTTP-only secure cookies
- Token revocation support
- CORS configuration

### Infrastructure
- Docker Compose setup for development and production
- PostgreSQL 15+ database
- Redis 7+ caching
- FastAPI 0.119+ async framework
- Python 3.13+ runtime
- APScheduler for background tasks
