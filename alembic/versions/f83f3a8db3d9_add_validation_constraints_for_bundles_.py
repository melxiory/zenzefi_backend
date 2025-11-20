"""add_validation_constraints_for_bundles_and_referrals

Revision ID: f83f3a8db3d9
Revises: a1b2c3d4e5f6
Create Date: 2025-11-20 12:52:33.607865

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f83f3a8db3d9'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add validation constraints to prevent invalid data."""

    # TokenBundle constraints
    op.create_check_constraint(
        'check_discount_percent_range',
        'token_bundles',
        'discount_percent >= 0 AND discount_percent <= 100'
    )

    op.create_check_constraint(
        'check_token_count_positive',
        'token_bundles',
        'token_count > 0'
    )

    # User self-referral constraint
    op.create_check_constraint(
        'check_no_self_referral',
        'users',
        'referred_by_id IS NULL OR referred_by_id != id'
    )


def downgrade() -> None:
    """Remove validation constraints."""

    # Remove TokenBundle constraints
    op.drop_constraint('check_discount_percent_range', 'token_bundles', type_='check')
    op.drop_constraint('check_token_count_positive', 'token_bundles', type_='check')

    # Remove User constraint
    op.drop_constraint('check_no_self_referral', 'users', type_='check')
