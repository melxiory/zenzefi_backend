"""
Tests for Token Bundle functionality.

Tests:
- Bundle listing and retrieval
- Bundle purchase with balance validation
- Bundle purchase API endpoints
- Bundle admin operations
"""
import pytest
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException

from app.models.bundle import TokenBundle
from app.models.user import User
from app.services.bundle_service import BundleService


class TestBundleModel:
    """Tests for TokenBundle model."""

    def test_bundle_model_creation(self, test_db):
        """Test creating a TokenBundle."""
        bundle = TokenBundle(
            name="Test Bundle",
            description="Test description",
            token_count=5,
            duration_hours=24,
            scope="full",
            discount_percent=Decimal("10.00"),
            base_price=Decimal("90.00"),
            total_price=Decimal("81.00"),
            is_active=True
        )
        test_db.add(bundle)
        test_db.commit()
        test_db.refresh(bundle)

        assert bundle.id is not None
        assert bundle.name == "Test Bundle"
        assert bundle.token_count == 5
        assert bundle.duration_hours == 24
        assert bundle.is_active is True

    def test_bundle_savings_property(self, test_db):
        """Test computed savings property."""
        bundle = TokenBundle(
            name="Test Bundle",
            token_count=5,
            duration_hours=24,
            discount_percent=Decimal("10.00"),
            base_price=Decimal("100.00"),
            total_price=Decimal("90.00")
        )
        test_db.add(bundle)
        test_db.commit()

        assert bundle.savings == Decimal("10.00")

    def test_bundle_price_per_token_property(self, test_db):
        """Test computed price_per_token property."""
        bundle = TokenBundle(
            name="Test Bundle",
            token_count=5,
            duration_hours=24,
            discount_percent=Decimal("10.00"),
            base_price=Decimal("100.00"),
            total_price=Decimal("90.00")
        )
        test_db.add(bundle)
        test_db.commit()

        assert bundle.price_per_token == Decimal("18.00")  # 90 / 5


class TestBundleService:
    """Tests for BundleService."""

    @pytest.fixture
    def sample_bundle(self, test_db):
        """Create a sample bundle for testing."""
        bundle = TokenBundle(
            name="Test Bundle",
            description="5 tokens for testing",
            token_count=5,
            duration_hours=24,
            scope="full",
            discount_percent=Decimal("10.00"),
            base_price=Decimal("90.00"),
            total_price=Decimal("81.00"),
            is_active=True
        )
        test_db.add(bundle)
        test_db.commit()
        test_db.refresh(bundle)
        return bundle

    @pytest.fixture
    def inactive_bundle(self, test_db):
        """Create an inactive bundle for testing."""
        bundle = TokenBundle(
            name="Inactive Bundle",
            token_count=5,
            duration_hours=24,
            discount_percent=Decimal("10.00"),
            base_price=Decimal("90.00"),
            total_price=Decimal("81.00"),
            is_active=False
        )
        test_db.add(bundle)
        test_db.commit()
        test_db.refresh(bundle)
        return bundle

    def test_get_available_bundles(self, test_db, sample_bundle, inactive_bundle):
        """Test retrieving available bundles (only active)."""
        bundles = BundleService.get_available_bundles(test_db, active_only=True)

        # Should only return active bundles
        bundle_ids = [b.id for b in bundles]
        assert sample_bundle.id in bundle_ids
        assert inactive_bundle.id not in bundle_ids

    def test_get_all_bundles_including_inactive(self, test_db, sample_bundle, inactive_bundle):
        """Test retrieving all bundles including inactive."""
        bundles = BundleService.get_available_bundles(test_db, active_only=False)

        bundle_ids = [b.id for b in bundles]
        assert sample_bundle.id in bundle_ids
        assert inactive_bundle.id in bundle_ids

    def test_get_bundle_by_id_success(self, test_db, sample_bundle):
        """Test retrieving bundle by ID."""
        bundle = BundleService.get_bundle_by_id(test_db, sample_bundle.id)

        assert bundle.id == sample_bundle.id
        assert bundle.name == sample_bundle.name

    def test_get_bundle_by_id_inactive_raises_404(self, test_db, inactive_bundle):
        """Test retrieving inactive bundle raises 404."""
        with pytest.raises(HTTPException) as exc_info:
            BundleService.get_bundle_by_id(test_db, inactive_bundle.id)

        assert exc_info.value.status_code == 404
        assert "not found or inactive" in str(exc_info.value.detail)

    def test_get_bundle_by_id_nonexistent_raises_404(self, test_db):
        """Test retrieving non-existent bundle raises 404."""
        fake_id = uuid4()

        with pytest.raises(HTTPException) as exc_info:
            BundleService.get_bundle_by_id(test_db, fake_id)

        assert exc_info.value.status_code == 404

    def test_purchase_bundle_success(self, test_db, test_user, sample_bundle):
        """Test successful bundle purchase."""
        # Give user sufficient balance
        test_user.currency_balance = Decimal("200.00")
        test_db.commit()

        # Purchase bundle
        result = BundleService.purchase_bundle(
            bundle_id=sample_bundle.id,
            user_id=test_user.id,
            db=test_db
        )

        # Verify result
        assert result["bundle_name"] == "Test Bundle"
        assert result["tokens_generated"] == 5
        assert result["cost_znc"] == Decimal("81.00")
        assert result["new_balance"] == Decimal("119.00")  # 200 - 81

        # Verify tokens were created
        assert len(result["tokens"]) == 5
        for token in result["tokens"]:
            assert token["duration_hours"] == 24
            assert token["scope"] == "full"

        # Verify balance was deducted
        test_db.refresh(test_user)
        assert test_user.currency_balance == Decimal("119.00")

    def test_purchase_bundle_insufficient_balance(self, test_db, test_user, sample_bundle):
        """Test bundle purchase with insufficient balance."""
        # Give user insufficient balance
        test_user.currency_balance = Decimal("50.00")
        test_db.commit()

        # Attempt purchase
        with pytest.raises(HTTPException) as exc_info:
            BundleService.purchase_bundle(
                bundle_id=sample_bundle.id,
                user_id=test_user.id,
                db=test_db
            )

        assert exc_info.value.status_code == 402
        assert "Insufficient balance" in str(exc_info.value.detail)

        # Verify balance unchanged
        test_db.refresh(test_user)
        assert test_user.currency_balance == Decimal("50.00")

    def test_purchase_bundle_inactive_raises_404(self, test_db, test_user, inactive_bundle):
        """Test purchasing inactive bundle raises 404."""
        test_user.currency_balance = Decimal("200.00")
        test_db.commit()

        with pytest.raises(HTTPException) as exc_info:
            BundleService.purchase_bundle(
                bundle_id=inactive_bundle.id,
                user_id=test_user.id,
                db=test_db
            )

        assert exc_info.value.status_code == 404

    def test_purchase_bundle_user_not_found(self, test_db, sample_bundle):
        """Test bundle purchase with non-existent user."""
        fake_user_id = uuid4()

        with pytest.raises(HTTPException) as exc_info:
            BundleService.purchase_bundle(
                bundle_id=sample_bundle.id,
                user_id=fake_user_id,
                db=test_db
            )

        assert exc_info.value.status_code == 404
        assert "User not found" in str(exc_info.value.detail)

    def test_create_bundle(self, test_db):
        """Test creating a new bundle."""
        bundle = BundleService.create_bundle(
            db=test_db,
            name="New Bundle",
            description="New bundle description",
            token_count=10,
            duration_hours=168,
            scope="full",
            discount_percent=Decimal("15.00"),
            base_price=Decimal("1000.00"),
            total_price=Decimal("850.00"),
            is_active=True
        )

        assert bundle.id is not None
        assert bundle.name == "New Bundle"
        assert bundle.token_count == 10
        assert bundle.is_active is True

    def test_update_bundle(self, test_db, sample_bundle):
        """Test updating a bundle."""
        updated_bundle = BundleService.update_bundle(
            db=test_db,
            bundle_id=sample_bundle.id,
            name="Updated Bundle",
            total_price=Decimal("75.00")
        )

        assert updated_bundle.name == "Updated Bundle"
        assert updated_bundle.total_price == Decimal("75.00")
        assert updated_bundle.token_count == 5  # Unchanged

    def test_delete_bundle_soft_delete(self, test_db, sample_bundle):
        """Test soft deleting a bundle."""
        result = BundleService.delete_bundle(test_db, sample_bundle.id)

        assert result is True

        # Verify bundle is inactive
        test_db.refresh(sample_bundle)
        assert sample_bundle.is_active is False


class TestBundleAPI:
    """Tests for Bundle API endpoints."""

    @pytest.fixture
    def sample_bundle(self, test_db):
        """Create a sample bundle for API testing."""
        bundle = TokenBundle(
            name="API Test Bundle",
            description="Bundle for API testing",
            token_count=5,
            duration_hours=24,
            scope="full",
            discount_percent=Decimal("10.00"),
            base_price=Decimal("90.00"),
            total_price=Decimal("81.00"),
            is_active=True
        )
        test_db.add(bundle)
        test_db.commit()
        test_db.refresh(bundle)
        return bundle

    def test_list_bundles_endpoint(self, client, sample_bundle):
        """Test GET /bundles endpoint."""
        response = client.get("/api/v1/bundles")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) > 0

        # Find our bundle in results
        bundle_names = [b["name"] for b in data["items"]]
        assert "API Test Bundle" in bundle_names

    def test_get_bundle_by_id_endpoint(self, client, sample_bundle):
        """Test GET /bundles/{id} endpoint."""
        response = client.get(f"/api/v1/bundles/{sample_bundle.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "API Test Bundle"
        assert data["token_count"] == 5
        # Decimal fields serialized as strings in JSON
        assert Decimal(data["total_price"]) == Decimal("81.00")
        assert Decimal(data["discount_percent"]) == Decimal("10.00")
        assert Decimal(data["savings"]) == Decimal("9.00")

    def test_purchase_bundle_endpoint_success(self, client, test_db, test_user, sample_bundle):
        """Test POST /bundles/{id}/purchase endpoint with success."""
        # Give user sufficient balance
        test_user.currency_balance = Decimal("200.00")
        test_db.commit()

        # Get JWT token
        from app.core.security import create_access_token
        token = create_access_token(data={"sub": str(test_user.id), "username": test_user.username})

        # Purchase bundle
        response = client.post(
            f"/api/v1/bundles/{sample_bundle.id}/purchase",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["bundle_name"] == "API Test Bundle"
        assert data["tokens_generated"] == 5
        # Decimal serialized as string in JSON
        assert Decimal(data["cost_znc"]) == Decimal("81.00")
        assert Decimal(data["new_balance"]) == Decimal("119.00")  # 200 - 81

    def test_purchase_bundle_endpoint_no_auth(self, client, sample_bundle):
        """Test purchase without authentication returns 403 (HTTPBearer missing credentials)."""
        response = client.post(f"/api/v1/bundles/{sample_bundle.id}/purchase")

        assert response.status_code == 403  # HTTPBearer returns 403 for missing credentials

    def test_purchase_bundle_endpoint_insufficient_balance(self, client, test_db, test_user, sample_bundle):
        """Test purchase with insufficient balance returns 402."""
        # Give user insufficient balance
        test_user.currency_balance = Decimal("10.00")
        test_db.commit()

        # Get JWT token
        from app.core.security import create_access_token
        token = create_access_token(data={"sub": str(test_user.id), "username": test_user.username})

        # Attempt purchase
        response = client.post(
            f"/api/v1/bundles/{sample_bundle.id}/purchase",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 402
        data = response.json()
        assert "Insufficient balance" in data["detail"]
