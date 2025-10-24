"""Make expires_at nullable for lazy activation

Revision ID: f909ad8c76ed
Revises: 0cbf73fcb14e
Create Date: 2025-10-24 12:05:20.425582

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f909ad8c76ed'
down_revision: Union[str, Sequence[str], None] = '0cbf73fcb14e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make expires_at nullable to support lazy token activation."""
    # Make expires_at nullable (previously NOT NULL)
    op.alter_column('access_tokens', 'expires_at',
                   existing_type=sa.DateTime(),
                   nullable=True)


def downgrade() -> None:
    """Revert expires_at to NOT NULL."""
    # Make expires_at NOT NULL again
    op.alter_column('access_tokens', 'expires_at',
                   existing_type=sa.DateTime(),
                   nullable=False)
