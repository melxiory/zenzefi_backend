# Changelog

All notable changes to the Zenzefi Backend project will be documented in this file.

## [Unreleased]

### Added
- Docker deployment support (2025-01-27)
  - Complete Docker Compose configuration for production
  - Automated Docker deployment script (scripts/deploy_docker.sh)
  - Docker deployment guide (DEPLOYMENT_DOCKER.md)
  - All services in containers: PostgreSQL, Redis, Backend, Nginx, Certbot
  - Docker-based backup and monitoring procedures
  - 5-10 minute deployment vs 30+ minutes for native installation
- Desktop client support via `X-Local-Url` header (2025-01-27)
  - Backend now reads `X-Local-Url` header from desktop client requests
  - Dynamic content rewriting based on local proxy URL
  - JavaScript injection adapted for transparent proxy mode
  - No URL prefix added when desktop client detected
- Production deployment documentation (2025-01-27)
  - Complete deployment guide with step-by-step instructions (DEPLOYMENT.md)
  - Automated deployment script for Ubuntu 22.04 (scripts/deploy.sh)
  - Quick reference cheat sheet (QUICKSTART.md)
  - Nginx configuration with SSL/TLS via Let's Encrypt
  - Systemd service configuration
  - PostgreSQL and Redis setup
  - Backup and monitoring procedures

### Changed
- Updated `proxy_service.py` to support desktop client mode
  - Added `X-Local-Url` header detection
  - Dynamic `ContentRewriter` creation for desktop clients
  - Conditional JavaScript and static asset URL rewriting
  - Excluded `x-local-url` header from upstream forwarding

## [0.1.0] - 2025-01-27

### Added (MVP Phase - Этап 1) ✅
- User authentication system
  - User registration with email and username
  - Login with JWT token generation
  - Password hashing with bcrypt
  - JWT token validation and refresh
- Access token system
  - Token generation with configurable durations (1h, 12h, 24h, week, month)
  - Token validation with Redis caching
  - Token activation on first use
  - Token revocation support
  - `expires_at` calculated as property (not stored in DB)
- Proxy functionality
  - HTTP request proxying to Zenzefi server
  - WebSocket connection proxying
  - Content rewriting for URLs in responses
  - JavaScript injection for client-side URL interception
  - HTTP Basic Auth support for upstream server
- Cookie-based authentication
  - Desktop client browser authentication via cookies
  - Cookie validation on each proxy request
  - HTTP-only, secure cookies with configurable SameSite policy
  - Cookie path set to "/" for entire domain access
  - Authentication status endpoint
  - Logout functionality
- Database
  - PostgreSQL with SQLAlchemy 2.0 ORM
  - Alembic migrations
  - User model with UUID primary keys
  - AccessToken model with relationships
- Caching
  - Redis integration for token caching
  - Fast token validation (cache hit ~1ms vs DB ~10ms)
  - TTL-based cache expiration
- Testing
  - 85 tests with 85%+ code coverage
  - Integration tests with real PostgreSQL and Redis
  - Test fixtures for authenticated clients
  - Isolated test database (zenzefi_test)
- API Documentation
  - OpenAPI (Swagger) at /docs
  - ReDoc at /redoc
  - Health check endpoint at /health
- Development setup
  - Docker Compose for PostgreSQL and Redis
  - Poetry for dependency management
  - Hot reload with uvicorn
  - Environment variable configuration

### Security
- JWT tokens with HS256 algorithm
- Password hashing with bcrypt
- HTTP-only cookies for desktop client auth
- Token expiration and validation
- CORS middleware configuration
- Rate limiting preparation in Nginx config

### Documentation
- CLAUDE.md with comprehensive project documentation
- README.md with quick start guide
- API endpoint documentation
- Testing guidelines
- Database schema documentation
- Architecture diagrams and request flows

## Project Status

**Current Phase**: MVP Complete (Этап 1) ✅

**Production Ready**: Yes
- All core features implemented
- 85/85 tests passing
- Production deployment scripts ready
- Documentation complete

**Next Phases**:
- Этап 2: Currency System (ZNC credits, transactions, refunds)
- Этап 3: Monitoring (proxy sessions, admin endpoints, metrics)
- Этап 4: Advanced Production (CI/CD, advanced monitoring)

---

## Version Numbering

This project follows [Semantic Versioning](https://semver.org/):
- MAJOR version for incompatible API changes
- MINOR version for new functionality in a backward compatible manner
- PATCH version for backward compatible bug fixes

## Categories

- **Added**: New features
- **Changed**: Changes in existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Security improvements