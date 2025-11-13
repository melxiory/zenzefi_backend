"""
Webhook endpoints for payment gateway callbacks.
"""
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.payment_service import MockPaymentProvider

router = APIRouter()


@router.post("/payment")
async def payment_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Payment webhook handler for mock payment gateway.

    In production with real gateway (YooKassa/Stripe):
    1. Verify webhook signature using HMAC
    2. Parse payment data
    3. Process payment status update

    Example (YooKassa):
        body = await request.body()
        signature = request.headers.get("X-Webhook-Signature")
        expected = hmac.new(
            settings.YOOKASSA_SECRET_KEY.encode(),
            body,
            hashlib.sha256
        ).hexdigest()

        if signature != expected:
            raise HTTPException(status_code=403, detail="Invalid signature")

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        dict with received and processed status

    Example Request:
        POST /api/v1/webhooks/payment
        {
            "payment_id": "MOCK_PAY_123",
            "status": "succeeded"  // or "canceled"
        }
    """
    try:
        data = await request.json()
        success = await MockPaymentProvider.handle_webhook(data, db)
        return {"received": True, "processed": success}
    except Exception as e:
        return {"received": True, "processed": False, "error": str(e)}


@router.get("/mock-payment")
async def mock_payment_page(
    payment_id: str,
    db: Session = Depends(get_db)
):
    """
    Mock payment completion page (simulates user completing payment).

    This endpoint is for development/testing only.
    In production, users would be redirected to real payment gateway.

    Args:
        payment_id: Payment ID to complete
        db: Database session

    Returns:
        dict with status and message

    Example:
        GET /api/v1/webhooks/mock-payment?payment_id=MOCK_PAY_123
    """
    success = await MockPaymentProvider.simulate_payment_success(payment_id, db)

    if success:
        return {
            "status": "success",
            "message": f"Payment {payment_id} completed successfully",
            "payment_id": payment_id
        }
    else:
        return {
            "status": "error",
            "message": "Payment not found or already processed",
            "payment_id": payment_id
        }
