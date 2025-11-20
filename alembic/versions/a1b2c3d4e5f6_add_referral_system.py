"""add referral system

Revision ID: a1b2c3d4e5f6
Revises: 15eb837251ea
Create Date: 2025-11-19 16:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '15eb837251ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add referral system columns to users table."""

    # Add referral_code column (unique, indexed)
    op.add_column('users', sa.Column(
        'referral_code',
        sa.String(length=12),
        nullable=True,  # Temporarily nullable for existing users
        comment='Unique 12-char referral code for this user'
    ))

    # Add referred_by_id column (FK to users.id)
    op.add_column('users', sa.Column(
        'referred_by_id',
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        comment='User who referred this user'
    ))

    # Add referral_bonus_earned column
    op.add_column('users', sa.Column(
        'referral_bonus_earned',
        sa.Numeric(precision=10, scale=2),
        nullable=False,
        server_default='0.00',
        comment='Total ZNC earned from referrals'
    ))

    # Generate unique referral codes for existing users
    op.execute("""
        UPDATE users
        SET referral_code = UPPER(
            SUBSTRING(MD5(RANDOM()::TEXT || id::TEXT) FROM 1 FOR 12)
        )
        WHERE referral_code IS NULL
    """)

    # Now make referral_code NOT NULL and add constraints
    op.alter_column('users', 'referral_code', nullable=False)

    # Create indexes
    op.create_index('ix_users_referral_code', 'users', ['referral_code'], unique=True)
    op.create_index('ix_users_referred_by_id', 'users', ['referred_by_id'])

    # Add REFERRAL_BONUS to transaction_type enum
    # Note: PostgreSQL enum alteration requires special handling
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'referral_bonus'")


def downgrade() -> None:
    """Remove referral system columns from users table."""

    # Drop indexes
    op.drop_index('ix_users_referred_by_id', 'users')
    op.drop_index('ix_users_referral_code', 'users')

    # Drop columns
    op.drop_column('users', 'referral_bonus_earned')
    op.drop_column('users', 'referred_by_id')
    op.drop_column('users', 'referral_code')

    # Note: Cannot remove enum value from PostgreSQL (enum limitation)
    # REFERRAL_BONUS will remain in transactiontype enum
