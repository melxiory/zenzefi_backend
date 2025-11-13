"""
Currency API endpoints for balance and transaction management
"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.models.transaction import TransactionType
from app.schemas.currency import (
    BalanceResponse,
    PaginatedTransactionsResponse,
    MockPurchaseRequest,
    MockPurchaseResponse,
    PurchaseRequest,
    PurchaseResponse,
)
from app.services.currency_service import CurrencyService
from app.services.payment_service import MockPaymentProvider

router = APIRouter()


@router.get("/balance", response_model=BalanceResponse)
def get_balance(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get current user's balance.

    Returns:
        BalanceResponse: Current balance in ZNC

    Raises:
        HTTPException: If user not found (should not happen with auth)
    """
    try:
        balance = CurrencyService.get_balance(current_user.id, db)
        return BalanceResponse(balance=balance, currency="ZNC")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get("/transactions", response_model=PaginatedTransactionsResponse)
def get_transactions(
    limit: int = Query(default=10, ge=1, le=100, description="Number of transactions to return"),
    offset: int = Query(default=0, ge=0, description="Number of transactions to skip"),
    transaction_type: Optional[TransactionType] = Query(
        default=None, description="Filter by transaction type"
    ),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get transaction history for current user with pagination and filtering.

    Args:
        limit: Number of transactions to return (1-100, default 10)
        offset: Number of transactions to skip (default 0)
        transaction_type: Filter by type (deposit, purchase, refund) - optional
        current_user: Authenticated user
        db: Database session

    Returns:
        PaginatedTransactionsResponse: Paginated list of transactions

    Example:
        GET /api/v1/currency/transactions?limit=20&offset=0&transaction_type=purchase
    """
    transactions, total = CurrencyService.get_transactions(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        transaction_type=transaction_type,
        db=db,
    )

    return PaginatedTransactionsResponse(
        items=transactions,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/mock-purchase", response_model=MockPurchaseResponse, status_code=status.HTTP_201_CREATED)
def mock_purchase(
    purchase_data: MockPurchaseRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Mock balance purchase for testing (temporary endpoint).

    ⚠️  WARNING: This is a MOCK endpoint for testing only!
    In production, this should be replaced with real payment gateway integration.

    Args:
        purchase_data: Purchase amount in ZNC
        current_user: Authenticated user
        db: Database session

    Returns:
        MockPurchaseResponse: New balance and transaction ID

    Raises:
        HTTPException:
            - 400: Invalid amount (must be positive)
    """
    # Validate amount
    if purchase_data.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be positive",
        )

    # Credit balance
    try:
        import hashlib
        user_hash = hashlib.md5(str(current_user.id).encode()).hexdigest()[:8]
        new_balance = CurrencyService.credit_balance(
            user_id=current_user.id,
            amount=purchase_data.amount,
            description=f"Mock purchase: {purchase_data.amount} ZNC",
            payment_id=f"MOCK_{user_hash}",
            db=db,
        )

        return MockPurchaseResponse(
            success=True,
            amount=purchase_data.amount,
            new_balance=new_balance,
            message=f"Successfully added {purchase_data.amount} ZNC to your balance",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/purchase", response_model=PurchaseResponse, status_code=status.HTTP_201_CREATED)
async def purchase_znc(
    request: PurchaseRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Create payment for purchasing ZNC credits via payment gateway.

    This endpoint initiates a payment through the payment provider (mock in development).
    User will be redirected to payment_url to complete the payment.

    Args:
        request: Purchase request (amount_znc, return_url)
        current_user: Authenticated user
        db: Database session

    Returns:
        PurchaseResponse: Payment details including payment_url

    Raises:
        HTTPException:
            - 422: Invalid amount (must be positive)

    Example:
        POST /api/v1/currency/purchase
        {
            "amount_znc": 100.00,
            "return_url": "https://app.zenzefi.com/payment/success"
        }

        Response:
        {
            "payment_id": "MOCK_PAY_123",
            "payment_url": "http://localhost:8000/api/v1/webhooks/mock-payment?payment_id=...",
            "amount_znc": 100.00,
            "amount_rub": 1000.00,
            "status": "pending"
        }
    """
    if request.amount_znc <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Amount must be positive",
        )

    payment_data = await MockPaymentProvider.create_payment(
        amount_znc=request.amount_znc,
        user_id=current_user.id,
        return_url=request.return_url,
        db=db
    )

    return PurchaseResponse(**payment_data)


@router.post("/admin/simulate-payment/{payment_id}")
async def simulate_payment(
    payment_id: str,
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to simulate successful payment (development/testing only).

    ⚠️  WARNING: This endpoint should be protected with admin authentication in production!
    Currently open for development/testing purposes.

    Args:
        payment_id: Payment ID to simulate success for
        db: Database session

    Returns:
        dict with success status and message

    Raises:
        HTTPException:
            - 404: Payment not found

    Example:
        POST /api/v1/currency/admin/simulate-payment/MOCK_PAY_123

        Response:
        {
            "success": true,
            "message": "Payment MOCK_PAY_123 simulated successfully"
        }
    """
    success = await MockPaymentProvider.simulate_payment_success(payment_id, db)

    if success:
        return {
            "success": True,
            "message": f"Payment {payment_id} simulated successfully"
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found or already processed"
        )
