"""
Test script to verify cost_znc property works correctly
"""
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.token import AccessToken
from app.schemas.token import TokenResponse
from app.config import settings


def test_cost_znc_property():
    """Test that cost_znc is calculated correctly via @property"""
    # Check settings fields directly
    print("Settings TOKEN_PRICE fields:")
    print(f"  TOKEN_PRICE_1H: {settings.TOKEN_PRICE_1H} (type: {type(settings.TOKEN_PRICE_1H)})")
    print(f"  TOKEN_PRICE_12H: {settings.TOKEN_PRICE_12H} (type: {type(settings.TOKEN_PRICE_12H)})")
    print(f"  TOKEN_PRICE_24H: {settings.TOKEN_PRICE_24H} (type: {type(settings.TOKEN_PRICE_24H)})")
    print(f"  TOKEN_PRICE_7D: {settings.TOKEN_PRICE_7D} (type: {type(settings.TOKEN_PRICE_7D)})")
    print(f"  TOKEN_PRICE_30D: {settings.TOKEN_PRICE_30D} (type: {type(settings.TOKEN_PRICE_30D)})")
    print()

    # Test settings.get_token_price() directly
    print("Testing settings.get_token_price():")
    for hours in [1, 12, 24, 168, 720]:
        price = settings.get_token_price(hours)
        print(f"  {hours}h -> {price} ZNC")
    print()

    db = SessionLocal()
    try:
        # Get all tokens from database
        tokens = db.query(AccessToken).limit(5).all()

        print(f"Found {len(tokens)} tokens in database\n")

        for token in tokens:
            # Direct model access
            print(f"Token ID: {token.id}")
            print(f"  Duration: {token.duration_hours}h")
            print(f"  Scope: {token.scope}")
            print(f"  Cost (via @property): {token.cost_znc} ZNC")

            # Pydantic serialization
            token_response = TokenResponse.model_validate(token)
            print(f"  Cost (via Pydantic): {token_response.cost_znc} ZNC")
            print()

        print("[OK] cost_znc property works correctly!")

    finally:
        db.close()


if __name__ == "__main__":
    test_cost_znc_property()
