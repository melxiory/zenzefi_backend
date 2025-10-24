# Token Activation Behavior

This document explains how token activation works in Zenzefi Backend.

## Overview

Tokens use **lazy activation**: they don't start expiring until first actual use. This ensures users get the full duration they paid for, regardless of when they start using the token.

## Token Lifecycle

```
1. Purchase    → Token created (expires_at = NULL, activated_at = NULL)
2. Check Status → Read-only check (no activation)
3. First Use   → Token activated (expires_at set, activated_at set)
4. Expiration  → Token expires after duration_hours from activation
```

## Endpoints and Activation

### ❌ Does NOT activate token:
- `POST /api/v1/tokens/purchase` - Creates token
- `GET /api/v1/tokens/my-tokens` - Lists user's tokens
- `POST /api/v1/tokens/validate` - Validates token **AND activates it!** ⚠️
- `GET /api/v1/proxy/status` - **Read-only status check (NEW!)**

### ✅ DOES activate token (on first use):
- `GET/POST/etc /api/v1/proxy/{path}` - Any proxy request
- `WS /api/v1/proxy/{path}` - WebSocket connections
- `POST /api/v1/tokens/validate` - Token validation endpoint

## API Examples

### Check Token Status (No Activation)

```bash
# Check if token is valid WITHOUT activating it
curl -H "X-Access-Token: your_token_here" \
     http://localhost:8000/api/v1/proxy/status
```

**Response for non-activated token:**
```json
{
  "connected": true,
  "user_id": "uuid",
  "token_id": "uuid",
  "is_activated": false,
  "expires_at": null,
  "time_remaining_seconds": null,
  "status": "ready",
  "duration_hours": 24
}
```

**Response for activated token:**
```json
{
  "connected": true,
  "user_id": "uuid",
  "token_id": "uuid",
  "is_activated": true,
  "expires_at": "2025-10-25T12:00:00",
  "time_remaining_seconds": 86400,
  "status": "active",
  "duration_hours": 24
}
```

### Activate Token (First Proxy Request)

```bash
# First proxy request activates the token
curl -H "X-Access-Token: your_token_here" \
     http://localhost:8000/api/v1/proxy/
```

After this request:
- `activated_at` is set to current time
- `expires_at` is set to `activated_at + duration_hours`
- Token countdown begins

## Code Usage

### TokenService Methods

```python
from app.services.token_service import TokenService

# Read-only check (does NOT activate)
valid, token_data = TokenService.check_token_status(token, db)
if valid:
    print(f"Token ready, activated: {token_data['is_activated']}")

# Validate and activate on first use
valid, token_data = TokenService.validate_token(token, db)
if valid:
    print(f"Token validated and activated (if first use)")
```

### Key Differences

| Method | Activates Token? | Use Case |
|--------|------------------|----------|
| `check_token_status()` | ❌ No | Status checks, UI display |
| `validate_token()` | ✅ Yes (first use) | Proxy requests, actual usage |

## Desktop Client Implementation

```python
class ZenzefiClient:
    def check_status(self):
        """Check token without activating"""
        response = requests.get(
            f"{self.backend_url}/api/v1/proxy/status",
            headers={"X-Access-Token": self.token}
        )
        data = response.json()

        if not data["is_activated"]:
            print(f"Token ready: {data['duration_hours']}h available")
        else:
            hours_left = data["time_remaining_seconds"] / 3600
            print(f"Token active: {hours_left:.1f}h remaining")

    def connect(self):
        """Activate token and connect"""
        # This will activate the token on first call
        response = requests.get(
            f"{self.backend_url}/api/v1/proxy/",
            headers={"X-Access-Token": self.token}
        )
        print("Connected! Token is now active.")
```

## Migration Notes

### Before (Old Behavior)
- Tokens activated immediately on purchase
- `/proxy/status` activated tokens
- Users lost time between purchase and first use

### After (New Behavior)
- Tokens activate on first proxy request
- `/proxy/status` is read-only (no activation)
- Users get full duration from first use

### Breaking Changes
- `/proxy/status` response now includes `is_activated` field
- Non-activated tokens return `expires_at: null`
- Clients should check `is_activated` before showing time remaining

## Testing

Run the test suite to verify activation behavior:

```bash
# Test only proxy status endpoint
poetry run pytest tests/test_proxy_status.py -v

# Test all token-related functionality
poetry run pytest tests/test_token_service.py tests/test_api_tokens.py tests/test_proxy_status.py -v
```

## Database Schema

```sql
-- access_tokens table
CREATE TABLE access_tokens (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    token VARCHAR NOT NULL UNIQUE,
    duration_hours INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NULL,        -- NULL until activated
    activated_at TIMESTAMP NULL,       -- Set on first use
    is_active BOOLEAN NOT NULL,
    revoked_at TIMESTAMP NULL
);
```

## Troubleshooting

**Q: Token expires_at is NULL, is this a bug?**
A: No! This means the token hasn't been activated yet. It will be set on first proxy request.

**Q: How do I check token status without activating it?**
A: Use `GET /api/v1/proxy/status` or `TokenService.check_token_status()`.

**Q: Can I manually activate a token?**
A: Yes, by calling `TokenService.validate_token()` or making any proxy request.

**Q: What happens if I check status multiple times?**
A: Nothing! Status checks are read-only and can be called unlimited times.
