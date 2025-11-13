from decimal import Decimal
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BalanceResponse(BaseModel):
    """Response for balance query"""

    balance: Decimal = Field(..., description="Current balance in ZNC")
    currency: str = Field(default="ZNC", description="Currency code")

    model_config = ConfigDict(from_attributes=True)


class TransactionResponse(BaseModel):
    """Response for transaction data"""

    id: UUID = Field(..., description="Transaction ID")
    amount: Decimal = Field(..., description="Amount in ZNC (+ for deposit/refund, - for purchase)")
    transaction_type: str = Field(..., description="Type: DEPOSIT, PURCHASE, REFUND")
    description: str = Field(..., description="Human-readable description")
    payment_id: Optional[str] = Field(None, description="External payment gateway ID")
    created_at: datetime = Field(..., description="Transaction creation time")

    model_config = ConfigDict(from_attributes=True)


class PaginatedTransactionsResponse(BaseModel):
    """Paginated response for transactions list"""

    items: List[TransactionResponse] = Field(..., description="List of transactions")
    total: int = Field(..., description="Total number of transactions")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Offset from start")

    model_config = ConfigDict(from_attributes=True)


class MockPurchaseRequest(BaseModel):
    """Request to mock purchase ZNC (for development/testing)"""

    amount: Decimal = Field(..., gt=0, description="Amount of ZNC to add (must be positive)")


class MockPurchaseResponse(BaseModel):
    """Response for mock purchase"""

    success: bool = Field(..., description="Whether the purchase was successful")
    amount: Decimal = Field(..., description="Amount added in ZNC")
    new_balance: Decimal = Field(..., description="New balance after purchase")
    message: str = Field(..., description="Success message")

    model_config = ConfigDict(from_attributes=True)


class PurchaseRequest(BaseModel):
    """Request to purchase ZNC via payment gateway"""

    amount_znc: Decimal = Field(..., gt=0, description="Amount of ZNC to purchase (must be positive)")
    return_url: str = Field(..., description="URL to redirect after payment completion")


class PurchaseResponse(BaseModel):
    """Response for ZNC purchase (payment gateway)"""

    payment_id: str = Field(..., description="Payment gateway payment ID")
    payment_url: str = Field(..., description="URL to complete payment")
    amount_znc: Decimal = Field(..., description="Amount to purchase in ZNC")
    amount_rub: Decimal = Field(..., description="Amount to pay in RUB")
    status: str = Field(default="pending", description="Payment status")

    model_config = ConfigDict(from_attributes=True)
